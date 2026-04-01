"""build_and_run.py -- Coupling-vs-scale study for CWC metamaterial absorber.

Creates a FRESH CST project for a given array configuration (1x1, 2x2, 4x4, 8x8),
builds the full model (materials, boundaries, solver, geometry), runs the HF
Frequency Domain solver, and exports absorptance spectrum.

No template needed -- each project is created from scratch to avoid history
conflicts that cause "Simulation could not be started" errors.

Usage:
    python build_and_run.py --config 1x1_a
    python build_and_run.py --config 1x1_b
    python build_and_run.py --config 2x2
    python build_and_run.py --config 4x4
    python build_and_run.py --config 8x8
    python build_and_run.py --config all          # run all sequentially
    python build_and_run.py --config 2x2 --skip-solve   # build only
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# CST library
# ---------------------------------------------------------------------------
CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

import cst.interface as cstint
import cst.results as cstres

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
EXPORTS_DIR = HERE / "exports"
RESULTS_TSV = HERE / "results.tsv"

# ---------------------------------------------------------------------------
# Cell definitions (from 1x1 database, random seed=42)
# ---------------------------------------------------------------------------
CELL_A = {
    "x": 0.7386, "g": 0.7414, "w": 0.2065,
    # r1 = 2.0 - 0.7386 = 1.2614 (large circle)
    # peak ~ 10.3 um (29.1 THz)
}

CELL_B = {
    "x": 1.1083, "g": 0.8253, "w": 0.2038,
    # r1 = 2.0 - 1.1083 = 0.8917 (small circle)
    # peak ~ 18.8 um (16.0 THz)
}

PITCH = 4.0  # um, fixed for all cells

BASE_PARAMS = {
    "t": 0.6,       # Ge spacer thickness (um)
    "t_gp": 0.2,    # Au ground plane thickness (um) -- matches 1x1 model (t_GP=0.2)
    "t_mm": 0.1,    # Au CWC pattern thickness (um)
}
# Z is computed per-config as 3*a_total (matches 1x1 model: Z=3*a)

# Material VBA files extracted from original 1x1 CST model
GOLD_VBA_FILE = HERE / "gold_vba.txt"
GE_IR_VBA_FILE = HERE / "ge_ir_vba.txt"

# Solver
FREQ_MIN_THZ = 14.0   # 21.4 um
FREQ_MAX_THZ = 32.0   # 9.4 um  (covers both cell peaks with margin)
POLL_INTERVAL = 5.0
SOLVER_TIMEOUT = 14400.0   # 4 hours (8x8 will be slow)


# ---------------------------------------------------------------------------
# Pattern generation
# ---------------------------------------------------------------------------

def generate_pattern(config: str) -> List[List[str]]:
    """Return the NxN cell-type pattern for a given configuration."""
    if config == "1x1_a":
        return [["a"]]
    elif config == "1x1_b":
        return [["b"]]
    elif config == "2x2":
        return [["a", "b"], ["b", "a"]]
    elif config == "4x4":
        return [
            ["a", "a", "b", "b"],
            ["a", "a", "b", "b"],
            ["b", "b", "a", "a"],
            ["b", "b", "a", "a"],
        ]
    elif config == "8x8":
        row_top = ["a"] * 4 + ["b"] * 4
        row_bot = ["b"] * 4 + ["a"] * 4
        return [row_top] * 4 + [row_bot] * 4
    else:
        raise ValueError(f"Unknown config: {config}")


def get_cell_params(cell_type: str) -> dict:
    return CELL_A if cell_type == "a" else CELL_B


def print_pattern(pattern: List[List[str]]) -> None:
    n = len(pattern)
    print(f"  Pattern ({n}x{n}):")
    for row in pattern:
        print("    " + " ".join(row))


# ---------------------------------------------------------------------------
# Full project builder (from scratch -- no template needed)
# ---------------------------------------------------------------------------

def plus_join(names: list) -> str:
    return " + ".join(names) if names else "0"


def build_project(project, pattern: List[List[str]], project_path: Path) -> None:
    """Build the COMPLETE CST project from scratch.

    Includes: units, materials, boundaries, Floquet ports, solver, and geometry.
    Uses add_to_history for everything, then one full_history_rebuild at the end.
    Since this is a fresh project with no prior history, rebuild works cleanly.
    """
    mws = project.model3d
    n = len(pattern)
    global_size = n * PITCH

    # ===== 1. UNITS =====
    mws.add_to_history("Set Units",
        'With Units\n'
        '    .SetUnit "Length", "um"\n'
        '    .SetUnit "Frequency", "THz"\n'
        '    .SetUnit "Time", "ps"\n'
        '    .SetUnit "Temperature", "K"\n'
        'End With')

    # ===== 2. BACKGROUND =====
    mws.add_to_history("Set Background",
        'With Background\n'
        '    .Type "Normal"\n'
        '    .Epsilon "1.0"\n'
        '    .Mue "1.0"\n'
        '    .XminSpace "0"\n'
        '    .XmaxSpace "0"\n'
        '    .YminSpace "0"\n'
        '    .YmaxSpace "0"\n'
        '    .ZminSpace "0"\n'
        '    .ZmaxSpace "0"\n'
        '    .ApplyInAllDirections "False"\n'
        'End With')

    # ===== 3. FREQUENCY RANGE =====
    # 10-20 um wavelength range covers both cell peaks
    mws.add_to_history("Set Frequency Range",
        'Solver.WavelengthRange "10", "20"')

    # ===== 4. BOUNDARY CONDITIONS =====
    # Unit cell (periodic) in X/Y, expanded open in Z
    mws.add_to_history("Set Boundaries",
        'With Boundary\n'
        '    .Xmin "unit cell"\n'
        '    .Xmax "unit cell"\n'
        '    .Ymin "unit cell"\n'
        '    .Ymax "unit cell"\n'
        '    .Zmin "expanded open"\n'
        '    .Zmax "expanded open"\n'
        'End With')

    # ===== 5. MATERIALS (loaded from original 1x1 CST model) =====
    # Gold (lossy metal with exact VBA from original model)
    gold_vba = GOLD_VBA_FILE.read_text(encoding="utf-8").strip()
    mws.add_to_history("Define Gold", gold_vba)

    # Ge_IR (full tabulated dispersive fitting from original model)
    ge_ir_vba = GE_IR_VBA_FILE.read_text(encoding="utf-8").strip()
    mws.add_to_history("Define Ge_IR", ge_ir_vba)

    # ===== 6. PARAMETERS =====
    for k, v in BASE_PARAMS.items():
        mws.StoreParameterWithDescription(k, str(v), f"Base: {k}")
    mws.StoreParameterWithDescription("GLOBAL_SIZE", str(global_size), "Total array size")
    # Z = 3*a (matches 1x1 model convention)
    z_val = 3.0 * PITCH
    mws.StoreParameterWithDescription("Z", str(z_val), "Vacuum height = 3*a")

    for i in range(n):
        for j in range(n):
            cell = get_cell_params(pattern[i][j])
            tag = f"({i},{j})={pattern[i][j]}"
            mws.StoreParameterWithDescription(f"a_{i}_{j}", str(PITCH), f"Pitch {tag}")
            mws.StoreParameterWithDescription(f"x_{i}_{j}", str(cell["x"]), f"x {tag}")
            mws.StoreParameterWithDescription(f"g_{i}_{j}", str(cell["g"]), f"g {tag}")
            mws.StoreParameterWithDescription(f"w_{i}_{j}", str(cell["w"]), f"w {tag}")
            mws.StoreParameterWithDescription(f"r1_{i}_{j}", f"(a_{i}_{j}/2) - x_{i}_{j}", f"r1 {tag}")
            mws.StoreParameterWithDescription(f"r2_{i}_{j}", f"r1_{i}_{j} - w_{i}_{j}", f"r2 {tag}")

    # ===== 7. GEOMETRY: STACKUP =====
    half_xy = "GLOBAL_SIZE / 2"
    mws.add_to_history("Ground Plane",
        'With Brick\n'
        '    .Reset\n'
        '    .Name "Ground_Plane"\n'
        '    .Component "component1"\n'
        '    .Material "Gold"\n'
        f'    .Xrange "-{half_xy}", "{half_xy}"\n'
        f'    .Yrange "-{half_xy}", "{half_xy}"\n'
        '    .Zrange "-(t + t_gp)", "-t"\n'
        '    .Create\n'
        'End With')

    mws.add_to_history("Ge Dielectric",
        'With Brick\n'
        '    .Reset\n'
        '    .Name "Ge_Dielectric"\n'
        '    .Component "component1"\n'
        '    .Material "Ge_IR"\n'
        f'    .Xrange "-{half_xy}", "{half_xy}"\n'
        f'    .Yrange "-{half_xy}", "{half_xy}"\n'
        '    .Zrange "-t", "0"\n'
        '    .Create\n'
        'End With')

    mws.add_to_history("Vacuum Top",
        'With Brick\n'
        '    .Reset\n'
        '    .Name "Vacuum_Top"\n'
        '    .Component "component1"\n'
        '    .Material "Vacuum"\n'
        f'    .Xrange "-{half_xy}", "{half_xy}"\n'
        f'    .Yrange "-{half_xy}", "{half_xy}"\n'
        '    .Zrange "t_mm", "Z"\n'
        '    .Create\n'
        'End With')

    # ===== 8. GEOMETRY: CWC CELLS =====
    for i in range(n):
        for j in range(n):
            x_off = plus_join([f"1*a_{k}_{j}" for k in range(i)])
            y_off = plus_join([f"1*a_{i}_{k}" for k in range(j)])

            cx = f"({x_off}) + a_{i}_{j}/2 - GLOBAL_SIZE/2"
            cy = f"({y_off}) + a_{i}_{j}/2 - GLOBAL_SIZE/2"

            r1 = f"r1_{i}_{j}"
            r2 = f"r2_{i}_{j}"
            w = f"w_{i}_{j}"
            g = f"g_{i}_{j}"

            struct_name = f"Au_Struct_{i}_{j}"
            cross_name = f"CrossTool_{i}_{j}"

            # Ring
            mws.add_to_history(f"Ring {i}_{j}",
                'With Cylinder\n'
                '    .Reset\n'
                f'    .Name "{struct_name}"\n'
                '    .Component "component1"\n'
                '    .Material "Gold"\n'
                f'    .OuterRadius "{r1}"\n'
                f'    .InnerRadius "{r2}"\n'
                '    .Axis "z"\n'
                '    .Zrange "0", "t_mm"\n'
                f'    .Xcenter "{cx}"\n'
                f'    .Ycenter "{cy}"\n'
                '    .Segments "0"\n'
                '    .Create\n'
                'End With')

            # Cross arm
            mws.add_to_history(f"CrossArm {i}_{j}",
                'With Brick\n'
                '    .Reset\n'
                f'    .Name "{cross_name}"\n'
                '    .Component "component1"\n'
                '    .Material "Gold"\n'
                f'    .Xrange "({cx}) - ({r2})", "({cx}) - ({g})/2"\n'
                f'    .Yrange "({cy}) - ({w})/2", "({cy}) + ({w})/2"\n'
                '    .Zrange "0", "t_mm"\n'
                '    .Create\n'
                'End With')

            # Rotate cross arm 3 times (90, 180, 270)
            mws.add_to_history(f"CrossRot90 {i}_{j}",
                'With Transform\n'
                '    .Reset\n'
                f'    .Name "component1:{cross_name}"\n'
                '    .Origin "Free"\n'
                f'    .Center "{cx}", "{cy}", "0"\n'
                '    .Angle "0", "0", "90"\n'
                '    .MultipleObjects "True"\n'
                '    .GroupObjects "False"\n'
                '    .Repetitions "3"\n'
                '    .AutoDestination "True"\n'
                '    .Transform "Shape", "Rotate"\n'
                'End With')

            # Boolean union: ring + 4 cross arms
            mws.add_to_history(f"AddCross {i}_{j}",
                f'Solid.Add "component1:{struct_name}", "component1:{cross_name}"\n'
                f'Solid.Add "component1:{struct_name}", "component1:{cross_name}_1"\n'
                f'Solid.Add "component1:{struct_name}", "component1:{cross_name}_2"\n'
                f'Solid.Add "component1:{struct_name}", "component1:{cross_name}_3"')

    # ===== 9. FLOQUET PORTS (matches 1x1 model) =====
    mws.add_to_history("Floquet Ports",
        'With FloquetPort\n'
        '    .Reset\n'
        '    .SetDialogTheta "0"\n'
        '    .SetDialogPhi "0"\n'
        '    .SetSortCode "+beta/pw"\n'
        '    .SetCustomizedListFlag "False"\n'
        '    .Port "Zmin"\n'
        '    .SetNumberOfModesConsidered "2"\n'
        '    .Port "Zmax"\n'
        '    .SetNumberOfModesConsidered "2"\n'
        'End With')

    # ===== 10. CHANGE TO OPTICAL PROBLEM TYPE =====
    mws.add_to_history("Set Optical Problem",
        'ChangeProblemType "Optical"')

    # ===== 11. MESH + SOLVER (matches 1x1 model) =====
    mws.add_to_history("Mesh Settings",
        'With Mesh\n'
        '    .MeshType "Tetrahedral"\n'
        'End With')

    mws.add_to_history("Set HF FD Solver",
        'ChangeSolverType("HF Frequency Domain")')

    mws.add_to_history("FD Solver Settings",
        'With FDSolver\n'
        '    .Reset\n'
        '    .Stimulation "List", "List"\n'
        '    .ResetExcitationList\n'
        '    .AddToExcitationList "Zmax", "TE(0,0);TM(0,0)"\n'
        '    .LowFrequencyStabilization "False"\n'
        'End With')

    # ===== 11. REBUILD =====
    print("  Performing full history rebuild...")
    mws.full_history_rebuild()
    print("  Build complete.")

    # Save with the desired path
    project.save()


# ---------------------------------------------------------------------------
# Result export (same approach as auto_cst_broad/runner.py)
# ---------------------------------------------------------------------------

def export_results(project_path: str, export_dir: Path) -> Dict[str, str]:
    """Extract absorptance and S-parameters via cst.results."""
    export_dir.mkdir(parents=True, exist_ok=True)
    exported = {}

    try:
        proj_res = cstres.ProjectFile(str(project_path), allow_interactive=True)
        proj3d = proj_res.get_3d()
        tree_items = proj3d.get_tree_items()
        sep = "\\"

        # --- S-Parameters ---
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

                out_path = export_dir / f"{label}.csv"
                with open(out_path, "w", newline="") as f:
                    f.write("# frequency_THz\t|S|^2\n")
                    for freq, val in zip(xdata, mag_sq):
                        f.write(f"{freq}\t{val}\n")
                exported[label] = str(out_path)
                print(f"    exported {label}: {len(xdata)} pts")
            except Exception as exc:
                print(f"    [WARN] {item_path}: {exc}")

        # --- RTA tables ---
        rta_prefix = "Tables" + sep + "1D Results" + sep + "Reflectance-Transmittance-Absorbance"
        rta_items = [item for item in tree_items if item.startswith(rta_prefix)]

        for item_path in rta_items:
            label = item_path.split(sep)[-1]
            try:
                result = proj3d.get_result_item(item_path)
                xdata = np.array(result.get_xdata())
                ydata = result.get_ydata()
                vals = np.array([abs(y) for y in ydata])
                xdata_thz = 300000.0 / xdata  # nm -> THz

                out_path = export_dir / f"{label}.csv"
                with open(out_path, "w", newline="") as f:
                    f.write(f"# frequency_THz\t{label}\n")
                    for freq, val in zip(xdata_thz, vals):
                        f.write(f"{freq}\t{val}\n")
                exported[label] = str(out_path)
                print(f"    exported {label}: {len(xdata)} pts")

                if label.startswith("A_Zmax"):
                    abs_path = export_dir / "Absorptance.csv"
                    with open(abs_path, "w", newline="") as f:
                        f.write("# frequency_THz\tAbsorptance\n")
                        for freq, val in zip(xdata_thz, vals):
                            f.write(f"{freq}\t{val}\n")
                    exported["Absorptance"] = str(abs_path)
            except Exception as exc:
                print(f"    [WARN] {label}: {exc}")

        # --- Compute from Floquet S-params if no RTA ---
        if "Absorptance" not in exported and s_param_items:
            print("    Computing Absorptance from Floquet S-parameters...")
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
                total_s_sq = np.zeros_like(ref_freq)
                for label, mag_sq in s_data.items():
                    if "Zmax(1)" in label and label.startswith("S"):
                        total_s_sq += mag_sq
                        print(f"      summing {label}: max|S|^2={np.max(mag_sq):.6f}")

                absorptance = np.clip(1.0 - total_s_sq, 0.0, 1.0)
                out_path = export_dir / "Absorptance.csv"
                with open(out_path, "w", newline="") as f:
                    f.write("# frequency_THz\tAbsorptance\n")
                    for freq, val in zip(ref_freq, absorptance):
                        f.write(f"{freq}\t{val}\n")
                exported["Absorptance"] = str(out_path)
                print(f"    exported Absorptance (computed): {len(ref_freq)} pts")

    except Exception as exc:
        print(f"  [ERROR] Result export failed: {exc}")
        import traceback
        traceback.print_exc()

    return exported


# ---------------------------------------------------------------------------
# Results logging
# ---------------------------------------------------------------------------

def init_results_tsv() -> None:
    if not RESULTS_TSV.exists():
        with open(RESULTS_TSV, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow([
                "config", "n_cells", "timestamp",
                "mean_abs_full", "min_abs_full",
                "mean_abs_10_13", "mean_abs_18_20",
                "solve_status", "solve_duration_s", "note",
            ])


def log_result(config: str, n: int, metrics: dict, solve_status: str,
               solve_duration: float, note: str) -> None:
    init_results_tsv()
    with open(RESULTS_TSV, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow([
            config, n * n,
            datetime.now().isoformat(timespec="seconds"),
            f"{metrics.get('mean_abs_full', 0):.4f}",
            f"{metrics.get('min_abs_full', 0):.4f}",
            f"{metrics.get('mean_abs_10_13', 0):.4f}",
            f"{metrics.get('mean_abs_18_20', 0):.4f}",
            solve_status, f"{solve_duration:.1f}", note,
        ])


# ---------------------------------------------------------------------------
# Evaluate absorptance spectrum
# ---------------------------------------------------------------------------

def evaluate_spectrum(csv_path: str) -> dict:
    """Compute metrics from exported absorptance CSV."""
    freq, absorptance = [], []
    with open(csv_path, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            try:
                freq.append(float(row[0].strip()))
                absorptance.append(float(row[1].strip()))
            except (ValueError, IndexError):
                continue

    freq = np.array(freq)
    absorptance = np.array(absorptance)

    mean_abs_full = float(np.mean(absorptance))
    min_abs_full = float(np.min(absorptance))

    # Cell A band: 10-13 um = 23.08-30.00 THz
    mask_a = (freq >= 23.08) & (freq <= 30.00)
    mean_abs_10_13 = float(np.mean(absorptance[mask_a])) if np.any(mask_a) else 0.0

    # Cell B band: 18-20 um = 15.00-16.67 THz
    mask_b = (freq >= 15.00) & (freq <= 16.67)
    mean_abs_18_20 = float(np.mean(absorptance[mask_b])) if np.any(mask_b) else 0.0

    return {
        "mean_abs_full": mean_abs_full,
        "min_abs_full": min_abs_full,
        "mean_abs_10_13": mean_abs_10_13,
        "mean_abs_18_20": mean_abs_18_20,
        "freq": freq,
        "absorptance": absorptance,
    }


# ---------------------------------------------------------------------------
# Main pipeline for one configuration
# ---------------------------------------------------------------------------

def run_one_config(config: str, skip_solve: bool = False) -> dict:
    """Run the full pipeline for one array configuration."""
    pattern = generate_pattern(config)
    n = len(pattern)

    print(f"\n{'='*60}")
    print(f"  Coupling Study -- Config: {config} ({n}x{n} = {n*n} cells)")
    print(f"  Cell A: x={CELL_A['x']}, g={CELL_A['g']}, w={CELL_A['w']}  (peak ~10.3 um)")
    print(f"  Cell B: x={CELL_B['x']}, g={CELL_B['g']}, w={CELL_B['w']}  (peak ~18.8 um)")
    print(f"{'='*60}")
    print_pattern(pattern)

    # Find a usable project path (avoid locked files from prior CST sessions)
    project_path = HERE / f"coupling_{config}.cst"
    results_dir = project_path.with_suffix("")
    attempt = 0
    while True:
        can_use = True
        # Check if results dir is locked
        if results_dir.exists():
            lok_file = results_dir / "Model.lok"
            if lok_file.exists():
                can_use = False
            else:
                try:
                    shutil.rmtree(str(results_dir))
                except PermissionError:
                    can_use = False
        if project_path.exists():
            try:
                project_path.unlink()
            except PermissionError:
                can_use = False
        if can_use:
            break
        attempt += 1
        project_path = HERE / f"coupling_{config}_v{attempt}.cst"
        results_dir = project_path.with_suffix("")
        print(f"  Path locked, trying: {project_path.name}")
        if attempt > 5:
            print("  [ERROR] All paths locked. Close CST and retry.")
            return {"config": config, "n": n, "solve_status": "error",
                    "solve_duration": 0, "metrics": {}, "export_dir": ""}

    print(f"  Project path: {project_path.name}")

    # --- Create fresh CST project, build model, solve ---
    env = None
    project = None
    solve_status = "not_started"
    solve_duration = 0.0

    try:
        print("  Creating fresh CST project...")
        env = cstint.DesignEnvironment()
        project = env.new_mws()

        # Save to desired path (model3d.SaveAs takes path + include_results bool)
        project.model3d.SaveAs(str(project_path), False)
        print(f"  Project saved as: {project_path.name}")

        # Build complete model (materials, BC, solver, geometry)
        print(f"  Building {n}x{n} CWC array model...")
        build_project(project, pattern, project_path)

        if skip_solve:
            print("  [SKIP] Solver skipped (--skip-solve)")
            solve_status = "skipped"
        else:
            mws = project.model3d
            print("  Starting HF Frequency Domain solver...")
            t0 = time.time()
            mws.start_solver()

            while mws.is_solver_running():
                elapsed = time.time() - t0
                if elapsed > SOLVER_TIMEOUT:
                    try:
                        mws.abort_solver()
                    except Exception:
                        pass
                    solve_status = "timeout"
                    solve_duration = elapsed
                    break
                # Progress every 60s
                mins = int(elapsed) // 60
                if int(elapsed) % 60 == 0 and mins > 0:
                    print(f"    ... solver running ({mins}m {int(elapsed)%60}s)")
                time.sleep(POLL_INTERVAL)
            else:
                solve_duration = time.time() - t0
                solve_status = "success"

            print(f"  Solver finished: {solve_status} ({solve_duration:.1f}s)")

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

    # --- Export results ---
    export_dir = EXPORTS_DIR / config
    exported = {}
    if solve_status in ("success", "skipped"):
        print("  Exporting results...")
        exported = export_results(str(project_path), export_dir)
        print(f"  Exported {len(exported)} result(s)")

    # --- Evaluate ---
    metrics = {}
    abs_csv = export_dir / "Absorptance.csv"
    if abs_csv.exists():
        metrics = evaluate_spectrum(str(abs_csv))
        print(f"\n  --- Results for {config} ---")
        print(f"  Mean absorptance (full):   {metrics['mean_abs_full']:.4f}")
        print(f"  Min absorptance (full):    {metrics['min_abs_full']:.4f}")
        print(f"  Mean abs 10-13um (cell A): {metrics['mean_abs_10_13']:.4f}")
        print(f"  Mean abs 18-20um (cell B): {metrics['mean_abs_18_20']:.4f}")

    log_result(config, n, metrics, solve_status, solve_duration,
               f"{config}: {n}x{n} checkerboard")

    return {
        "config": config,
        "n": n,
        "solve_status": solve_status,
        "solve_duration": solve_duration,
        "metrics": metrics,
        "export_dir": str(export_dir),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

ALL_CONFIGS = ["1x1_a", "1x1_b", "2x2", "4x4", "8x8"]


def main():
    parser = argparse.ArgumentParser(
        description="Coupling-vs-scale study for CWC metamaterial absorber")
    parser.add_argument("--config", type=str, required=True,
                        choices=ALL_CONFIGS + ["all"],
                        help="Array configuration to run")
    parser.add_argument("--skip-solve", action="store_true",
                        help="Build geometry only, skip solver")
    args = parser.parse_args()

    configs = ALL_CONFIGS if args.config == "all" else [args.config]

    results = []
    for cfg in configs:
        result = run_one_config(cfg, skip_solve=args.skip_solve)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  COUPLING STUDY SUMMARY")
    print(f"{'='*60}")
    for r in results:
        m = r.get("metrics", {})
        print(f"  {r['config']:8s} | {r['n']}x{r['n']} | "
              f"status={r['solve_status']:8s} | "
              f"mean_abs={m.get('mean_abs_full', 0):.4f} | "
              f"A_band={m.get('mean_abs_10_13', 0):.4f} | "
              f"B_band={m.get('mean_abs_18_20', 0):.4f} | "
              f"time={r['solve_duration']:.0f}s")


if __name__ == "__main__":
    main()
