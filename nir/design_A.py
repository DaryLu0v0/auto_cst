# nir/design_A.py -- the editable design for hypothesis A (metallic disk MIM).
#
# Each key maps 1:1 to a named CST parameter in the working project.
# Units: all lengths in NANOMETERS (nm).

DESIGN = {
    # Unit cell period (nm) -- square lattice
    "p": 1300.0,

    # Ag disk radius (nm) -- strongest lever on resonance position
    "r": 580.0,

    # Ag disk thickness (nm) -- weak lever, mostly affects Q
    "h": 105.98,

    # SiO2 spacer thickness (nm) -- secondary lever (cavity-disk coupling)
    "d": 100.0,

    # Au ground thickness (nm) -- fixed; just needs to be opaque (>= 50 nm)
    "t_ground": 100.0,

}
