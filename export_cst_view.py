"""Open elc_11ghz_v10.cst and try to export an image of the 3D structure view
via CST's VBA Plot/View export macros.

CST has several image-export APIs whose names drift across versions. Try a few.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, r"E:\cst\AMD64\python_cst_libraries")
import cst.interface as cstint

TARGET = Path(r"D:\Claude\MetaClaw\runs\elc_11ghz\Experiment\cst_design\elc_11ghz_v10.cst")
OUT_DIR = TARGET.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)


env = cstint.DesignEnvironment()
print(f"Opening {TARGET.name}...")
proj = env.open_project(str(TARGET.resolve()))
m3d = proj.model3d

# Try several VBA image-export forms. The right one for CST 2026 may be
# any of these; we attempt each and report which (if any) succeed.
attempts = [
    # Form A: Plot.ExportPlot with format string
    ("Plot.ExportPlot PNG", f'Plot.ExportPlot "{(OUT_DIR / "cst_view_A.png").as_posix()}", "PNG"'),
    # Form B: Plot.StoreImage
    ("Plot.StoreImage",     f'Plot.StoreImage "{(OUT_DIR / "cst_view_B.bmp").as_posix()}"'),
    # Form C: View.ExportImage
    ("View.ExportImage",    f'View.ExportImage "{(OUT_DIR / "cst_view_C.png").as_posix()}", "PNG"'),
    # Form D: ExportImage at top-level (no object prefix)
    ("ExportImage top-level", f'ExportImage "{(OUT_DIR / "cst_view_D.png").as_posix()}"'),
    # Form E: ASCIIExport for 3D model? No, that's data. Skip.
    # Form F: Mesh.ExportMeshToFile? geometry export...
]

for label, vba in attempts:
    print(f"--- {label} ---")
    try:
        m3d.add_to_history(f"probe_{label}", vba)
        print(f"  add_to_history OK -- check if file was created.")
    except Exception as e:
        print(f"  add_to_history raised: {e}")

# Check which images were actually written
print()
print("Generated files in OUT_DIR (latest 5):")
for f in sorted(OUT_DIR.glob("cst_view_*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
    print(f"  {f.name}  ({f.stat().st_size:,} bytes)")

proj.save()
proj.close()
env.close()
print("Done.")
