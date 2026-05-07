# nir/design_B.py -- editable design for hypothesis B (rectangular-patch MIM).
#
# Polarization-sensitive (lx != ly). Unit: NANOMETERS.

DESIGN = {
    # Unit cell period (nm) -- square lattice
    "p": 1400.0,

    # Patch full length along x (nm) -- LONG axis, tunes one polarization
    "lx": 500.0,

    # Patch full length along y (nm) -- SHORT axis, tunes the other polarization
    "ly": 1100.0,

    # Ag patch thickness (nm) -- weak lever
    "h": 100.0,

    # SiO2 spacer thickness (nm) -- secondary lever
    "d": 200.0,

    # Au ground thickness (nm) -- fixed
    "t_ground": 100.0,

}
