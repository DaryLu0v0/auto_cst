"""validate_elc_geometry.py -- CLI for the ELC pre-flight render.

Thin wrapper around `nir.geometry_elc.render_top_view()`. The actual
rendering logic lives in nir/geometry_elc.py alongside the VBA emitter
(single source of truth -- both consume the same `ELC_BRICK_SPEC`).

Usage:
    python validate_elc_geometry.py
    python validate_elc_geometry.py --out my_render.png

Compares the geometry implied by `nir/design_ELC.py`'s DESIGN dict
against the Schurig 2006 Fig 1(b) drawing in your head (or on paper).
If they don't match, the topology in `nir/geometry_elc.py` is wrong --
fix it BEFORE running build_elc_11ghz.py (saves ~30 minutes of CST
solver time and ~9 silent-failure build iterations, per the v1-v9
post-mortem).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from nir.design_ELC import DESIGN  # noqa: E402
from nir.geometry_elc import render_top_view  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design/elc_geometry_validation.png"),
        help="Output PNG path.",
    )
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    render_top_view(
        DESIGN,
        args.out,
        unit_scale=1e-6,   # DESIGN is in nm; render in mm
        unit_label="mm",
        title="Schurig 2006 ELC -- top view (validation render)",
    )
    print(f"Wrote {args.out}")
    print("Compare against the CST 3D render and Schurig 2006 Fig 1(b).")


if __name__ == "__main__":
    main()
