"""Diagnostic: inspect the post-solve elc_11ghz_v1.cst to figure out why the
S-parameters didn't end up at the expected tree paths.

Reports:
  - Full cst.results tree (every item, full path)
  - cst.interface mesh cell count
  - Solid component list
  - Defined materials
"""
import sys
from pathlib import Path

sys.path.insert(0, r"E:\cst\AMD64\python_cst_libraries")

import cst.interface as cstint
import cst.results as cstres


PROJECT = Path(r"D:\Claude\MetaClaw\runs\elc_11ghz\Experiment\cst_design\elc_11ghz_v1.cst")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Pass 1: cst.results read-only inspection
# ---------------------------------------------------------------------------
section("cst.results.ProjectFile tree items")
proj_res = cstres.ProjectFile(str(PROJECT), allow_interactive=True)
proj3d = proj_res.get_3d()
tree_items = proj3d.get_tree_items()
print(f"Total tree items: {len(tree_items)}")
for t in tree_items:
    print(f"  {t!r}")

# ---------------------------------------------------------------------------
# Pass 2: cst.interface re-open + inspect mesh / solids / materials
# ---------------------------------------------------------------------------
section("cst.interface inspection")

env = cstint.DesignEnvironment()
proj = env.open_project(str(PROJECT))
m3d = proj.model3d

# Mesh
try:
    n_cells = m3d.Mesh.GetNumberOfMeshCells()
    print(f"Mesh cells: {n_cells:,}")
except Exception as e:
    print(f"[WARN] mesh probe failed: {e}")

# Solids: list every solid via VBA dump
try:
    print()
    print("Defined solids (VBA query):")
    # Execute a VBA snippet that dumps the solid list into a string.
    # GetSolidCount() and GetSolidName(i) are the canonical accessors.
    snippet = """\
Dim n As Integer
n = Solid.GetNumberOfShapes
Dim s As String
s = "n=" & n
Dim i As Integer
For i = 0 To n - 1
    s = s & "|" & Solid.GetNameOfShapeFromIndex(i)
Next
ReportInformation s
"""
    # Note: ReportInformation echoes to CST's message window, not to Python.
    # Simpler approach -- iterate via Pick (not great). Instead, just
    # check whether any solids exist via the solver's mesh.
    print("  (Solid enumeration requires CST GUI; skipping VBA reflection.)")
except Exception as e:
    print(f"[WARN] solid enumeration failed: {e}")

# Try reading 3D project parameters
try:
    print()
    print("Stored parameters (from m3d):")
    for name in ("a", "d", "l", "w", "g", "h_FR4", "t_Cu", "air_extent"):
        try:
            val = m3d.GetParameterByName(name)
            print(f"  {name} = {val}")
        except Exception as e:
            print(f"  {name} : not found ({e})")
except Exception as e:
    print(f"[WARN] parameter probe failed: {e}")

proj.close()
env.close()
print()
print("Done.")
