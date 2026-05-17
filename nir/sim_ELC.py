"""Schurig 2006 ELC — simulation context for the inno-ml-design pipeline.

Pairs with `design_ELC.py` (param defaults), `constraints_ELC.py` (fab rules),
and `geometry_elc.py` (VBA emitter). Exports `HYPOTHESIS`, a HypothesisSpec
instance that the skill's `build_and_solve` consumes.

To add a new hypothesis (e.g., a fishnet at 100 GHz on quartz), write a
sim_<id>.py mirroring this file: construct UnitSpec / BoundarySpec /
FloquetPortSpec / MaterialSpec tuples, point the function fields at the
hypothesis's geometry module, and declare the channels.

This module imports HypothesisSpec from the skill via dynamic path resolution
so auto_cst doesn't need a hard dependency on MetaClaw — drop the file in a
different auto_cst checkout, set METACLAW_SKILLS_DIR, and it still works.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Resolve the skill scripts dir (where _cst_template lives).
_SKILLS_DIR = Path(os.environ.get(
    "METACLAW_SKILLS_DIR",
    "D:/Claude/MetaClaw/skills/inno-ml-design/scripts",
)).resolve()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

from _cst_template import (  # noqa: E402
    BoundarySpec, FloquetPortSpec, HypothesisSpec, MaterialSpec, UnitSpec,
)

from nir.constraints_ELC import validate_design  # noqa: E402
from nir.geometry_elc import (  # noqa: E402
    build_elc_geometry_vba, expected_solid_names, render_top_view,
)


# Schurig 2006 FR4 (fitted): eps' = 3.75, eps'' = 0.084. Equivalent
# tan(δ) = 0.084 / 3.75 = 0.0224. Other vendors quote 0.018-0.025 depending
# on resin; this is the paper's value, kept for reproducibility.
_FR4_EPS_REAL = 3.75
_FR4_TAND = 0.084 / _FR4_EPS_REAL


HYPOTHESIS = HypothesisSpec(
    id="ELC",
    long_name="Schurig 2006 ELC (closed frame + two T-fingers on FR4+Cu)",

    units=UnitSpec(
        length="mm",
        frequency="GHz",
        time="ns",
        param_unit_scale=1e-6,  # nm -> mm (skill stores geometry in nm)
    ),
    boundary=BoundarySpec(
        # Periodic in X/Y (unit-cell), open in Z. PEC on Xmin/Xmax (set
        # implicitly by the "unit cell" macro per Floquet symmetry) forces E
        # along x, which is perpendicular to the ELC capacitor plates and
        # drives the resonance.
        xmin="unit cell", xmax="unit cell",
        ymin="unit cell", ymax="unit cell",
        zmin="expanded open", zmax="expanded open",
    ),
    port=FloquetPortSpec(n_modes=2),

    materials=(
        MaterialSpec(
            name="FR4", type="Normal",
            epsilon=_FR4_EPS_REAL, mu=1.0, kappa=0.0,
            tand=_FR4_TAND, tand_model="ConstTanD",
            colour=(0.0, 0.6, 0.1),
        ),
        # PEC is a CST 2026 built-in — declared here for documentation only;
        # to_vba() returns "" so no VBA is emitted.
        MaterialSpec(name="PEC", type="PEC"),
    ),

    geometry_vba_fn=build_elc_geometry_vba,
    expected_solids_fn=expected_solid_names,
    validate_design_fn=validate_design,
    render_top_view_fn=render_top_view,

    # Vacuum padding above/below the substrate (mm). expanded-open auto-extends
    # but we add explicit pads to make port placement deterministic.
    extra_params={"air_extent": 10.0},

    # Channels the runner can export. Stage 11 trains on `primary_channel`
    # by default; Stage 13 / NRW can use the complex pair for permittivity
    # extraction.
    channels=("S11_mag", "S21_mag", "S11_complex", "S21_complex"),
    primary_channel="S21_mag",
)
