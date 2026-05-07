"""nir/probe_drude_vba.py -- discover the working Drude / library-load VBA
syntax in this CST install by trial.

Each candidate VBA snippet is injected into a fresh CST project as its
own history step. CST raises with a clear error message when a property
or method doesn't exist; we capture that, print it, move on. The first
snippet that doesn't raise is the working syntax.

Usage:
    conda activate cst_inference
    cd D:/Claude/auto_cst
    python -m nir.probe_drude_vba

Per-attempt time: ~5-10 s (no solve, just history-rebuild). The whole
probe takes ~1 minute.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, CST_PYTHON_LIB)

import cst.interface as cstint  # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
TEMPLATE = PROJECT_ROOT / "templates" / "base_project.cst"
WORK_DIR = HERE / "drude_probe"
WORK_FILE = WORK_DIR / "probe.cst"


# ---- Candidate VBA snippets ----
# Au plasma freq omega_p = 1.367e16 rad/s (~9.03 eV)
# Au damping omega_c    = 1.05e14 rad/s   (~70 meV)

CANDIDATES = [
    ("V1: .DispModelEpsilon (already known to fail; canary)", """
With Material
  .Reset
  .Name "Au_V1"
  .Folder ""
  .FrqType "all"
  .Type "Normal"
  .Epsilon "1"
  .Mu "1"
  .Sigma "0"
  .DispModelEpsilon "Drude"
  .EpsInfinity "1"
  .DispCoeff1Eps "1.367e16"
  .DispCoeff2Eps "1.05e14"
  .Colour "1.0", "0.84", "0.0"
  .Create
End With
"""),

    ("V2: Material.LoadLibraryMaterial via With block", """
With Material
  .Reset
  .Name "Gold (Lossy)"
  .Folder ""
  .LoadLibraryMaterial
End With
"""),

    ("V3: top-level LoadLibraryMaterial", """
LoadLibraryMaterial "Gold (Lossy)"
"""),

    ("V4: top-level Material.LoadFromMaterialLib", """
Material.LoadFromMaterialLib "Gold (Lossy)"
"""),

    ("V5: Lossy metal + EpsilonInfinity + DispCoeffsAddDrude", """
With Material
  .Reset
  .Name "Au_V5"
  .Folder ""
  .FrqType "all"
  .Type "Lossy metal"
  .EpsilonInfinity "1.0"
  .DispCoeffsAddDrude "1.367e16", "1.05e14"
  .Colour "1.0", "0.84", "0.0"
  .Create
End With
"""),

    ("V6: AddDispEpsPole 'Drude'", """
With Material
  .Reset
  .Name "Au_V6"
  .Folder ""
  .FrqType "all"
  .Type "Normal"
  .Epsilon "1"
  .EpsInfinity "1.0"
  .AddDispEpsPole "Drude", "1.367e16", "1.05e14"
  .Colour "1.0", "0.84", "0.0"
  .Create
End With
"""),

    ("V7: Lorentz pole (single-pole approximation of Drude)", """
With Material
  .Reset
  .Name "Au_V7"
  .Folder ""
  .FrqType "all"
  .Type "Normal"
  .Epsilon "1"
  .EpsInfinity "1.0"
  .DispCoeffsAddLorentz "0", "1.367e16", "1.05e14"
  .Colour "1.0", "0.84", "0.0"
  .Create
End With
"""),

    ("V8: 'Disp Lorentz' separate calls", """
With Material
  .Reset
  .Name "Au_V8"
  .Folder ""
  .FrqType "all"
  .Type "Normal"
  .EpsInfinity "1"
  .DispCoeffsEpsilonOrder "1"
  .DispCoeffsEpsilon "1", "0", "1.367e16", "1.05e14"
  .Create
End With
"""),

    ("V9: Material with Conductivity DispModel (alternative form)", """
With Material
  .Reset
  .Name "Au_V9"
  .Folder ""
  .FrqType "all"
  .Type "Lossy metal"
  .Sigma "0"
  .DispersiveFittingSchemeSigma "Conductivity"
  .DispCoeff1Sigma "1.367e16"
  .DispCoeff2Sigma "1.05e14"
  .Create
End With
"""),
]


def _setup_project():
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATE, WORK_FILE)


def main():
    if not TEMPLATE.exists():
        print(f"Template not found: {TEMPLATE}")
        sys.exit(1)

    print("=" * 68)
    print("CST Drude / library-load VBA probe")
    print(f"Project: {WORK_FILE}")
    print(f"Trying {len(CANDIDATES)} candidate VBA snippets...")
    print("=" * 68)
    print()

    _setup_project()

    print("Opening CST environment...")
    env = cstint.DesignEnvironment()
    project = env.open_project(str(WORK_FILE.resolve()))
    m3d = project.model3d

    # First, delete the default PEC box so material defs don't conflict
    m3d.add_to_history("probe: clean", 'Component.Delete "component1"')

    results = []
    for label, vba in CANDIDATES:
        sys.stdout.write(f"\n{label}\n")
        sys.stdout.flush()
        try:
            m3d.add_to_history(f"probe: {label[:40]}", vba.strip())
            print("  -> SUCCESS (no exception)")
            results.append((label, "SUCCESS", None))
        except Exception as exc:
            err = str(exc).strip().splitlines()
            err_short = err[0] if err else ""
            for ln in err[1:4]:
                err_short += " | " + ln.strip()
            print(f"  -> FAIL: {err_short[:200]}")
            results.append((label, "FAIL", err_short))

    project.save()
    project.close()
    env.close()

    print()
    print("=" * 68)
    print("SUMMARY")
    print("=" * 68)
    for label, status, err in results:
        marker = "OK " if status == "SUCCESS" else "ERR"
        print(f"  [{marker}] {label}")
        if err:
            print(f"        {err[:160]}")

    successes = [(l, e) for l, s, e in results if s == "SUCCESS"]
    if successes:
        print()
        print(f"Working snippet(s): {len(successes)}")
        print("Manually inspect the saved project's history list to confirm the")
        print("material is correctly registered with the expected dispersion.")
        print(f"Project saved at: {WORK_FILE}")
    else:
        print()
        print("No snippet worked. Next step: open CST GUI, manually create a")
        print("'Gold (Lossy)' material via the material library import dialog,")
        print("save the project, and read the history-list VBA. That gives the")
        print("literal correct VBA syntax for this CST version.")


if __name__ == "__main__":
    main()
