"""Build and run the Schurig 2006 ELC unit cell on FR4+Cu PCB, at 11 GHz.

================================================================================
THIS FILE IS A TEMPLATE / EXAMPLE -- NOT A GENERAL PIPELINE.
================================================================================

What's general (reusable across hypotheses):
  - nir/cst_helpers.py: HistoryBuilder, save_project_at, verify_*_exists,
    assert_spectrum_nontrivial, open_results, get_result_with_data,
    find_reflection_sparams, get_messages_safe. Use these as-is for any
    new CST build.
  - The pattern of 3 files per hypothesis under nir/:
        design_<id>.py        -- DESIGN dict (numeric values + units)
        constraints_<id>.py   -- validate_design() + PARAM_BOUNDS
        geometry_<id>.py      -- BRICK_SPEC + build_geometry_vba +
                                 expected_solid_names + render_top_view
  - The docs in nir/VBA_COOKBOOK.md and the feedback_cst_2026_vba memory.

What's hypothesis-specific in THIS file (you must adapt for a new hypothesis):
  - Materials block (VBA_FR4_MATERIAL).  Different physics regimes need
    different materials -- microwave PCB uses FR4+Cu+PEC, NIR uses
    SiO2+Au_lossy+Ag_lossy, mid-IR uses Ge+Si3N4+Ti, etc.
  - Boundary conditions (VBA_BOUNDARY).  Periodic structures use
    "unit cell" on X/Y + "expanded open" on Z; isolated antennas use
    "expanded open" everywhere; waveguide simulators use PEC/PMC walls.
  - Port type (VBA_PORTS).  FloquetPort for periodic + plane-wave incidence;
    Waveguide port for closed cavity; Discrete port for antenna feed.
  - Solver + sweep (VBA_FREQ_RANGE, ChangeSolverType in VBA_SOLVER_*).
    FD Frequency-Domain for narrowband resonances, TD Time-Domain for
    broadband sweeps, Eigenmode for closed cavities, etc.
  - Frequency band (F_MIN_GHZ, F_MAX_GHZ, F_TARGET_GHZ) and target metric
    (target.peak_ghz, target.type) in resonance_summary.

To build a CST simulation for a NEW hypothesis (NOT a new geometry sample
of the SAME hypothesis -- that just changes the DESIGN dict values):
  1. Copy this file to build_<new_id>.py.
  2. Write nir/design_<new_id>.py, nir/constraints_<new_id>.py,
     nir/geometry_<new_id>.py (look at the ELC versions as references).
  3. Edit the materials / boundary / ports / solver / freq band in the
     copy to match the new physics regime.
  4. Update the imports and HistoryBuilder.add(...) calls to reference
     the new hypothesis module.

The Tier-1 helpers in nir/cst_helpers.py handle ALL the CST 2026 VBA
gotchas (silent failures, run_id, FloquetPort naming, SaveAs lock, etc.)
-- the per-hypothesis adaptation is purely the physics-and-topology
choices listed above.

================================================================================

History of canonical-pattern enforcement (v6 onward, against
cst_python/examples/patch_antenna_workflow.py):

  - env.new_mws() for an empty project (no template pollution)
  - save_project_at() (Mode 3 SaveAs, not history) to control the output path
  - Units.SetUnit "Length"/"Frequency"/"Time" (canonical VBA form -- the
    .Geometry/.Frequency/.Time shorthands are Python-only proxies)
  - All geometry uses the default Component "component1" -- no custom components
  - Material "PEC" is a CST 2026 built-in -- no Cu material to define
  - Material VBA: .TanD + .TanDGiven + .TanDModel (NOT .Tandd, which raises 10091)
  - m3d.FDSolver.Start() is the Mode 2 direct call -- blocks until done
  - cst_helpers.open_results() handles run_id and FloquetPort tree-name footguns
  - HistoryBuilder verifies side effects after each VBA step (catches silent
    failures specifically, with the offending step labeled)
  - render_top_view() pre-flight render catches wrong-topology bugs in 1 sec

Outputs (under <run_dir>/):
  preflight_render_v<N>.png         pre-flight matplotlib top-view
  elc_11ghz_v<N>.cst                CST project
  s_params_complex.csv              freq_GHz, Re(S11), Im(S11), Re(S21), Im(S21)
  s_params_mag_sq.csv               freq_GHz, |S11|^2, |S21|^2
  resonance_summary.json            detected peak + in-target-band verdict
  build_log.txt                     per-step VBA injection log
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# --- Path setup ---
PROJECT_ROOT = Path("D:/Claude/auto_cst")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# CST Python libraries
CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

import cst.interface as cstint  # noqa: E402
import cst.results as cstres    # noqa: E402

from nir.design_ELC import DESIGN  # noqa: E402 -- values in nm
from nir.constraints_ELC import validate_design  # noqa: E402
from nir.geometry_elc import (  # noqa: E402
    expected_solid_names,
    render_top_view,
)
from nir.cst_helpers import (  # noqa: E402
    HistoryBuilder,
    assert_spectrum_nontrivial,
    find_reflection_sparams,
    get_result_with_data,
    open_results,
    save_project_at,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CST geometry unit: mm (matches CST default + cst_python/examples/patch_antenna).
# We convert from the nm convention used in design_ELC.py -> mm at injection.
NM_PER_MM = 1_000_000.0

# Frequency band. After the v8 sweep located the original geometry's resonance
# at 19.418 GHz and we one-shot-scaled the geometry by 1.7653x to bring it to
# 11 GHz, we narrow the sweep to 6-16 GHz for higher resolution near the
# expected target. Still wide enough to absorb any scaling imperfection.
F_MIN_GHZ = 6.0
F_MAX_GHZ = 16.0
F_TARGET_GHZ = 11.0
TARGET_TOL_FRAC = 0.10   # +/-10% acceptable window

# FR4 (Schurig 2006 fitted value: eps' = 3.75, eps'' = 0.084).
FR4_EPS_REAL = 3.75
FR4_TAND = 0.084 / 3.75   # = 0.0224

# Vacuum extent above/below the substrate (mm). expanded-open auto-extends
# but we add explicit pads to make the port placement deterministic.
AIR_EXTENT_MM = 10.0   # = 10 mm. lambda_0 at 11 GHz is 27.25 mm.

SOLVER_TIMEOUT_S = 3600.0   # 1 hour hard cap on the solver poll loop


# ---------------------------------------------------------------------------
# VBA fragments -- all using the canonical Mode 1 syntax verified against
# cst_python/examples/patch_antenna_workflow.py (the only known-good end-to-end
# CST 2026 example in this codebase).
# ---------------------------------------------------------------------------

VBA_UNITS = """\
With Units
    .SetUnit "Length", "mm"
    .SetUnit "Frequency", "GHz"
    .SetUnit "Time", "ns"
