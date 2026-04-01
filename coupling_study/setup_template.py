"""setup_template.py -- Create a blank CST template for the coupling study.

Creates a new CST Microwave Studio project with:
  - Units: um / THz
  - Materials: Gold (lossy metal), Ge_IR (loaded from library), Vacuum
  - Boundary conditions: unit cell (periodic) in X/Y, open in Z
  - Floquet ports on Zmax and Zmin
  - Frequency Domain solver configured for 14-32 THz (9.4-21.4 um)
  - Tetrahedral mesh

The resulting template has NO geometry -- geometry is added by build_and_run.py.

Usage:
    python setup_template.py
    python setup_template.py --output my_template.cst
    python setup_template.py --from-existing "path/to/5x5.cst"

If --from-existing is provided, copies that project and strips its geometry
(keeping solver/BC/material settings intact). This is RECOMMENDED because
it preserves the exact Ge_IR material definition from the original project.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CST library
# ---------------------------------------------------------------------------
CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

import cst.interface as cstint

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "template_coupling.cst"

# The original 5x5 project (has correct materials, solver, BC)
EXISTING_5X5 = Path(r"D:\Dary\agent\broad\Agent_fine\Ge_Abs_CWC_5x5_run10 (1).cst")


def create_from_existing(src_path: Path, dst_path: Path) -> None:
    """Copy existing CST project and strip geometry to create a clean template.

    This is the RECOMMENDED approach because it preserves:
      - Ge_IR material with correct frequency-dependent optical constants
      - Gold material definition
      - Solver settings (frequency range, accuracy, etc.)
      - Boundary conditions (unit cell periodic, open Z)
      - Floquet port configuration
      - Background material
      - Mesh settings
    """
    print(f"  Copying {src_path.name} -> {dst_path.name}")
    shutil.copy2(str(src_path), str(dst_path))

    # Also copy the associated results directory if it exists
    # (CST creates a folder alongside the .cst file)
    src_dir = src_path.with_suffix("")
    # We don't need the results dir for the template

    print(f"  Opening project to strip geometry...")
    env = cstint.DesignEnvironment()
    project = env.open_project(str(dst_path))
    mws = project.model3d

    # Delete all existing geometry by deleting component1
    # This removes shapes but preserves solver/BC/material definitions
    print("  Deleting existing geometry (component1)...")
    try:
        mws.add_to_history("Delete All Geometry",
            'Component.Delete "component1"\n')
    except Exception as e:
        print(f"  [WARN] Could not delete component1: {e}")
        print("  Trying alternative: delete individual shapes...")
        try:
            mws.add_to_history("Delete All Shapes", 'Solid.DeleteAll\n')
        except Exception as e2:
            print(f"  [WARN] Could not delete shapes: {e2}")

    # Delete old parameters (x_0_0 through x_4_4, etc.)
    # These will be replaced by build_and_run.py for the new array size
    print("  Clearing old parameters...")
    for i in range(5):
        for j in range(5):
            for prefix in ["x_", "g_", "w_", "a_", "r1_", "r2_"]:
                param = f"{prefix}{i}_{j}"
                try:
                    mws.add_to_history(f"Del {param}",
                        f'DeleteParameter "{param}"\n')
                except Exception:
                    pass

    # Clear GLOBAL_SIZE
    try:
        mws.add_to_history("Del GLOBAL_SIZE", 'DeleteParameter "GLOBAL_SIZE"\n')
    except Exception:
        pass

    # Update frequency range to cover both cell peaks (14-32 THz)
    print("  Updating frequency range to 14-32 THz...")
    try:
        mws.add_to_history("Update Freq Range",
            'Solver.FrequencyRange "14", "32"\n')
    except Exception as e:
        print(f"  [WARN] Could not update frequency range: {e}")

    # Rebuild to apply deletions
    print("  Rebuilding...")
    try:
        mws.full_history_rebuild()
    except Exception as e:
        print(f"  [WARN] Rebuild warning: {e}")

    project.save()
    project.close()
    env.close()

    print(f"  Template saved: {dst_path}")
    print(f"  Template is ready for build_and_run.py")


def create_from_scratch(dst_path: Path) -> None:
    """Create a new CST project from scratch with all settings.

    WARNING: This uses simplified material definitions. The Ge_IR material
    is approximated as a constant-epsilon dielectric (n=4.0, epsilon=16).
    For accurate results, use create_from_existing() instead.
    """
    print("  Creating new CST project from scratch...")
    print("  WARNING: Ge_IR will use simplified constant-epsilon model.")
    print("  For accurate results, use --from-existing instead.")

    env = cstint.DesignEnvironment()
    project = env.new_mws()

    mws = project.model3d

    # --- Units ---
    mws.add_to_history("Set Units",
        'With Units\n'
        '    .SetUnit "Length", "um"\n'
        '    .SetUnit "Frequency", "THz"\n'
        '    .SetUnit "Time", "ps"\n'
        '    .SetUnit "Temperature", "K"\n'
        'End With')

    # --- Background ---
    mws.add_to_history("Background",
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
        'End With')

    # --- Boundary conditions: unit cell (periodic) in X/Y, open in Z ---
    mws.add_to_history("Boundaries",
        'With Boundary\n'
        '    .Xmin "unit cell"\n'
        '    .Xmax "unit cell"\n'
        '    .Ymin "unit cell"\n'
        '    .Ymax "unit cell"\n'
        '    .Zmin "expanded open"\n'
        '    .Zmax "expanded open"\n'
        '    .XminThermal "isothermal"\n'
        '    .XmaxThermal "isothermal"\n'
        '    .YminThermal "isothermal"\n'
        '    .YmaxThermal "isothermal"\n'
        '    .ZminThermal "isothermal"\n'
        '    .ZmaxThermal "isothermal"\n'
        'End With')

    # --- Frequency range ---
    mws.add_to_history("Frequency Range",
        'Solver.FrequencyRange "14", "32"')

    # --- Materials ---
    # Gold (lossy metal)
    mws.add_to_history("Material: Gold",
        'With Material\n'
        '    .Reset\n'
        '    .Name "Gold"\n'
        '    .Folder ""\n'
        '    .FrqType "all"\n'
        '    .Type "Lossy metal"\n'
        '    .MaterialUnit "Frequency", "THz"\n'
        '    .MaterialUnit "Geometry", "um"\n'
        '    .MaterialUnit "Time", "ps"\n'
        '    .Conductivity "45610000"\n'
        '    .LossyMetalSIRoughness "0.0"\n'
        '    .CoordSystemType "Cartesian"\n'
        '    .Colour "1", "0.84", "0"\n'
        '    .Create\n'
        'End With')

    # Ge_IR (simplified: constant epsilon ~ 16, n ~ 4.0)
    mws.add_to_history("Material: Ge_IR",
        'With Material\n'
        '    .Reset\n'
        '    .Name "Ge_IR"\n'
        '    .Folder ""\n'
        '    .FrqType "all"\n'
        '    .Type "Normal"\n'
        '    .MaterialUnit "Frequency", "THz"\n'
        '    .MaterialUnit "Geometry", "um"\n'
        '    .Epsilon "16.0"\n'
        '    .Mue "1.0"\n'
        '    .Sigma "0"\n'
        '    .TanD "0"\n'
        '    .TanDFreq "0"\n'
        '    .TanDGiven "False"\n'
        '    .TanDModel "ConstTanD"\n'
        '    .ConstTanDModelOrderEps "1"\n'
        '    .Colour "0.75", "0.75", "0.75"\n'
        '    .Create\n'
        'End With')

    # --- Floquet ports ---
    mws.add_to_history("Floquet Ports",
        'With FloquetPort\n'
        '    .Reset\n'
        '    .SetDialogTheta "0"\n'
        '    .SetDialogPhi "0"\n'
        '    .SetPolarizationIndependentOfScanAnglePhi "0.0", "False"\n'
        '    .SetSortCode "+rep/+freq"\n'
        '    .SetCustomizedListFlag "False"\n'
        '    .Port "Zmax"\n'
        '    .SetNumberOfModesConsidered "2"\n'
        '    .SetDistanceToReferencePlane "0.0"\n'
        '    .SetUseCircularPolarization "False"\n'
        '    .Port "Zmin"\n'
        '    .SetNumberOfModesConsidered "2"\n'
        '    .SetDistanceToReferencePlane "0.0"\n'
        '    .SetUseCircularPolarization "False"\n'
        'End With')

    # --- Frequency Domain Solver ---
    mws.add_to_history("FD Solver",
        'With FDSolver\n'
        '    .Reset\n'
        '    .SetMethod "Tetrahedral", "General purpose"\n'
        '    .OrderTet "Second"\n'
        '    .OrderSrf "First"\n'
        '    .Stimulation "All", "All"\n'
        '    .ResetExcitationList\n'
        '    .AutoNormImpedance "True"\n'
        '    .NormingImpedance "50"\n'
        '    .ModesOnly "False"\n'
        '    .ConsiderPortLossesTet "True"\n'
        '    .SetShieldAllPorts "False"\n'
        '    .AccuracyHex "1e-6"\n'
        '    .AccuracyTet "1e-4"\n'
        '    .AccuracySrf "1e-3"\n'
        '    .LimitIterations "False"\n'
        '    .MaxIterations "0"\n'
        '    .SetCalcBlockExcitationsInParallel "True", "True", ""\n'
        'End With')

    # --- Mesh ---
    mws.add_to_history("Mesh",
        'With Mesh\n'
        '    .MeshType "Tetrahedral"\n'
        'End With')

    # Rebuild
    mws.full_history_rebuild()

    # Save
    project.save_as(str(dst_path))
    project.close()
    env.close()

    print(f"  Template saved: {dst_path}")
    print(f"  NOTE: Ge_IR uses simplified epsilon=16.0 model.")


def main():
    parser = argparse.ArgumentParser(
        description="Create a blank CST template for the coupling study")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT),
                        help="Output path for the template .cst file")
    parser.add_argument("--from-existing", type=str, default=None,
                        help="Copy from an existing CST project (RECOMMENDED). "
                             "Strips geometry but keeps solver/BC/materials.")
    parser.add_argument("--from-scratch", action="store_true",
                        help="Create from scratch (uses simplified Ge_IR)")
    args = parser.parse_args()

    dst = Path(args.output)

    if args.from_existing:
        src = Path(args.from_existing)
        if not src.exists():
            print(f"ERROR: Source project not found: {src}")
            sys.exit(1)
        create_from_existing(src, dst)
    elif args.from_scratch:
        create_from_scratch(dst)
    else:
        # Default: use existing 5x5 project if available
        if EXISTING_5X5.exists():
            print(f"  Using existing 5x5 project as base (recommended)")
            create_from_existing(EXISTING_5X5, dst)
        else:
            print(f"  No existing project found, creating from scratch")
            create_from_scratch(dst)


if __name__ == "__main__":
    main()
