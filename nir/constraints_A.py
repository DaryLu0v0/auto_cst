"""nir/constraints_A.py -- hard fabrication and geometry rules for the disk MIM.

Independent of the project-root `constraints.py` (which is THz-specific).
All values in NANOMETERS to match design_A.py.
"""


# ---------------------------------------------------------------------------
# NIR fabrication / geometric limits (E-beam lithography on Au/SiO2)
# ---------------------------------------------------------------------------
MIN_PERIOD_NM = 700.0       # below 700 nm risks 1st-order grating diffraction at 1550 nm
MAX_PERIOD_NM = 1500.0      # above 1500 nm is too sparse, weakens absorber

MIN_DISK_RADIUS_NM = 200.0  # below ~200 nm the plasmonic disk mode is poorly defined
                            # MAX is enforced dynamically against period (see below)

MIN_DISK_THICKNESS_NM = 30.0
MAX_DISK_THICKNESS_NM = 200.0

MIN_SPACER_NM = 50.0        # below 50 nm risks pinhole shorts to ground
MAX_SPACER_NM = 400.0       # above 400 nm decouples disk from cavity mode

MIN_GROUND_THICKNESS_NM = 50.0
MAX_GROUND_THICKNESS_NM = 200.0

# Geometric: disk must clear neighbors -- diameter < period - margin
# Lit-review baseline (rank 2) leaves ~80 nm gap (39 nm per side), so 50 nm margin (25 nm/side)
# is the threshold that admits the baseline while still preventing disk-disk overlap.
DISK_PERIOD_MARGIN_NM = 50.0    # require 2*r <= p - 50


def validate_design(d: dict) -> tuple[bool, str]:
    """Check all hard constraints. Returns (ok, reason)."""

    # --- Required keys ---
    required = {"p", "r", "h", "d", "t_ground"}
    missing = required - set(d.keys())
    if missing:
        return False, f"missing keys: {missing}"

    # --- Fabrication bounds ---
    if d["p"] < MIN_PERIOD_NM:
        return False, f"period p ({d['p']:.1f} nm) < min {MIN_PERIOD_NM} nm"
    if d["p"] > MAX_PERIOD_NM:
        return False, f"period p ({d['p']:.1f} nm) > max {MAX_PERIOD_NM} nm"

    if d["r"] < MIN_DISK_RADIUS_NM:
        return False, f"disk radius r ({d['r']:.1f} nm) < min {MIN_DISK_RADIUS_NM} nm"

    if d["h"] < MIN_DISK_THICKNESS_NM:
        return False, f"disk thickness h ({d['h']:.2f} nm) < min {MIN_DISK_THICKNESS_NM} nm"
    if d["h"] > MAX_DISK_THICKNESS_NM:
        return False, f"disk thickness h ({d['h']:.2f} nm) > max {MAX_DISK_THICKNESS_NM} nm"

    if d["d"] < MIN_SPACER_NM:
        return False, f"spacer d ({d['d']:.2f} nm) < min {MIN_SPACER_NM} nm"
    if d["d"] > MAX_SPACER_NM:
        return False, f"spacer d ({d['d']:.2f} nm) > max {MAX_SPACER_NM} nm"

    if d["t_ground"] < MIN_GROUND_THICKNESS_NM:
        return False, f"ground t_ground ({d['t_ground']:.1f} nm) < min {MIN_GROUND_THICKNESS_NM} nm"
    if d["t_ground"] > MAX_GROUND_THICKNESS_NM:
        return False, f"ground t_ground ({d['t_ground']:.1f} nm) > max {MAX_GROUND_THICKNESS_NM} nm"

    # --- Geometric consistency: disk fits inside unit cell with clearance ---
    max_radius_for_period = (d["p"] - DISK_PERIOD_MARGIN_NM) / 2.0
    if d["r"] > max_radius_for_period:
        return False, (
            f"disk radius r ({d['r']:.1f} nm) > (p - margin)/2 "
            f"= ({d['p']:.1f} - {DISK_PERIOD_MARGIN_NM})/2 = {max_radius_for_period:.1f} nm: "
            f"disk overlaps neighboring cell. Increase p or decrease r."
        )

    return True, ""


# Hard bounds exposed for the agent prompt + runtime checking
PARAM_BOUNDS = {
    "p": (MIN_PERIOD_NM, MAX_PERIOD_NM),
    "r": (MIN_DISK_RADIUS_NM, (MAX_PERIOD_NM - DISK_PERIOD_MARGIN_NM) / 2.0),
    "h": (MIN_DISK_THICKNESS_NM, MAX_DISK_THICKNESS_NM),
    "d": (MIN_SPACER_NM, MAX_SPACER_NM),
    "t_ground": (MIN_GROUND_THICKNESS_NM, MAX_GROUND_THICKNESS_NM),
}


if __name__ == "__main__":
    from design_A import DESIGN
    ok, reason = validate_design(DESIGN)
    if ok:
        print("Baseline disk-MIM design: VALID")
    else:
        print(f"Baseline disk-MIM design: INVALID -- {reason}")
