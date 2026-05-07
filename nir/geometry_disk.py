"""nir/geometry_disk.py -- VBA builder for the disk-MIM absorber unit cell.

Hypothesis A geometry (from doi:10.1039/d2ra05617h, lambda-scaled to 1550 nm):

    +-----------------------------+   z = t_ground + d + h
    |   Ag disk (cylinder, r,h)   |
    |       (centered)            |   z = t_ground + d
    +-----------------------------+
    |       SiO2 spacer (d)       |
    +-----------------------------+   z = t_ground
    |       Au ground (t_ground)  |
    +-----------------------------+   z = 0

Unit cell:  -p/2 .. +p/2  in X and Y  (square lattice).
Boundaries: unit cell in X/Y, expanded open in Z.
"""
from __future__ import annotations

from typing import Dict


def build_disk_geometry_vba(params: Dict[str, float]) -> str:
    """Generate VBA for the disk-MIM unit cell.

    Expects params with keys: p, r, h, d, t_ground (all in nm, written
    earlier as StoreDoubleParameter so we reference them by NAME here).

    The 4 solids created (in order):
      absorber:ground   -- Au_lossy brick spanning the unit cell
      absorber:spacer   -- SiO2 brick spanning the unit cell
      absorber:disk     -- Ag_lossy cylinder (z-aligned), centered

    No diff/boolean ops needed -- the disk sits on top of the spacer; the
    background (vacuum) fills the rest.
    """
    # Sanity check -- the runner will also validate but a clear error here
    # beats a cryptic VBA failure.
    required = {"p", "r", "h", "d", "t_ground"}
    missing = required - set(params.keys())
    if missing:
        raise KeyError(f"build_disk_geometry_vba: missing params: {missing}")

    return "\n".join([
        # --- Au ground plane: full unit cell, z=[0, t_ground] ---
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
        # --- SiO2 spacer: full unit cell, z=[t_ground, t_ground + d] ---
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
        # --- Ag disk: cylinder centered at origin, height h above spacer ---
        "With Cylinder",
        "  .Reset",
        '  .Name "disk"',
        '  .Component "absorber"',
        '  .Material "Ag_lossy"',
        '  .Axis "z"',
        '  .Outerradius "r"',
        '  .Innerradius "0"',
        '  .Xcenter "0"',
        '  .Ycenter "0"',
        '  .Zrange "t_ground + d", "t_ground + d + h"',
        '  .Segments "0"',
        "  .Create",
        "End With",
    ])
