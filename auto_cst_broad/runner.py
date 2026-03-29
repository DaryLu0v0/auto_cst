"""runner.py -- fixed experiment harness for broadband Ge CWC absorber.

DO NOT MODIFY this file during agent runs.

Opens the CST project in-place, injects design parameters via VBA,
rebuilds geometry, runs the HF Frequency Domain solver, exports
absorptance spectrum, evaluates broadband score, and logs results.

Usage:
    python runner.py                     # run with design.py defaults
    python runner.py --parent-id 0001    # set parent for lineage
    python runner.py --skip-solve        # skip solver (use cached results)
    python runner.py --dry-run           # validate only, no CST
"""
from __future__ import annotations

import argparse
import csv
import json
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
PROJECT_CST = Path(r"D:\Dary\agent\broad\Agent_fine\Ge_Abs_CWC_5x5_run10 (1).cst")
EXPORTS_DIR = HERE / "exports"
RESULTS_TSV = HERE / "results.tsv"
DESIGN_PY = HERE / "design.py"

# Solver settings
POLL_INTERVAL = 5.0       # seconds between solver status checks
SOLVER_TIMEOUT = 7200.0   # 2 hours max (optical FD solver is slow)


# ---------------------------------------------------------------------------
# Parameter injection via VBA
# ---------------------------------------------------------------------------

def _build_parameter_vba(params: dict) -> str:
    """Generate VBA code to update CST project parameters.

    Uses StoreDoubleParameter which updates the named parameter
    in the CST parameter list.
    """
    lines = []
    for name, value in params.items():
        # Skip non-geometric parameters
        if name in ("theta", "phi"):
            continue
        lines.append(f'StoreDoubleParameter "{name}", {value}')
    return "\n".join(lines)


def _inject_parameters(project, params: dict) -> None:
    """Push design parameters into the CST project.

    Uses the direct COM API StoreDoubleParameter instead of add_to_history
    to avoid history accumulation which breaks the solver after rebuild.
    """
    m3d = project.model3d
    for name, value in params.items():
        if name in ("theta", "phi"):
            continue
        m3d.StoreDoubleParameter(name, float(value))


# ---------------------------------------------------------------------------
# Result export via cst.results
# ---------------------------------------------------------------------------

