"""nir/geometry_planar.py -- VBA builder for the planar MIM (hypothesis C).

Three-layer Fabry-Perot stack, no lateral patterning:

    +-----------------------------+   z = t_ground + d + t_top
    |   Ag top layer (t_top)      |   <- semi-transparent, ~8-15 nm
    +-----------------------------+   z = t_ground + d
    |   SiO2 cavity (d)           |   <- quarter-wave at target wavelength
    +-----------------------------+   z = t_ground
    |   Au ground (t_ground)      |   <- opaque mirror
    +-----------------------------+   z = 0

NOTE: originally specced with Cr_lossy as the top layer (per the
'lithography-free' paper's mention of Cr), but constant-sigma Cr at NIR
underestimates absorption -- the smoke test gave abs=0.0 everywhere.
Using thin Ag instead (proven in hypothesis A's MIM stack) for the
same Salisbury-screen physics.
"""
from __future__ import annotations
from typing import Dict


def build_planar_geometry_vba(params: Dict[str, float]) -> str:
    required = {"p", "t_top", "d", "t_ground"}
    missing = required - set(params.keys())
    if missing:
        raise KeyError(f"build_planar_geometry_vba: missing params: {missing}")

    return "\n".join([
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
        "With Brick",
        "  .Reset",
        '  .Name "cavity"',
        '  .Component "absorber"',
        '  .Material "SiO2"',
        '  .Xrange "-p/2", "p/2"',
        '  .Yrange "-p/2", "p/2"',
        '  .Zrange "t_ground", "t_ground + d"',
        "  .Create",
        "End With",
        "",
        "With Brick",
        "  .Reset",
        '  .Name "top_layer"',
        '  .Component "absorber"',
        '  .Material "Ag_lossy"',
        '  .Xrange "-p/2", "p/2"',
        '  .Yrange "-p/2", "p/2"',
        '  .Zrange "t_ground + d", "t_ground + d + t_top"',
        "  .Create",
        "End With",
    ])
