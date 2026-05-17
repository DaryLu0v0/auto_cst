# nir/design_ELC.py -- editable design for hypothesis ELC (Schurig 2006 ELC at 11 GHz).
#
# Each key maps 1:1 to a named CST parameter in the working project.
# Units: all lengths in NANOMETERS (nm), matching the nir/A and nir/B convention.
#
# Topology: two adjacent rectangular Cu loops on FR4, sharing a central capacitor
# gap. Linear-scaled from Schurig/Mock/Smith APL 2006 (paper f_peak = 13.5 GHz,
# operating at a = 3.333 mm) to f_peak = 11 GHz at a = 4.09 mm (scale ratio 1.227).
#
# Polarization: E perpendicular to the capacitor plates (i.e. along x in the
# build_elc_geometry_vba convention) excites the resonance. Enforced in the
# CST project by Xmin/Xmax = PEC, Ymin/Ymax = PMC boundary conditions.

DESIGN = {
    # Unit cell period (nm) -- square lattice, sets the lattice constant.
    # Linear-scaled from Schurig 2006 (a = 3.333 mm @ 13.5 GHz) by 1.227x to
    # bring the resonance to 11 GHz. The geometry_elc.py topology now correctly
    # implements Schurig Fig 1(b) (closed outer frame + two T-fingers), so
    # this linear scaling should land near 11 GHz directly without the
    # additional 1.7653x correction that was needed when the topology was wrong.
    "a": 4090500.0,

    # ELC pattern outer extent (nm) -- size of the outer rectangular frame.
    "d": 3681818.0,

    # Capacitor plate length (nm) -- horizontal extent of each T-finger's
    # crossbar (the capacitor plate). Strongest geometric lever on resonance.
    "l": 1227273.0,

    # Conductor line width (nm) -- linewidth of every metal trace (outer
    # frame rails, T spines, T plates).
    "w": 306818.0,

    # Capacitor gap (nm) -- vertical separation between the top and bottom
    # plates. Weak lever on resonance position, strong lever on Q.
    "g": 306818.0,

    # FR4 substrate thickness (nm) -- standard PCB stock. 0.203 mm = 8 mil.
    "h_FR4": 203000.0,

    # Cu cladding thickness (nm) -- half-ounce Cu (~17 um).
    # Skin depth at 11 GHz is ~0.65 um, so 17 um is electrically perfect.
    "t_Cu": 17000.0,
}