def _export_results(project_path: str, export_dir: Path) -> Dict[str, str]:
    """Extract absorptance and other results via cst.results.

    Must be called AFTER the project is closed by cst.interface.
    Returns dict mapping label -> file_path.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    exported = {}

    try:
        proj_res = cstres.ProjectFile(str(project_path), allow_interactive=True)
        proj3d = proj_res.get_3d()
        tree_items = proj3d.get_tree_items()

        sep = "\\"

        import numpy as np

        # --- S-Parameters (complex) ---
        s_param_items = [
            item for item in tree_items
            if item.startswith("1D Results" + sep + "S-Parameters" + sep + "S")
        ]

        for item_path in s_param_items:
            try:
                result = proj3d.get_result_item(item_path)
                xdata = np.array(result.get_xdata())
                ydata = result.get_ydata()
                mag_sq = np.array([abs(y) ** 2 for y in ydata])

                label = item_path.split(sep)[-1]
                # CST S-parameters already return frequency in THz
                xdata_thz = xdata
                out_path = export_dir / f"{label}.csv"

                with open(out_path, "w", newline="") as f:
                    f.write("# frequency_THz\t|S|^2\n")
                    for freq, val in zip(xdata_thz, mag_sq):
                        f.write(f"{freq}\t{val}\n")

                exported[label] = str(out_path)
                print(f"    exported {label}: {len(xdata)} pts")

            except Exception as exc:
                print(f"    [WARN] {item_path}: {exc}")

        # --- Tables: Absorptance, Reflectance, Transmittance ---
        # CST stores these under:
        #   Tables\1D Results\Reflectance-Transmittance-Absorbance\A_Zmax(1)
        #   Tables\1D Results\Reflectance-Transmittance-Absorbance\R_Zmax(1),Zmax(1)
        #   etc.
        rta_prefix = "Tables" + sep + "1D Results" + sep + "Reflectance-Transmittance-Absorbance"
        rta_items = [item for item in tree_items if item.startswith(rta_prefix)]
        if rta_items:
            print(f"    Found RTA items: {[it.split(sep)[-1] for it in rta_items]}")

        # Look for A_Zmax(1) = Absorptance
        for item_path in rta_items:
            label = item_path.split(sep)[-1]
            try:
                result = proj3d.get_result_item(item_path)
                xdata = np.array(result.get_xdata())
                ydata = result.get_ydata()
                vals = np.array([abs(y) for y in ydata])

                # CST RTA tables return wavelength in nm (not frequency).
                # Convert nm -> THz:  f_THz = c / lambda = 299792.458 / lambda_nm
                # We use 300000 as a convenient approximation.
                xdata_thz = 300000.0 / xdata

                out_path = export_dir / f"{label}.csv"
                with open(out_path, "w", newline="") as f:
                    f.write(f"# frequency_THz\t{label}\n")
                    for freq, val in zip(xdata_thz, vals):
                        f.write(f"{freq}\t{val}\n")

                exported[label] = str(out_path)
                print(f"    exported {label}: {len(xdata)} pts")

                # Map A_Zmax(1) -> Absorptance so the evaluator finds it
                if label.startswith("A_Zmax"):
                    abs_path = export_dir / "Absorptance.csv"
                    with open(abs_path, "w", newline="") as f:
                        f.write("# frequency_THz\tAbsorptance\n")
                        for freq, val in zip(xdata_thz, vals):
                            f.write(f"{freq}\t{val}\n")
                    exported["Absorptance"] = str(abs_path)
                    print(f"    -> copied as Absorptance.csv (mean={np.mean(vals):.4f})")

            except Exception as exc:
                print(f"    [WARN] {label}: {exc}")

        # Legacy fallback: try old-style Tables\1D Results\Absorptance
        if "Absorptance" not in exported:
            for tname in ["Absorptance", "Reflectance", "Transmittance"]:
                tpath = "Tables" + sep + "1D Results" + sep + tname
                if tpath not in tree_items:
                    continue
                try:
                    result = proj3d.get_result_item(tpath)
                    xdata = np.array(result.get_xdata())
                    ydata = result.get_ydata()
                    vals = np.array([abs(y) for y in ydata])

                    # CST RTA tables return wavelength in nm; convert to THz
                    xdata_thz = 300000.0 / xdata
                    out_path = export_dir / f"{tname}.csv"
                    with open(out_path, "w", newline="") as f:
                        f.write(f"# frequency_THz\t{tname}\n")
                        for freq, val in zip(xdata_thz, vals):
                            f.write(f"{freq}\t{val}\n")

                    exported[tname] = str(out_path)
                    print(f"    exported {tname}: {len(xdata)} pts")

                except Exception as exc:
                    print(f"    [WARN] {tname}: {exc}")

        # --- Compute Absorptance from Floquet S-parameters ---
        # If CST did not produce an Absorptance table, compute it from
        # the Floquet mode S-parameters:
        #   Absorption = 1 - sum(|S_reflected|^2) - sum(|S_transmitted|^2)
        #
        # Floquet naming convention:
        #   SZmax(m),Zmax(n) = reflected mode m from excitation mode n
        #   SZmin(m),Zmax(n) = transmitted mode m from excitation mode n
        # We excite Zmax(1), so we sum over all m for both ports.
        if "Absorptance" not in exported and s_param_items:
            print("    Computing Absorptance from Floquet S-parameters...")
            # Collect all |S|^2 arrays keyed by label
            s_data = {}
            ref_freq = None
            for item_path in s_param_items:
                try:
                    result = proj3d.get_result_item(item_path)
                    xdata = np.array(result.get_xdata())
                    ydata = result.get_ydata()
                    mag_sq = np.array([abs(y) ** 2 for y in ydata])
                    label = item_path.split(sep)[-1]
                    s_data[label] = mag_sq
                    if ref_freq is None:
                        ref_freq = xdata
                except Exception:
                    pass

            if ref_freq is not None and s_data:
                # Sum all |S|^2 for modes excited by Zmax(1)
                total_s_sq = np.zeros_like(ref_freq)
                for label, mag_sq in s_data.items():
                    # Only include S-params excited by Zmax(1)
                    if "Zmax(1)" in label and label.startswith("S"):
                        total_s_sq += mag_sq
                        print(f"      summing {label}: max|S|^2={np.max(mag_sq):.6f}")

                absorptance = 1.0 - total_s_sq
                # Clamp to [0, 1]
                absorptance = np.clip(absorptance, 0.0, 1.0)

                # CST S-parameters already return frequency in THz
                ref_freq_thz = ref_freq
                out_path = export_dir / "Absorptance.csv"
                with open(out_path, "w", newline="") as f:
                    f.write("# frequency_THz\tAbsorptance\n")
                    for freq, val in zip(ref_freq_thz, absorptance):
                        f.write(f"{freq}\t{val}\n")

                exported["Absorptance"] = str(out_path)
                print(f"    exported Absorptance (computed): {len(ref_freq)} pts")
                print(f"    mean Abs in full range: {np.mean(absorptance):.4f}")

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
                "score", "valid", "mean_abs", "min_abs",
                "freq_at_min_thz", "band_coverage_90",
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
    mean_abs: float,
    min_abs: float,
    freq_at_min: float,
    band_coverage_90: float,
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
            f"{mean_abs:.4f}" if valid else "NaN",
            f"{min_abs:.4f}" if valid else "NaN",
            f"{freq_at_min:.4f}" if valid else "NaN",
            f"{band_coverage_90:.4f}" if valid else "NaN",
            solve_status,
            f"{solve_duration:.1f}",
            status, note,
        ])


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    candidate_id: Optional[str] = None,
    parent_id: str = "root",
    note: str = "",
    skip_solve: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Execute one full experiment cycle.

    1. Load design.py
    2. Validate constraints
    3. Open CST project in-place
    4. Inject parameters
    5. Rebuild + solve
    6. Export absorptance
    7. Evaluate broadband score
    8. Log to results.tsv
    """
    from design import DESIGN
    from constraints import validate_design
    from evaluator import evaluate_candidate

    # --- Assign candidate ID ---
    _init_results_tsv()
    if candidate_id is None:
        candidate_id = _next_candidate_id()

    # Show compact summary (75 params is too verbose for full dump)
    n_params = len(DESIGN)
    print(f"\n{'='*60}")
    print(f"  Broadband Absorber -- Candidate {candidate_id}")
    print(f"  Band: 14-22 um (13.64-21.43 THz)")
    print(f"  Parameters: {n_params} tunable")
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

    # --- Step 2: Open CST project in-place ---
    if not PROJECT_CST.exists():
        msg = f"CST project not found: {PROJECT_CST}"
        print(f"  [ERROR] {msg}")
        return {"status": "error", "message": msg}

    env = None
    project = None
    solve_status = "not_started"
    solve_duration = 0.0

    try:
        print("  Opening CST environment...")
        env = cstint.DesignEnvironment()
        project = env.open_project(str(PROJECT_CST))
        m3d = project.model3d

        # Inject parameters
        print(f"  Injecting {n_params} design parameters...")
        _inject_parameters(project, DESIGN)

        if skip_solve:
            print("  [SKIP] Solver skipped (--skip-solve)")
            solve_status = "skipped"
        else:
            # Rebuild geometry with updated parameters.
            # NOTE: Using Rebuild() instead of full_history_rebuild().
            # full_history_rebuild() causes "Simulation could not be
            # started. Unknown error." because it replays the full
            # construction history which invalidates the solver setup.
            # Rebuild() updates the geometry from changed parameters
            # without replaying history.
            print("  Rebuilding geometry...")
            m3d.Rebuild()

            # Run solver
            print("  Starting HF Frequency Domain solver...")
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
        exported = _export_results(str(PROJECT_CST), export_subdir)
        print(f"  Exported {len(exported)} result(s): {list(exported.keys())}")

    # --- Step 3: Evaluate ---
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

    # Find Absorptance CSV
    export_subdir = EXPORTS_DIR / candidate_id
    eval_result = None

    absorptance_csv = export_subdir / "Absorptance.csv"
    if absorptance_csv.exists():
        try:
            eval_result = evaluate_candidate(str(absorptance_csv))
            print(f"  Evaluated Absorptance.csv: score={eval_result['score']}, "
                  f"mean_abs={eval_result['mean_abs']}, "
                  f"min_abs={eval_result['min_abs']}")
        except Exception as exc:
            print(f"  [WARN] Could not evaluate Absorptance.csv: {exc}")

    if eval_result is None:
        # Fallback: try any CSV
        for fpath in sorted(export_subdir.glob("*.csv")):
            try:
                eval_result = evaluate_candidate(str(fpath))
                print(f"  Evaluated {fpath.name}: score={eval_result['score']}")
                break
            except Exception:
                continue

    if eval_result is None:
        _log_result(
            candidate_id, parent_id,
            999.0, False, 0.0, 0.0, 0.0, 0.0,
            solve_status, solve_duration, "no_results",
            "no Absorptance data found",
        )
        return {
            "status": "no_results",
            "candidate_id": candidate_id,
        }

    # --- Step 4: Log ---
    _log_result(
        candidate_id, parent_id,
        eval_result["score"], eval_result["valid"],
        eval_result["mean_abs"], eval_result["min_abs"],
        eval_result["freq_at_min_thz"], eval_result["band_coverage_90"],
        solve_status, solve_duration,
        "keep", note,
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
        description="Broadband absorber runner -- one experiment cycle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
        candidate_id=args.candidate_id,
        parent_id=args.parent_id,
        note=args.note,
        skip_solve=args.skip_solve,
        dry_run=args.dry_run,
    )

    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