End With
"""


def build_param_vba(design_nm: dict, air_extent_mm: float) -> str:
    """StoreParameter calls in MM units (= design_nm/1e6).

    Uses StoreParameter "name", "value" syntax (string value, parens-free)
    per the patch_antenna example.
    """
    lines = []
    for k, v_nm in design_nm.items():
        v_mm = v_nm / NM_PER_MM
        lines.append(f'StoreParameter "{k}", "{v_mm:.9f}"')
    lines.append(f'StoreParameter "air_extent", "{air_extent_mm}"')
    return "\n".join(lines)


VBA_FREQ_RANGE = f'Solver.FrequencyRange "{F_MIN_GHZ}", "{F_MAX_GHZ}"\n'


# Unit cell BC on X/Y (periodic), expanded-open on Z (vacuum above + below).
# This is the canonical periodic-metamaterial setup that pairs with FloquetPort.
VBA_BOUNDARY = """\
With Boundary
    .Xmin "unit cell"
    .Xmax "unit cell"
    .Ymin "unit cell"
    .Ymax "unit cell"
    .Zmin "expanded open"
    .Zmax "expanded open"
End With
"""


VBA_BACKGROUND = """\
With Background
    .Type "Normal"
    .Epsilon "1.0"
    .Mu "1.0"
End With
"""


# FR4 substrate material. The cookbook-verbose form -- the patch antenna's
# 5-field form (which uses .Tandd) fails with (10091) "no such property" in
# this CST 2026 install. .TanD (single d, capital D) + .TanDGiven + .TanDModel
# is the form verified in nir/VBA_COOKBOOK.md and used successfully in the
# midIR pipeline.
VBA_FR4_MATERIAL = f"""\
With Material
    .Reset
    .Name "FR4"
    .Folder ""
    .FrqType "all"
    .Type "Normal"
    .Epsilon "{FR4_EPS_REAL}"
    .Mu "1"
    .Kappa "0"
    .TanD "{FR4_TAND}"
    .TanDGiven "True"
    .TanDModel "ConstTanD"
    .Colour "0.0", "0.6", "0.1"
    .Create
