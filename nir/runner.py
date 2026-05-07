"""nir/runner.py -- standalone build-and-run CST harness for the disk MIM (hypothesis A).

Mirrors the mid-IR pattern in run_midIR_v3.py: copies templates/base_project.cst
to a working file, deletes the default PEC box, then injects units / freq /
boundary / materials / geometry / Floquet ports / solver / mesh as separate
history steps. Solver = HF Time Domain with PBA mesh (memory-efficient).

Bypasses the project-root runner.py (which is THz/SRR-specific).

Usage:
    # one-shot run with the current nir/design_A.py values
    python -m nir.runner

    # programmatic from agent.py:
    from nir.runner import run_pipeline
    result = run_pipeline(target_freq_thz=193.41, iter_dir=Path("runs/.../iteration_03"))
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
# CST library setup (must come BEFORE cst imports)
# ---------------------------------------------------------------------------
CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

# Make this module importable both as `nir.runner` and as a script
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cst.interface as cstint  # noqa: E402
import numpy as np              # noqa: E402

from nir.materials import (  # noqa: E402
    build_nir_materials_vba,
    build_nir_materials_vba_constant_only,
    build_nir_materials_vba_with_cr,
)

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
TEMPLATE_CST = PROJECT_ROOT / "templates" / "base_project.cst"


# ---------------------------------------------------------------------------
# Hypothesis dispatch -- which design / constraints / geometry / materials
# / working-file naming to use.
# ---------------------------------------------------------------------------

def _load_hypothesis(name: str):
    """Return a dict of hypothesis-specific callables and constants."""
    name = name.upper()
    if name == "A":
        from nir.design_A import DESIGN
        from nir.constraints_A import validate_design
        from nir.geometry_disk import build_disk_geometry_vba as build_geom
        return {
            "name": "A",
            "long_name": "disk MIM",
            "design": dict(DESIGN),
            "validate": validate_design,
            "build_geometry": build_geom,
            "build_materials": build_nir_materials_vba_constant_only,
            "working_basename": "working_A",
            "default_results_tsv": HERE / "results_A.tsv",
            "default_working_dir": HERE / "working_default_A",
        }
    elif name == "B":
        from nir.design_B import DESIGN
        from nir.constraints_B import validate_design
        from nir.geometry_ellipse import build_ellipse_geometry_vba as build_geom
        return {
            "name": "B",
            "long_name": "elliptical-disk MIM",
            "design": dict(DESIGN),
            "validate": validate_design,
            "build_geometry": build_geom,
            "build_materials": build_nir_materials_vba_constant_only,
            "working_basename": "working_B",
            "default_results_tsv": HERE / "results_B.tsv",
            "default_working_dir": HERE / "working_default_B",
        }
    elif name == "C":
        from nir.design_C import DESIGN
        from nir.constraints_C import validate_design
        from nir.geometry_planar import build_planar_geometry_vba as build_geom
        return {
            "name": "C",
            "long_name": "planar Au/SiO2/Cr MIM",
            "design": dict(DESIGN),
            "validate": validate_design,
            "build_geometry": build_geom,
            "build_materials": build_nir_materials_vba_constant_only,
            "working_basename": "working_C",
            "default_results_tsv": HERE / "results_C.tsv",
            "default_working_dir": HERE / "working_default_C",
        }
    else:
        raise ValueError(f"Unknown hypothesis '{name}' (must be A, B, or C)")

# ---------------------------------------------------------------------------
# Target / solver settings (NIR band)
# ---------------------------------------------------------------------------
TARGET_FREQ_THZ = 193.41        # 1550 nm in THz
FREQ_MIN_THZ = 100.0            # 3000 nm
FREQ_MAX_THZ = 300.0            # 1000 nm
SOLVER_TIMEOUT_S = 1800.0       # 30 min hard cap
POLL_INTERVAL_S = 10.0


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# VBA assembly
# ---------------------------------------------------------------------------

def _build_full_vba(params: Dict[str, float],
                    hypothesis_cfg: Dict[str, Any],
                    freq_min: float = FREQ_MIN_THZ,
                    freq_max: float = FREQ_MAX_THZ,
                    quick: bool = False) -> Dict[str, str]:
    """Return a dict of named VBA blocks. Each is injected as a separate
    history step so a failure in one localizes cleanly."""

    vba_params = "\n".join(
        f'StoreDoubleParameter "{k}", {v}' for k, v in params.items()
    )

    vba_units = (
        'With Units\n'
        '  .Geometry "nm"\n'
        '  .Frequency "THz"\n'
        '  .Time "fs"\n'
        'End With'
    )

    vba_freq = (
        f'With Solver\n'
        f'  .FrequencyRange "{freq_min}", "{freq_max}"\n'
        f'End With'
    )

    vba_boundary = (
        'With Boundary\n'
        '  .Xmin "unit cell"\n'
        '  .Xmax "unit cell"\n'
        '  .Ymin "unit cell"\n'
        '  .Ymax "unit cell"\n'
        '  .Zmin "expanded open"\n'
        '  .Zmax "expanded open"\n'
        'End With'
    )

    vba_bg = (
        'With Background\n'
        '  .Type "Normal"\n'
        '  .Epsilon "1.0"\n'
        '  .Mu "1.0"\n'
        'End With'
    )

    vba_floquet = (
        'With FloquetPort\n'
        '  .Reset\n'
        '  .SetDialogTheta "0"\n'
        '  .SetDialogPhi "0"\n'
        '  .SetPolarizationIndependentOfScanAnglePhi "0", "False"\n'
        '  .SetSortCode "+beta/pw"\n'
        '  .SetCustomizedListFlag "False"\n'
        '  .Port "Zmax"\n'
        '  .SetNumberOfModesConsidered "2"\n'
        '  .SetDistanceToReferencePlane "0"\n'
        '  .SetUseCircularPolarization "False"\n'
        '  .Port "Zmin"\n'
        '  .SetNumberOfModesConsidered "2"\n'
        'End With'
    )

    # Hypothesis C is a uniform planar thin-film stack -- Frequency Domain
    # solver is better suited to high-Q FP cavity than Time Domain (which
    # gave zero absorption on smoke test). A and B keep TD (proven, fast).
    if hypothesis_cfg["name"] == "C":
        vba_solver = 'ChangeSolverType "HF Frequency Domain"'
        mesh_type = "Tetrahedral"
    else:
        vba_solver = 'ChangeSolverType "HF Time Domain"'
        mesh_type = "PBA"

    # In --quick mode, request a coarser cells-per-wavelength to roughly
    # halve the solve time. The standard CST default is 10; we use 5 in
    # quick mode. This is enough to verify geometry+VBA but too coarse for
    # converged peak position -- meant for smoke tests, not convergence.
    if quick:
        vba_mesh = (
            f'With Mesh\n'
            f'  .MeshType "{mesh_type}"\n'
            f'  .SetCreator "High Frequency"\n'
            f'End With\n'
            f'With MeshSettings\n'
            f'  .SetMeshType "Hex"\n'
            f'  .Set "StepsPerWaveNear", "5"\n'
            f'  .Set "StepsPerWaveFar", "5"\n'
            f'End With'
        )
    else:
        vba_mesh = (
            f'With Mesh\n'
            f'  .MeshType "{mesh_type}"\n'
            f'  .SetCreator "High Frequency"\n'
            f'End With'
        )

    # Constant-sigma materials only (build_materials selected per hypothesis).
    # The Drude VBA syntax in build_nir_materials_vba() (.DispModelEpsilon
    # "Drude") errors on this CST install (ActiveX 10091).
    return {
        "delete_default": 'Component.Delete "component1"',
        "params": vba_params,
        "units_freq_boundary_bg": "\n\n".join([vba_units, vba_freq, vba_boundary, vba_bg]),
        "materials": hypothesis_cfg["build_materials"](),
        "geometry": hypothesis_cfg["build_geometry"](params),
        "floquet": vba_floquet,
        "solver_type": vba_solver,
        "mesh": vba_mesh,
    }


# ---------------------------------------------------------------------------
# CST simulation core
# ---------------------------------------------------------------------------

def _run_cst_simulation(params: Dict[str, float],
                        iter_dir: Path,
                        hypothesis_cfg: Dict[str, Any],
                        quick: bool = False) -> Dict[str, Any]:
    """Build the project, solve, export. Returns a dict; valid=False on errors."""
    iter_dir.mkdir(parents=True, exist_ok=True)

    basename = hypothesis_cfg["working_basename"]
    working_cst = iter_dir / f"{basename}.cst"
    working_folder = iter_dir / basename

    if working_cst.exists():
        working_cst.unlink()
    if working_folder.exists():
        shutil.rmtree(working_folder, ignore_errors=True)
        time.sleep(1)

    log(f"  Copying template -> {working_cst}")
    shutil.copy2(TEMPLATE_CST, working_cst)

    vba_blocks = _build_full_vba(params, hypothesis_cfg, quick=quick)
    history_tag = f"NIR_{hypothesis_cfg['name']}"
    if quick:
        log("  [QUICK MODE] coarser mesh, faster solve, lower accuracy")

    steps = [
        ("Step 0: Delete default PEC box", vba_blocks["delete_default"]),
        ("Step 1: Parameters", vba_blocks["params"]),
        ("Step 2: Units + Freq + Boundary + Background",
         vba_blocks["units_freq_boundary_bg"]),
        ("Step 3: Materials", vba_blocks["materials"]),
        ("Step 4: Geometry", vba_blocks["geometry"]),
        ("Step 5: Floquet ports", vba_blocks["floquet"]),
        ("Step 6: Solver type (Time Domain)", vba_blocks["solver_type"]),
        ("Step 7: Mesh (PBA)", vba_blocks["mesh"]),
    ]

    env = None
    project = None
    elapsed = 0.0

    try:
        log("  Opening CST environment...")
        env = cstint.DesignEnvironment()
        project = env.open_project(str(working_cst.resolve()))
        m3d = project.model3d

        for step_name, vba in steps:
            log(f"    {step_name}...")
            try:
                m3d.add_to_history(f"{history_tag}: {step_name}", vba)
                log("      OK")
            except Exception as exc:
                log(f"      [ERROR] {step_name}: {exc}")
                return {
                    "valid": False,
                    "error": f"VBA history step failed [{step_name}]: {exc}",
                    "solve_duration_s": 0.0,
                }

        log("  All VBA injected. Starting solver...")
        t0 = time.time()
        try:
            m3d.start_solver()
            while m3d.is_solver_running():
                elapsed = time.time() - t0
                if elapsed > SOLVER_TIMEOUT_S:
                    log(f"  [TIMEOUT] solver still running after {elapsed:.0f}s")
                    try:
                        m3d.abort_solver()
                    except Exception:
                        pass
                    return {
                        "valid": False,
                        "error": f"solver timeout after {elapsed:.0f}s",
                        "solve_duration_s": elapsed,
                    }
                time.sleep(POLL_INTERVAL_S)
            elapsed = time.time() - t0
            log(f"  Solver completed in {elapsed:.1f}s")
        except Exception as exc:
            elapsed = time.time() - t0
            log(f"  [ERROR] solver: {exc}")
            return {
                "valid": False,
                "error": f"solver: {exc}",
                "solve_duration_s": elapsed,
            }

    finally:
        # Always try to save + close even on errors so the project file is inspectable
        if project is not None:
            try:
                project.save()
            except Exception:
                pass
            try:
                project.close()
            except Exception:
                pass
        if env is not None:
            try:
                env.close()
            except Exception:
                pass

    # ---- Result export (must be after project.close) ----
    try:
        export = _export_spectrum(working_cst, iter_dir)
        if not export.get("valid"):
            return {**export, "solve_duration_s": elapsed}

        # ---- Score ----
        from nir.evaluator import detect_resonance, score_design  # local import (cycle safety)
        f_peak, abs_peak, fwhm_thz = detect_resonance(
            export["freq"], export["absorptance"],
            freq_min=FREQ_MIN_THZ, freq_max=FREQ_MAX_THZ,
        )
        score_formula = hypothesis_cfg.get("score_formula", "legacy")
        target_fwhm_thz = hypothesis_cfg.get("target_fwhm_thz")
        score = score_design(
            f_peak, abs_peak,
            target_thz=hypothesis_cfg.get("target_thz", TARGET_FREQ_THZ),
            fwhm_thz=fwhm_thz,
            target_fwhm_thz=target_fwhm_thz,
            formula=score_formula,
        )

        return {
            "valid": True,
            "f_peak_thz": float(f_peak),
            "abs_at_peak": float(abs_peak),
            "fwhm_thz": float(fwhm_thz),
            "score": float(score),
            "score_formula": score_formula,
            "freq_error": float(abs(f_peak - hypothesis_cfg.get("target_thz", TARGET_FREQ_THZ))),
            "abs_penalty": float(max(0.0, 0.90 - abs_peak)),
            "solve_duration_s": elapsed,
            "absorptance_csv": export["absorptance_csv"],
            "s11_csv": export["s11_csv"],
        }
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return {
            "valid": False,
            "error": f"export/score: {exc}",
            "solve_duration_s": elapsed,
        }


def _export_spectrum(working_cst: Path, iter_dir: Path) -> Dict[str, Any]:
    """Open the closed CST project via cst.results, export S-params + Absorptance.

    Uses the helpers in nir.cst_helpers which wrap the two silent footguns
    in cst.results: relative-path index corruption, and run_id=0 default
    after parameter injection.
    """
    # Small delay so CST finishes flushing its result database after env.close()
    time.sleep(2.0)

    log("  Exporting results...")
    from nir.cst_helpers import (
        open_results, get_result_with_data, find_reflection_sparams,
    )
    proj3d, all_run_ids = open_results(working_cst)
    tree_items = proj3d.get_tree_items()
    log(f"    Available run_ids: {all_run_ids}")

    sep = "\\"
    s_params = [
        item for item in tree_items
        if (item.split(sep)[:2] == ["1D Results", "S-Parameters"])
    ]
    if not s_params:
        return {"valid": False, "error": "no S-parameters in tree"}

    reflection_items = set(find_reflection_sparams(tree_items, sep=sep))
    log(f"    Found S-params: {[s.split(sep)[-1] for s in s_params]}")
    log(f"    Reflection diag candidates: "
        f"{[s.split(sep)[-1] for s in reflection_items]}")

    s11_path = None
    s11_freq = None
    s11_mag_sq = None

    for sp in s_params:
        label = sp.split(sep)[-1]
        try:
            result, used_rid = get_result_with_data(proj3d, sp, all_run_ids)
            xdata = np.array(result.get_xdata())
            ydata = result.get_ydata()
            mag_sq = np.array([abs(y) ** 2 for y in ydata])

            fname = (label.replace(",", "_")
                          .replace("(", "")
                          .replace(")", "")
                          .replace(" ", "_"))
            out_path = iter_dir / f"{fname}.csv"
            with open(out_path, "w", newline="") as f:
                f.write(f"# frequency_THz\t|{label}|^2\n")
                for fr, val in zip(xdata, mag_sq):
                    f.write(f"{fr}\t{val}\n")

            # Pick the FIRST diagonal reflection that exports successfully.
            # (Prefer Zmax(1),Zmax(1) when present; FD solver often only
            # has Zmax(2),Zmax(2) -- both work as reflection coefficients
            # for Absorptance = 1 - |S|^2 over a ground plane.)
            if sp in reflection_items and s11_path is None:
                s11_path = out_path
                s11_freq = xdata
                s11_mag_sq = mag_sq

            log(f"    exported {label} (run_id={used_rid}): {len(xdata)} pts, "
                f"{xdata[0]:.1f}-{xdata[-1]:.1f} THz")
        except Exception as exc:
            log(f"    [WARN] {label}: {exc}")

    if s11_path is None or s11_freq is None:
        return {"valid": False, "error": "could not identify S11 reflection in tree"}

    absorptance = 1.0 - s11_mag_sq
    abs_path = iter_dir / "Absorptance.csv"
    with open(abs_path, "w", newline="") as f:
        f.write("# frequency_THz\tAbsorptance\n")
        for fr, val in zip(s11_freq, absorptance):
            f.write(f"{fr}\t{val}\n")

    log(f"    Absorptance: {len(s11_freq)} pts, "
        f"min={absorptance.min():.3f}, max={absorptance.max():.3f}")

    return {
        "valid": True,
        "freq": s11_freq,
        "absorptance": absorptance,
        "absorptance_csv": str(abs_path),
        "s11_csv": str(s11_path),
    }


# ---------------------------------------------------------------------------
# Results TSV ledger
# ---------------------------------------------------------------------------

_RESULTS_HEADER = [
    "candidate_id", "parent_id", "timestamp",
    "score", "valid", "f_peak_thz", "abs_at_peak",
    "freq_error", "abs_penalty",
    "solve_duration_s", "status", "note",
]


def _init_results_tsv(path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(_RESULTS_HEADER)


def _next_candidate_id(results_tsv: Path) -> str:
    _init_results_tsv(results_tsv)
    with open(results_tsv, "r") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    max_id = 0
    for row in rows[1:]:
        try:
            max_id = max(max_id, int(row[0]))
        except (ValueError, IndexError):
            pass
    return f"{max_id + 1:04d}"


def _log_result(results_tsv: Path, candidate_id: str, parent_id: str,
                *, score: float, valid: bool,
                f_peak_thz: float = 0.0, abs_at_peak: float = 0.0,
                freq_error: float = 0.0, abs_penalty: float = 0.0,
                solve_duration_s: float = 0.0,
                status: str = "ok", note: str = "") -> None:
    _init_results_tsv(results_tsv)
    with open(results_tsv, "a", newline="") as f:
        csv.writer(f, delimiter="\t").writerow([
            candidate_id, parent_id,
            datetime.now().isoformat(timespec="seconds"),
            f"{score:.6f}" if valid else "999.000000",
            "true" if valid else "false",
            f"{f_peak_thz:.4f}" if valid else "NaN",
            f"{abs_at_peak:.4f}" if valid else "NaN",
            f"{freq_error:.4f}" if valid else "NaN",
            f"{abs_penalty:.4f}" if valid else "NaN",
            f"{solve_duration_s:.1f}",
            status, note[:200],
        ])


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(target_freq_thz: float = TARGET_FREQ_THZ,
                 candidate_id: Optional[str] = None,
                 parent_id: str = "root",
                 note: str = "",
                 iter_dir: Optional[Path] = None,
                 results_tsv: Optional[Path] = None,
                 design: Optional[Dict[str, float]] = None,
                 hypothesis: str = "A",
                 dry_run: bool = False,
                 quick: bool = False) -> Dict[str, Any]:
    """Full cycle for one candidate.

    Args:
        target_freq_thz: target peak frequency.
        candidate_id: 4-digit ID; auto-incremented if None.
        parent_id: id of the design we mutated from (for genealogy).
        note: short free-text note (truncated to 200 chars in TSV).
        iter_dir: where to put working_X.cst + Absorptance.csv etc.
                  Default: nir/working_default_<hypothesis>/.
        results_tsv: append-only ledger path. Default: nir/results_<hypothesis>.tsv.
        design: parameter dict; defaults to the live nir/design_<hypothesis>.py DESIGN.
        hypothesis: "A" (disk), "B" (elliptical disk), or "C" (planar MIM).
        dry_run: stop before opening CST (validation only).
    """
    cfg = _load_hypothesis(hypothesis)
    if iter_dir is None:
        iter_dir = cfg["default_working_dir"]
    if results_tsv is None:
        results_tsv = cfg["default_results_tsv"]
    if design is None:
        design = dict(cfg["design"])

    iter_dir = Path(iter_dir)
    results_tsv = Path(results_tsv)

    if candidate_id is None:
        candidate_id = _next_candidate_id(results_tsv)

    target_nm = 1e3 * 299.792458 / target_freq_thz  # c [nm/fs] / f [THz] = lambda [nm]
    log("\n" + "=" * 60)
    log(f"  NIR auto_cst (hypothesis {cfg['name']} = {cfg['long_name']})  --  Candidate {candidate_id}")
    log(f"  Target: {target_freq_thz:.3f} THz  ({target_nm:.1f} nm)")
    log(f"  Iter dir: {iter_dir}")
    log(f"  Parameters: {json.dumps(design, indent=2)}")
    log("=" * 60 + "\n")

    # --- Validate ---
    ok, reason = cfg["validate"](design)
    if not ok:
        log(f"  [INVALID] {reason}")
        _log_result(results_tsv, candidate_id, parent_id,
                    score=999.0, valid=False, status="invalid", note=reason)
        return {"status": "invalid", "reason": reason,
                "candidate_id": candidate_id, "valid": False}
    log("  [OK] Design passes constraints")

    if dry_run:
        log("  [DRY RUN] Stopping before CST.")
        return {"status": "dry_run", "candidate_id": candidate_id, "valid": True}

    # --- Template check ---
    if not TEMPLATE_CST.exists():
        msg = f"Template not found: {TEMPLATE_CST}"
        log(f"  [ERROR] {msg}")
        return {"status": "error", "message": msg, "valid": False,
                "candidate_id": candidate_id}

    # --- Run CST ---
    sim = _run_cst_simulation(design, iter_dir, cfg, quick=quick)

    if not sim.get("valid"):
        log(f"  [FAIL] {sim.get('error', 'unknown')}")
        _log_result(results_tsv, candidate_id, parent_id,
                    score=999.0, valid=False,
                    solve_duration_s=sim.get("solve_duration_s", 0.0),
                    status="error", note=sim.get("error", "unknown"))
        return {"status": "error", "valid": False,
                "candidate_id": candidate_id, **sim}

    # --- Log + persist ---
    _log_result(
        results_tsv, candidate_id, parent_id,
        score=sim["score"], valid=True,
        f_peak_thz=sim["f_peak_thz"], abs_at_peak=sim["abs_at_peak"],
        freq_error=sim["freq_error"], abs_penalty=sim["abs_penalty"],
        solve_duration_s=sim["solve_duration_s"],
        status="ok", note=note,
    )

    iter_record = {
        "candidate_id": candidate_id,
        "parent_id": parent_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "target_freq_thz": target_freq_thz,
        "design": design,
        "result": {k: v for k, v in sim.items() if k != "freq" and k != "absorptance"},
        "note": note,
    }
    with open(iter_dir / "iteration_record.json", "w") as f:
        json.dump(iter_record, f, indent=2)

    log(f"\n  [DONE] f_peak={sim['f_peak_thz']:.3f} THz "
        f"(target {target_freq_thz:.3f}), "
        f"abs_peak={sim['abs_at_peak']:.3f}, "
        f"score={sim['score']:.6f}\n")

    return {"status": "ok", "valid": True, "candidate_id": candidate_id, **sim}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="NIR single CST run (hypothesis A/B/C)")
    parser.add_argument("--hypothesis", type=str, default="A", choices=["A", "B", "C"],
                        help="Which hypothesis to run (default A)")
    parser.add_argument("--target", type=float, default=TARGET_FREQ_THZ,
                        help=f"Target peak frequency in THz (default {TARGET_FREQ_THZ})")
    parser.add_argument("--iter-dir", type=str, default=None,
                        help="Output dir for this iteration")
    parser.add_argument("--results-tsv", type=str, default=None,
                        help="Results ledger path")
    parser.add_argument("--candidate-id", type=str, default=None,
                        help="Explicit 4-digit ID (default auto)")
    parser.add_argument("--parent-id", type=str, default="root",
                        help="Parent candidate ID for genealogy")
    parser.add_argument("--note", type=str, default="",
                        help="Short note saved to results.tsv")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate only, do not open CST")
    parser.add_argument("--quick", action="store_true",
                        help="Smoke-test mode: coarser mesh (5 cells/lambda) for "
                             "~2x faster solve. Verifies geometry + VBA, NOT "
                             "accurate enough for convergence -- use as a "
                             "pre-flight check before launching the full agent.")
    args = parser.parse_args()

    iter_dir = Path(args.iter_dir) if args.iter_dir else None
    results_tsv = Path(args.results_tsv) if args.results_tsv else None

    result = run_pipeline(
        target_freq_thz=args.target,
        candidate_id=args.candidate_id,
        parent_id=args.parent_id,
        note=args.note,
        iter_dir=iter_dir,
        results_tsv=results_tsv,
        hypothesis=args.hypothesis,
        dry_run=args.dry_run,
        quick=args.quick,
    )

    # Emit a JSON line at the end so the agent subprocess can parse it
    print("RESULT_JSON: " + json.dumps({
        k: v for k, v in result.items() if k not in ("freq", "absorptance")
    }))


if __name__ == "__main__":
    main()
