"""nir/constraints_C.py -- constraints for the planar MIM (hypothesis C)."""

MIN_PERIOD_NM = 200.0           # planar -> period ~ irrelevant, just keep mesh small
MAX_PERIOD_NM = 1000.0

MIN_TOP_THICKNESS_NM = 3.0      # Cr below 3 nm risks discontinuous film
MAX_TOP_THICKNESS_NM = 50.0     # too thick = mostly reflective, no resonance

MIN_CAVITY_NM = 80.0            # below 80 nm cavity is too thin for FP
MAX_CAVITY_NM = 600.0           # above 600 nm = higher-order FP modes appear in 100-300 THz

MIN_GROUND_THICKNESS_NM = 50.0
MAX_GROUND_THICKNESS_NM = 200.0


def validate_design(d: dict) -> tuple[bool, str]:
    required = {"p", "t_top", "d", "t_ground"}
    missing = required - set(d.keys())
    if missing:
        return False, f"missing keys: {missing}"

    if d["p"] < MIN_PERIOD_NM:
        return False, f"period p ({d['p']:.1f}) < min {MIN_PERIOD_NM} nm"
    if d["p"] > MAX_PERIOD_NM:
        return False, f"period p ({d['p']:.1f}) > max {MAX_PERIOD_NM} nm"

    if d["t_top"] < MIN_TOP_THICKNESS_NM:
        return False, f"t_top ({d['t_top']:.2f}) < min {MIN_TOP_THICKNESS_NM} nm"
    if d["t_top"] > MAX_TOP_THICKNESS_NM:
        return False, f"t_top ({d['t_top']:.2f}) > max {MAX_TOP_THICKNESS_NM} nm"

    if d["d"] < MIN_CAVITY_NM:
        return False, f"d ({d['d']:.2f}) < min {MIN_CAVITY_NM} nm"
    if d["d"] > MAX_CAVITY_NM:
        return False, f"d ({d['d']:.2f}) > max {MAX_CAVITY_NM} nm"

    if d["t_ground"] < MIN_GROUND_THICKNESS_NM:
        return False, f"t_ground ({d['t_ground']:.1f}) < min {MIN_GROUND_THICKNESS_NM} nm"
    if d["t_ground"] > MAX_GROUND_THICKNESS_NM:
        return False, f"t_ground ({d['t_ground']:.1f}) > max {MAX_GROUND_THICKNESS_NM} nm"

    return True, ""


PARAM_BOUNDS = {
    "p": (MIN_PERIOD_NM, MAX_PERIOD_NM),
    "t_top": (MIN_TOP_THICKNESS_NM, MAX_TOP_THICKNESS_NM),
    "d": (MIN_CAVITY_NM, MAX_CAVITY_NM),
    "t_ground": (MIN_GROUND_THICKNESS_NM, MAX_GROUND_THICKNESS_NM),
}
