"""nir/geometry_ellipse.py -- VBA builder for hypothesis B (rectangular-patch MIM).

NOTE: Originally planned as elliptical disk per the rank-1 paper figure, but
CST VBA for both ExtrudeCurve+Translate and Cylinder+Transform.Scale failed
on this CST install (ActiveX 10091: no such property/method). Pivoted to a
RECTANGULAR PATCH which uses the same Brick primitive proven in
run_midIR_v3.py. Polarization sensitivity is preserved via lx != ly.

Stack:
    +-----------------------------+   z = t_ground + d + h
    |  Ag rectangular patch (lx,ly,h) |
    +-----------------------------+   z = t_ground + d
    |       SiO2 spacer (d)         |
    +-----------------------------+   z = t_ground
    |       Au ground (t_ground)    |
    +-----------------------------+   z = 0

Params:
    p        : square unit cell period (nm)
    lx, ly   : patch full lengths along x and y (nm) -- can differ for
               polarization-sensitive resonance
    h        : Ag patch thickness (nm)
    d        : SiO2 spacer thickness (nm)
    t_ground : Au ground thickness (nm)
"""
from __future__ import annotations
from typing import Dict


def build_ellipse_geometry_vba(params: Dict[str, float]) -> str:
    """Build the rectangular-patch-on-MIM unit cell.

    The function name is kept (`build_ellipse_geometry_vba`) for backward
    compatibility with the runner's hypothesis dispatch; it now builds a
    rectangular patch instead of an ellipse for VBA reliability.
    """
    required = {"p", "lx", "ly", "h", "d", "t_ground"}
    missing = required - set(params.keys())
    if missing:
        raise KeyError(f"build_ellipse_geometry_vba: missing params: {missing}")

    return "\n".join([
        # --- Au ground ---
        "With Brick",
        "  .Reset",
        '  .Name "ground"',
        '  .Component "absorber"',
        '  .Material "Au_lossy"',
        '  .Xrange "-p/2", "p/2"',
        '  .Yrange "-p/2", "p/2"',
        '  .Zrange "0", "t_ground"',
        "  .Create",
        "End With",
        "",
        # --- SiO2 spacer ---
        "With Brick",
        "  .Reset",
        '  .Name "spacer"',
        '  .Component "absorber"',
        '  .Material "SiO2"',
        '  .Xrange "-p/2", "p/2"',
        '  .Yrange "-p/2", "p/2"',
        '  .Zrange "t_ground", "t_ground + d"',
        "  .Create",
        "End With",
        "",
        # --- Ag rectangular patch (lx by ly, centered) ---
        "With Brick",
        "  .Reset",
        '  .Name "patch"',
        '  .Component "absorber"',
        '  .Material "Ag_lossy"',
        '  .Xrange "-lx/2", "lx/2"',
        '  .Yrange "-ly/2", "ly/2"',
        '  .Zrange "t_ground + d", "t_ground + d + h"',
        "  .Create",
        "End With",
    ])
