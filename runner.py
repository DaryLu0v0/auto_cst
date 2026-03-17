"""runner.py -- fixed experiment harness for CST autoresearch.

DO NOT MODIFY this file during agent runs.

This is the CST equivalent of prepare.py in autoresearch.
It provides the stable runtime: load design -> validate -> open CST
-> inject parameters -> rebuild -> solve -> export -> evaluate -> log.

Usage:
    python runner.py                          # run with design.py defaults
    python runner.py --target 0.7             # override target frequency
    python runner.py --candidate-id 0001      # set explicit candidate ID
    python runner.py --skip-solve             # skip CST solve (use cached results)
    python runner.py --dry-run                # validate only, no CST
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# CST library setup  (must come before cst imports)
# ---------------------------------------------------------------------------
CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

import cst.interface as cstint   # noqa: E402
import cst.results as cstres     # noqa: E402

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
TEMPLATE_CST = HERE / "templates" / "base_project.cst"
WORKING_CST = HERE / "working.cst"
EXPORTS_DIR = HERE / "exports"
RESULTS_TSV = HERE / "results.tsv"
DESIGN_PY = HERE / "design.py"

# Default target
DEFAULT_TARGET_FREQ_THZ = 0.7

# Solver settings
POLL_INTERVAL = 5.0      # seconds between solver status checks
SOLVER_TIMEOUT = 1800.0  # 30 minutes max


# ---------------------------------------------------------------------------
# Parameter injection via VBA (the clean way to update CST parameters)
# ---------------------------------------------------------------------------

def _build_parameter_vba(params: dict) -> str:
    """Generate VBA code to update CST project parameters.

    Uses StoreDoubleParameter which updates the named parameter
    in the CST parameter list without needing to rebuild geometry
    history entries.
    """
    lines = []
    for name, value in params.items():
        # Skip non-geometric parameters
        if name in ("theta", "phi"):
            continue
        lines.append(f'StoreDoubleParameter "{name}", {value}')
    return "\n".join(lines)


def _inject_parameters(project, params: dict) -> None:
    """Push design parameters into the CST project."""
    vba = _build_parameter_vba(params)
    if vba.strip():
        m3d = project.model3d
        m3d.add_to_history("auto_cst: update design parameters", vba)


# ---------------------------------------------------------------------------
# S-parameter export via cst.results
# ---------------------------------------------------------------------------

def _export_results(project_path: str, export_dir: Path) -> Dict[str, str]:
    """Extract S-parameter and RTA results via cst.results.

    Must be called AFTER the project is closed by cst.interface,
    because cst.results opens the file independently.

    Returns dict mapping label -> file_path.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    exported = {}

    try:
        proj_res = cstres.ProjectFile(str(project_path), allow_interactive=True)
        proj3d = proj_res.get_3d()
        tree_items = proj3d.get_tree_items()

        sep = "\\"

        # --- S-Parameters (complex) ---
        s_param_items = [
            item for item in tree_items
            if item.startswith("1D Results" + sep + "S-Parameters" + sep + "S")
        ]

        import numpy as np

        for item_path in s_param_items:
            try:
                result = proj3d.get_result_item(item_path)
                xdata = np.array(result.get_xdata())
                ydata = result.get_ydata()
                # ydata is complex; export |S|^2 (power magnitude)
                mag_sq = np.array([abs(y) ** 2 for y in ydata])

                label = item_path.split(sep)[-1]  # e.g. "SZmax(2),Zmax(2)"
                out_path = export_dir / f"{label}.csv"

                with open(out_path, "w", newline="") as f:
                    f.write("# frequency_THz\t|S|^2\n")
                    for freq, val in zip(xdata, mag_sq):
                        f.write(f"{freq}\t{val}\n")

                exported[label] = str(out_path)
                print(f"    exported {label}: {len(xdata)} pts")

            except Exception as exc:
                print(f"    [WARN] {item_path}: {exc}")

        # --- Tables: Absorptance, Reflectance, Transmittance ---
        for tname in ["Absorptance", "Reflectance", "Transmittance"]:
            tpath = "Tables" + sep + "1D Results" + sep + tname
            if tpath not in tree_items:
                continue
            try:
                result = proj3d.get_result_item(tpath)
                xdata = np.array(result.get_xdata())
                ydata = result.get_ydata()
                vals = np.array([abs(y) for y in ydata])

                out_path = export_dir / f"{tname}.csv"
                with open(out_path, "w", newline="") as f:
                    f.write(f"# frequency_THz\t{tname}\n")
                    for freq, val in zip(xdata, vals):
                        f.write(f"{freq}\t{val}\n")

                exported[tname] = str(out_path)
                print(f"    exported {tname}: {len(xdata)} pts")

            except Exception as exc:
                print(f"    [WARN] {tname}: {exc}")

    except Exception as exc:
        print(f"  [ERROR] Result export failed: {exc}")
        import traceback
        traceback.print_exc()

    return exported


# ---------------------------------------------------------------------------
# Results logging
# ---------------------------------------------------------------------------