End With
"""


# Geometry VBA emitter lives in nir/geometry_elc.py (single source of truth
# for both VBA emission AND the pre-flight matplotlib render). Import it here.
from nir.geometry_elc import build_elc_geometry_vba as _build_elc_geometry_vba  # noqa: E402

def build_elc_geometry_vba_simple(design_nm: dict) -> str:
    """Compatibility shim -- delegates to nir.geometry_elc.build_elc_geometry_vba."""
    return _build_elc_geometry_vba(design_nm)


# Floquet ports on Zmin and Zmax. Cookbook-verified VBA from
# nir/VBA_COOKBOOK.md ("Floquet ports (both Zmax and Zmin)" section).
VBA_PORTS = """\
With FloquetPort
    .Reset
    .SetDialogTheta "0"
    .SetDialogPhi "0"
    .SetPolarizationIndependentOfScanAnglePhi "0", "False"
    .SetSortCode "+beta/pw"
    .SetCustomizedListFlag "False"
    .Port "Zmax"
    .SetNumberOfModesConsidered "2"
    .SetDistanceToReferencePlane "0"
    .SetUseCircularPolarization "False"
    .Port "Zmin"
    .SetNumberOfModesConsidered "2"
End With
"""


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design"),
    )
    ap.add_argument("--version", type=str, default="v6")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build VBA + save .cst, then stop before solver.")
    args = ap.parse_args(argv)

    run_dir: Path = args.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    version = args.version

    log_path = run_dir / "build_log.txt"
    log_path.write_text("")
    log_lines = []

    def log(msg: str) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        log_lines.append(line)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ----------------------------------------------------------------------
    # 1. Validate the design
    # ----------------------------------------------------------------------
    log(f"ELC build {version} -- output dir {run_dir}")
    log(f"Design (nm):\n{json.dumps(DESIGN, indent=2)}")
    design_mm = {k: v / NM_PER_MM for k, v in DESIGN.items()}
    design_mm["air_extent"] = AIR_EXTENT_MM
    log(f"Design (mm, CST units):\n{json.dumps(design_mm, indent=2)}")

    ok, reason = validate_design(DESIGN)
    if not ok:
        log(f"FATAL: design fails fab constraints: {reason}")
        return 2
    log("Design passes constraints_ELC.validate_design().")

    # ----------------------------------------------------------------------
    # 2. PRE-FLIGHT RENDER: produce a top-view PNG of the geometry from the
    #    DESIGN dict BEFORE opening CST. If the render doesn't match the
    #    seed paper's figure, the build will reproduce that wrong topology
    #    in CST (silently, after 30+ min of solver time). One-second sanity
    #    check that would have caught the v1-v9 wrong-topology bug at v1.
    # ----------------------------------------------------------------------
    preflight_png = run_dir / f"preflight_render_{version}.png"
    try:
        render_top_view(
            DESIGN,
            preflight_png,
            unit_scale=1e-6,    # DESIGN is in nm; render in mm
            unit_label="mm",
            title=f"ELC pre-flight render ({version})",
        )
        log(f"Pre-flight render saved -> {preflight_png}")
        log("  Visually compare this PNG against the seed paper's geometry BEFORE")
        log("  the long CST solve. If it doesn't match, abort and fix nir/geometry_elc.py.")
    except Exception as e:
        log(f"  [WARN] pre-flight render failed: {e}")
        log("  (continuing anyway; not a hard blocker)")

    # ----------------------------------------------------------------------
    # 3. Stale-file cleanup + open CST + create empty MWS project
    # ----------------------------------------------------------------------
    target_cst = run_dir / f"elc_11ghz_{version}.cst"
    target_folder = run_dir / f"elc_11ghz_{version}"
    if target_cst.exists():
        log(f"Removing stale {target_cst.name}")
        target_cst.unlink()
    if target_folder.exists():
        shutil.rmtree(target_folder, ignore_errors=True)

    log("Opening CST + creating new MWS project...")
    env = cstint.DesignEnvironment()
    project = env.new_mws()
    m3d = project.model3d

    # Save to the chosen path via Mode 3 (NOT history) -- avoids the circular
    # file-lock that bit v10 when SaveAs was in the history list.
    log(f"Setting project path -> {target_cst.name} (Mode 3, not in history)")
    save_project_at(project, target_cst)

    # ----------------------------------------------------------------------
    # 4. Inject VBA history via HistoryBuilder. Each step declares the side
    #    effects it expects (parameters created, materials defined, solids
    #    built). The builder verifies via Mode 3 queries after each step and
    #    raises with the specific missing artifact on any silent VBA failure.
    #    Order matters: Units first (so subsequent geometry uses the right
    #    unit context), then everything else.
    # ----------------------------------------------------------------------
    elc_param_names = list(DESIGN.keys()) + ["air_extent"]
    elc_solid_names = expected_solid_names()
    log("Building CST history with side-effect verification...")
    builder = HistoryBuilder(project, verify=True)
    try:
        builder.add(f"elc_11ghz_{version}: Step 1 Units",
                    VBA_UNITS)
        builder.add(f"elc_11ghz_{version}: Step 2 Parameters",
                    build_param_vba(DESIGN, AIR_EXTENT_MM),
                    expects_parameters=elc_param_names)
        builder.add(f"elc_11ghz_{version}: Step 3 Freq range",
                    VBA_FREQ_RANGE)
        builder.add(f"elc_11ghz_{version}: Step 4 Boundary",
                    VBA_BOUNDARY)
        builder.add(f"elc_11ghz_{version}: Step 5 Background",
                    VBA_BACKGROUND)
        builder.add(f"elc_11ghz_{version}: Step 6 FR4 material",
                    VBA_FR4_MATERIAL,
                    expects_materials=["FR4"])
        builder.add(f"elc_11ghz_{version}: Step 7 ELC geometry",
                    build_elc_geometry_vba_simple(DESIGN),
                    expects_solids=elc_solid_names)
        builder.add(f"elc_11ghz_{version}: Step 8 Floquet ports",
                    VBA_PORTS)
    except RuntimeError as e:
        log(f"  [FATAL] HistoryBuilder caught silent VBA failure:\n{e}")
        log(f"\nSteps that completed successfully before the failure:\n{builder.summary()}")
        try:
            project.save()
            project.close()
            env.close()
        except Exception:
            pass
        return 3

    log("History applied + side effects verified. Builder summary:")
    for line in builder.summary().splitlines():
        log(line)

    project.save()
    log("CST history saved.")

    if args.dry_run:
        log("[DRY RUN] Stopping before solver. Open the .cst to inspect.")
        project.close()
        env.close()
        return 0

    # ----------------------------------------------------------------------
    # 4. Solve via FDSolver.Start() (Mode 2 direct call).
    #    Per the patch antenna example: this is a blocking call that returns
    #    when the solver is done.
    # ----------------------------------------------------------------------
    log("Starting FD solver (m3d.FDSolver.Start())...")
    t0 = time.time()
    try:
        m3d.FDSolver.Start()
        elapsed = time.time() - t0
        log(f"FDSolver.Start() returned after {elapsed:.1f}s")
    except Exception as e:
        log(f"  [ERROR] FDSolver.Start() raised: {e}")
        import traceback
        log(traceback.format_exc())
        try:
            project.save()
            project.close()
            env.close()
        except Exception:
            pass
        return 4

    project.save()
    project.close()
    env.close()

    # ----------------------------------------------------------------------
    # 5. Export complex S-parameters via cst_helpers
    # ----------------------------------------------------------------------
    log("Exporting complex S-parameters...")
    proj3d, run_ids = open_results(target_cst)
    log(f"  Available run_ids: {run_ids}")

    tree = proj3d.get_tree_items()
    s_items_all = [t for t in tree if t.startswith("1D Results\\S-Parameters\\")]
    log(f"  S-parameter tree items found ({len(s_items_all)}):")
    for t in s_items_all:
        log(f"    {t}")

    refl_paths = find_reflection_sparams(tree)
    log(f"  Reflection (S_RR) candidates: {refl_paths}")
    if not refl_paths:
        log("  [ERROR] no diagonal Zmax(i),Zmax(i) reflection S-param in tree.")
        return 5

    # Pick mode 1 reflection -- the lower-cutoff TEM-like mode whose E-field
    # is along whatever axis our geometry forces resonance on.
    s11_path = refl_paths[0]
    m = re.search(r"Zmax\((\d+)\),Zmax\(\1\)", s11_path)
    s21_path = None
    if m:
        mode_idx = m.group(1)
        pat = f"Zmin({mode_idx}),Zmax({mode_idx})"
        s21_path = next((t for t in s_items_all if pat in t), None)
    if not s21_path:
        s21_path = next(
            (t for t in s_items_all
             if "Zmin(" in t and t.split(",")[-1].startswith("Zmax(")),
            None,
        )
    if not s21_path:
        log(f"  [ERROR] could not find matching transmission for {s11_path}")
        return 5
    log(f"  Reflection : {s11_path}")
    log(f"  Transmission: {s21_path}")

    s11_item, rid11 = get_result_with_data(proj3d, s11_path, run_ids)
    s21_item, rid21 = get_result_with_data(proj3d, s21_path, run_ids)
    log(f"  Data run_ids: S11 from {rid11}, S21 from {rid21}")

    f_s11 = np.array(s11_item.get_xdata(), dtype=float)
    s11   = np.array(s11_item.get_ydata(), dtype=complex)
    f_s21 = np.array(s21_item.get_xdata(), dtype=float)
    s21   = np.array(s21_item.get_ydata(), dtype=complex)
    if not np.allclose(f_s11, f_s21):
        log("  [WARN] S11/S21 frequency grids differ; interpolating onto S11 grid")
        s21 = np.interp(f_s11, f_s21, s21.real) + 1j * np.interp(f_s11, f_s21, s21.imag)

    # Flat-spectrum guard (last-line-of-defense for silent failures the
    # HistoryBuilder missed -- e.g., a port silently failing to attach so
    # the solver runs on a no-excitation domain).
    s11_var = float(np.std(np.abs(s11)))
    s21_var = float(np.std(np.abs(s21)))
    s21_min = float(np.min(np.abs(s21)))
    log(f"  Spectrum sanity: std|S11|={s11_var:.4f}, "
        f"std|S21|={s21_var:.4f}, min|S21|={s21_min:.4f}")
    try:
        assert_spectrum_nontrivial(s11, s21, threshold=0.02)
    except RuntimeError as e:
        log(f"  [FATAL] {e}")
        return 7

    # ----------------------------------------------------------------------
    # 6. Save CSVs + detect resonance
    # ----------------------------------------------------------------------
    freq_ghz = f_s11
    complex_csv = run_dir / "s_params_complex.csv"
    with complex_csv.open("w") as f:
        f.write(f"# Schurig 2006 ELC at 11 GHz target (build {version})\n")
        f.write(f"# DESIGN (nm): {json.dumps(DESIGN)}\n")
        f.write(f"# DESIGN (mm, in CST): {json.dumps(design_mm)}\n")
        f.write("freq_GHz,Re_S11,Im_S11,Re_S21,Im_S21\n")
        for fr, s1, s2 in zip(freq_ghz, s11, s21):
            f.write(f"{fr:.6f},{s1.real:.8e},{s1.imag:.8e},"
                    f"{s2.real:.8e},{s2.imag:.8e}\n")
    log(f"Wrote {complex_csv}")

    mag_csv = run_dir / "s_params_mag_sq.csv"
    with mag_csv.open("w") as f:
        f.write("freq_GHz,|S11|^2,|S21|^2\n")
        for fr, s1, s2 in zip(freq_ghz, s11, s21):
            f.write(f"{fr:.6f},{abs(s1)**2:.6e},{abs(s2)**2:.6e}\n")
    log(f"Wrote {mag_csv}")

    s21_mag = np.abs(s21)
    s11_mag = np.abs(s11)
    idx_min_s21 = int(np.argmin(s21_mag))
    f_peak_s21 = float(freq_ghz[idx_min_s21])
    s21_at_peak = float(s21_mag[idx_min_s21])
    idx_max_s11 = int(np.argmax(s11_mag))
    f_peak_s11 = float(freq_ghz[idx_max_s11])
    log(f"Resonance: |S21| min at {f_peak_s21:.3f} GHz "
        f"(|S21|={s21_at_peak:.3f}); |S11| max at {f_peak_s11:.3f} GHz")

    target_lo = F_TARGET_GHZ * (1.0 - TARGET_TOL_FRAC)
    target_hi = F_TARGET_GHZ * (1.0 + TARGET_TOL_FRAC)
    in_band = (target_lo <= f_peak_s21 <= target_hi)
    scale_correction = f_peak_s21 / F_TARGET_GHZ
    suggested = {
        k: v * scale_correction
        for k, v in DESIGN.items()
        if k in {"a", "d", "l", "w", "g"}
    }

    summary = {
        "version": version,
        "target_peak_ghz": F_TARGET_GHZ,
        "target_band_ghz": [target_lo, target_hi],
        "observed_peak_ghz_from_S21_notch": f_peak_s21,
        "observed_peak_ghz_from_S11_max":   f_peak_s11,
        "observed_S21_at_notch": s21_at_peak,
        "in_target_band": in_band,
        "scale_correction_factor": scale_correction,
        "suggested_design_after_one_shot_correction_nm": suggested,
        "note": (
            "If in_target_band, hand off to ML Design Stage 9. "
            "If not, replace DESIGN['a','d','l','w','g'] in design_ELC.py with "
            "suggested_design_after_one_shot_correction_nm and rerun."
        ),
    }
    summary_path = run_dir / "resonance_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log(f"Wrote {summary_path}")
    log(f"in_target_band = {in_band}")

    return 0 if in_band else 1


if __name__ == "__main__":
    raise SystemExit(main())
