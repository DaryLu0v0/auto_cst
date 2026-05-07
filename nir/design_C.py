# nir/design_C.py -- editable design for hypothesis C (planar Au/SiO2/Cr MIM).
#
# Lithography-free Fabry-Perot absorber, no lateral patterning.
# Units: NANOMETERS.

DESIGN = {
    # Unit cell period (nm) -- arbitrary; planar structure is uniform
    "p": 500.0,

    # Ag top layer thickness (nm) -- secondary lever (controls Q)
    "t_top": 8.0,

    # SiO2 cavity thickness (nm) -- STRONGEST lever (Fabry-Perot peak)
    "d": 450.0,

    # Au ground thickness (nm) -- fixed
    "t_ground": 100.0,

}