def _init_results_tsv() -> None:
    """Create results.tsv with header if it doesn't exist."""
    if not RESULTS_TSV.exists():
        with open(RESULTS_TSV, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([
                "candidate_id", "parent_id", "timestamp",
                "score", "valid", "f_res_thz", "abs_at_res",
                "freq_error", "abs_penalty",
                "solve_status", "solve_duration_s",
                "status", "note",
            ])


def _next_candidate_id() -> str:
    """Read results.tsv and return the next sequential ID."""
    if not RESULTS_TSV.exists():
        return "0001"
    with open(RESULTS_TSV, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        rows = list(reader)
    # Skip header, find max ID
    max_id = 0
    for row in rows[1:]:
        try:
            max_id = max(max_id, int(row[0]))
        except (ValueError, IndexError):
            pass
    return f"{max_id + 1:04d}"


def _log_result(
    candidate_id: str,
    parent_id: str,
    score: float,
    valid: bool,
    f_res: float,
    abs_at_res: float,
    freq_error: float,
    abs_penalty: float,
    solve_status: str,
    solve_duration: float,
    status: str,
    note: str,
) -> None:
    """Append one row to results.tsv."""
    _init_results_tsv()
    with open(RESULTS_TSV, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow([
            candidate_id, parent_id,
            datetime.now().isoformat(timespec="seconds"),
            f"{score:.6f}" if valid else "999.000000",
            str(valid).lower(),
            f"{f_res:.6f}" if valid else "NaN",
            f"{abs_at_res:.4f}" if valid else "NaN",
            f"{freq_error:.6f}" if valid else "NaN",
            f"{abs_penalty:.4f}" if valid else "NaN",
            solve_status,
            f"{solve_duration:.1f}",
            status, note,
        ])


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    target_freq_thz: float = DEFAULT_TARGET_FREQ_THZ,
    candidate_id: Optional[str] = None,
    parent_id: str = "root",
    note: str = "",
    skip_solve: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute one full experiment cycle.

    1. Load design.py
    2. Validate constraints
    3. Copy template -> working.cst
    4. Inject parameters
    5. Rebuild + solve
    6. Export S-parameters
    7. Evaluate score
    8. Log to results.tsv
    """
    from design import DESIGN
    from constraints import validate_design
    from evaluator import evaluate_candidate

    # --- Assign candidate ID ---
    _init_results_tsv()
    if candidate_id is None:
        candidate_id = _next_candidate_id()

    print(f"\n{'='*60}")
    print(f"  CST AutoResearch -- Candidate {candidate_id}")
    print(f"  Target: {target_freq_thz} THz")
    print(f"  Parameters: {json.dumps(DESIGN, indent=2)}")
    print(f"{'='*60}\n")

    # --- Step 1: Validate ---
    ok, reason = validate_design(DESIGN)
    if not ok:
        print(f"  [INVALID] {reason}")
        _log_result(
            candidate_id, parent_id,
            999.0, False, 0.0, 0.0, 0.0, 0.0,
            "skipped", 0.0, "invalid", reason,
        )
        return {"status": "invalid", "reason": reason, "candidate_id": candidate_id}

    print("  [OK] Design passes all constraints")

    if dry_run:
        print("  [DRY RUN] Stopping before CST.")
        return {"status": "dry_run", "candidate_id": candidate_id, "valid": True}

    # --- Step 2: Prepare working project ---
    if not TEMPLATE_CST.exists():
        msg = f"Template not found: {TEMPLATE_CST}"
        print(f"  [ERROR] {msg}")
        print(f"  [HINT] Copy your test.cst to {TEMPLATE_CST}")
        return {"status": "error", "message": msg}

    # Clean previous working files
    working_folder = WORKING_CST.parent / WORKING_CST.stem
    if working_folder.exists():
        shutil.rmtree(working_folder, ignore_errors=True)
    if WORKING_CST.exists():
        WORKING_CST.unlink(missing_ok=True)

    print(f"  Copying template -> {WORKING_CST}")
    shutil.copy2(TEMPLATE_CST, WORKING_CST)

    # Also copy the companion folder if it exists
    template_folder = TEMPLATE_CST.parent / (TEMPLATE_CST.stem)
    if template_folder.is_dir():
        shutil.copytree(template_folder, working_folder)

    # --- Step 3: Open CST, inject parameters, solve ---
    env = None
    project = None
    solve_status = "not_started"
    solve_duration = 0.0

    try:
        print("  Opening CST environment...")
        env = cstint.DesignEnvironment()
        project = env.open_project(str(WORKING_CST))
        m3d = project.model3d

        # Inject parameters
        print("  Injecting design parameters...")
        _inject_parameters(project, DESIGN)

        if skip_solve:
            print("  [SKIP] Solver skipped (--skip-solve)")
            solve_status = "skipped"
        else:
            # Rebuild geometry
            print("  Rebuilding geometry...")
            m3d.full_history_rebuild()

            # Run solver
            print("  Starting FD solver...")
            t0 = time.time()
            m3d.start_solver()

            while m3d.is_solver_running():
                elapsed = time.time() - t0
                if elapsed > SOLVER_TIMEOUT:
                    try:
                        m3d.abort_solver()
                    except Exception:
                        pass
                    solve_status = "timeout"
                    solve_duration = elapsed
                    break
                time.sleep(POLL_INTERVAL)
            else:
                solve_duration = time.time() - t0
                solve_status = "success"

            print(f"  Solver finished: {solve_status} ({solve_duration:.1f}s)")

        # Save and close project (must close before cst.results can read)
        project.save()
        project.close()
        project = None
        env.close()
        env = None
        print("  CST project saved and closed.")

    except Exception as exc:
        solve_status = "error"
        print(f"  [ERROR] CST pipeline failed: {exc}")
        import traceback
        traceback.print_exc()

    finally:
        if project is not None:
            try:
                project.close()
            except Exception:
                pass
        if env is not None:
            try:
                env.close()
            except Exception:
                pass

    # --- Export results via cst.results (project must be closed) ---
    exported = {}
    if solve_status in ("success", "skipped"):
        print("  Exporting results via cst.results...")
        export_subdir = EXPORTS_DIR / candidate_id
        exported = _export_results(str(WORKING_CST), export_subdir)
        print(f"  Exported {len(exported)} result(s): {list(exported.keys())}")

    # --- Step 4: Evaluate ---
    if solve_status not in ("success", "skipped"):
        _log_result(
            candidate_id, parent_id,
            999.0, False, 0.0, 0.0, 0.0, 0.0,
            solve_status, solve_duration, "crash",
            f"solver {solve_status}",
        )
        return {
            "status": "crash",
            "solve_status": solve_status,
            "candidate_id": candidate_id,
        }

    # Find the best result file to evaluate
    export_subdir = EXPORTS_DIR / candidate_id
    eval_result = None

    # Priority: Reflectance table (cleanest resonance dip),
    # then S-parameter reflection SZmax(2),Zmax(2)
    eval_candidates = [
        ("Reflectance.csv", "reflectance"),
        ("SZmax(2),Zmax(2).csv", "s11"),
    ]

    for fname, dtype in eval_candidates:
        csv_path = export_subdir / fname
        if csv_path.exists():
            try:
                eval_result = evaluate_candidate(
                    str(csv_path), target_freq_thz, data_type=dtype,
                )
                print(f"  Evaluated {fname}: score={eval_result['score']}, "
                      f"f_res={eval_result['f_res_thz']} THz, "
                      f"abs={eval_result['abs_at_res']}")
                break
            except Exception as exc:
                print(f"  [WARN] Could not evaluate {fname}: {exc}")

    if eval_result is None:
        # Fallback: try any CSV
        for fpath in sorted(export_subdir.glob("*.csv")):
            try:
                eval_result = evaluate_candidate(
                    str(fpath), target_freq_thz, data_type="s11"
                )
                print(f"  Evaluated {fpath.name}: score={eval_result['score']}")
                break
            except Exception:
                continue

    if eval_result is None:
        _log_result(
            candidate_id, parent_id,
            999.0, False, 0.0, 0.0, 0.0, 0.0,
            solve_status, solve_duration, "no_results",
            "no exportable S-parameters found",
        )
        return {
            "status": "no_results",
            "candidate_id": candidate_id,
        }

    # --- Step 5: Log ---
    result_status = "keep"  # agent decides keep/discard based on score
    _log_result(
        candidate_id, parent_id,
        eval_result["score"], eval_result["valid"],
        eval_result["f_res_thz"], eval_result["abs_at_res"],
        eval_result["freq_error"], eval_result["abs_penalty"],
        solve_status, solve_duration,
        result_status, note,
    )

    final = {
        "status": "success",
        "candidate_id": candidate_id,
        **eval_result,
        "solve_duration_s": solve_duration,
    }

    print(f"\n  Result: {json.dumps(final, indent=2)}")
    return final


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CST AutoResearch runner -- one experiment cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", type=float, default=DEFAULT_TARGET_FREQ_THZ,
                        help=f"Target frequency in THz (default {DEFAULT_TARGET_FREQ_THZ})")
    parser.add_argument("--candidate-id", type=str, default=None,
                        help="Explicit candidate ID (default: auto-increment)")
    parser.add_argument("--parent-id", type=str, default="root",
                        help="Parent candidate ID (default: root)")
    parser.add_argument("--note", type=str, default="",
                        help="Freeform note for the results log")
    parser.add_argument("--skip-solve", action="store_true",
                        help="Skip CST simulation (use cached results)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate design only, do not open CST")
    args = parser.parse_args()

    result = run_pipeline(
        target_freq_thz=args.target,
        candidate_id=args.candidate_id,
        parent_id=args.parent_id,
        note=args.note,
        skip_solve=args.skip_solve,
        dry_run=args.dry_run,
    )

    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
