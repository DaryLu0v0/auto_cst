# design.py -- the ONLY file the agent is allowed to edit
# This is the CST equivalent of train.py in autoresearch.
#
# Each key maps 1:1 to a named CST parameter in the template project.
# Units: all lengths in micrometers (um), matching CST project units.

DESIGN = {
    # Unit cell period (um)
    "p": 84.0,

    # Outer SRR square dimension (um)
    "outer_srr": 82.0,

    # Metal trace width (um)
    "w": 2.0,

    # Split gap width (um) -- capacitive gap
    "gap": 0.42,

    # Metal (Gold) thickness (um)
    "t_m": 0.1,

    # Substrate (Silicon) thickness (um)
    "st": 30.0,

    # Coupling arm length (um)
    "length_arm": 27.0,

}
