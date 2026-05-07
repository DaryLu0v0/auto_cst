"""nir/constraints_B.py -- hard constraints for the rectangular-patch MIM (hypothesis B).

Patch params lx, ly are FULL LENGTHS (not semi-axes), so the clearance check
is lx <= p - margin (and same for ly), not 2*lx <= p - margin.
"""

MIN_PERIOD_NM = 700.0
MAX_PERIOD_NM = 1700.0

MIN_PATCH_LENGTH_NM = 200.0     # below this the patch resonance is poorly defined
# MAX is dynamic against period

MIN_DISK_THICKNESS_NM = 30.0
MAX_DISK_THICKNESS_NM = 200.0

MIN_SPACER_NM = 50.0
MAX_SPACER_NM = 400.0

MIN_GROUND_THICKNESS_NM = 50.0
MAX_GROUND_THICKNESS_NM = 200.0

# Geometric: patch must clear neighbors (at least 50 nm gap on each axis)
PATCH_PERIOD_MARGIN_NM = 50.0


def validate_design(d: dict) -> tuple[bool, str]:
    required = {"p", "lx", "ly", "h", "d", "t_ground"}
    missing = required - set(d.keys())
    if missing:
        return False, f"missing keys: {missing}"

    if d["p"] < MIN_PERIOD_NM:
        return False, f"period p ({d['p']:.1f}) < min {MIN_PERIOD_NM} nm"
    if d["p"] > MAX_PERIOD_NM:
        return False, f"period p ({d['p']:.1f}) > max {MAX_PERIOD_NM} nm"

    for axis_name in ("lx", "ly"):
        if d[axis_name] < MIN_PATCH_LENGTH_NM:
            return False, f"{axis_name} ({d[axis_name]:.1f}) < min {MIN_PATCH_LENGTH_NM} nm"

    max_length = d["p"] - PATCH_PERIOD_MARGIN_NM
    for axis_name in ("lx", "ly"):
        if d[axis_name] > max_length:
            return False, (
                f"{axis_name} ({d[axis_name]:.1f}) > p - {PATCH_PERIOD_MARGIN_NM} "
                f"= {max_length:.1f} nm: patch overlaps neighbor along this axis. "
                f"Increase p or decrease {axis_name}."
            )

    if d["h"] < MIN_DISK_THICKNESS_NM:
        return False, f"h ({d['h']:.2f}) < min {MIN_DISK_THICKNESS_NM} nm"
    if d["h"] > MAX_DISK_THICKNESS_NM:
        return False, f"h ({d['h']:.2f}) > max {MAX_DISK_THICKNESS_NM} nm"

    if d["d"] < MIN_SPACER_NM:
        return False, f"d ({d['d']:.2f}) < min {MIN_SPACER_NM} nm"
    if d["d"] > MAX_SPACER_NM:
        return False, f"d ({d['d']:.2f}) > max {MAX_SPACER_NM} nm"

    if d["t_ground"] < MIN_GROUND_THICKNESS_NM:
        return False, f"t_ground ({d['t_ground']:.1f}) < min {MIN_GROUND_THICKNESS_NM} nm"

    return True, ""


PARAM_BOUNDS = {
    "p": (MIN_PERIOD_NM, MAX_PERIOD_NM),
    "lx": (MIN_PATCH_LENGTH_NM, MAX_PERIOD_NM - PATCH_PERIOD_MARGIN_NM),
    "ly": (MIN_PATCH_LENGTH_NM, MAX_PERIOD_NM - PATCH_PERIOD_MARGIN_NM),
    "h": (MIN_DISK_THICKNESS_NM, MAX_DISK_THICKNESS_NM),
    "d": (MIN_SPACER_NM, MAX_SPACER_NM),
    "t_ground": (MIN_GROUND_THICKNESS_NM, MAX_GROUND_THICKNESS_NM),
}
