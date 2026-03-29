"""constraints.py -- hard geometry rules for 5x5 CWC absorber.

DO NOT MODIFY this file during agent runs.

Each CWC cell (i,j) has:
  x_i_j : margin (um) -- distance from unit cell edge to outer ring edge
  g_i_j : gap (um) -- gap in the complementary wire circle
  w_i_j : width (um) -- ring metal width

Derived (computed inside CST):
  r1_i_j = a/2 - x_i_j   (outer radius)
  r2_i_j = r1_i_j - w_i_j (inner radius)

Fixed: a = 4.0 um (pitch for all cells)

All values in micrometers (um).
"""

# ---------------------------------------------------------------------------
# Fixed constants
# ---------------------------------------------------------------------------
PITCH = 4.0  # um, fixed for all cells

# ---------------------------------------------------------------------------
# Tunable parameter bounds
# ---------------------------------------------------------------------------
MIN_X = 0.1     # minimum margin
MAX_X = 1.8     # maximum margin (leaves r1 >= 0.2 um)
MIN_W = 0.05    # minimum ring width
MAX_W = 1.5     # maximum ring width
MIN_G = 0.1     # minimum gap
MAX_G = 3.5     # maximum gap
MIN_R1 = 0.15   # minimum outer radius
MIN_R2 = 0.02   # minimum inner radius


def validate_design(d: dict) -> tuple[bool, str]:
    """Check all hard constraints. Returns (ok, reason)."""

    for i in range(5):
        for j in range(5):
            tag = f"cell ({i},{j})"
            x_key = f"x_{i}_{j}"
            g_key = f"g_{i}_{j}"
            w_key = f"w_{i}_{j}"

            x = d[x_key]
            g = d[g_key]
            w = d[w_key]

            # --- bound checks ---
            if x < MIN_X:
                return False, f"{tag}: x={x:.4f} < min {MIN_X}"
            if x > MAX_X:
                return False, f"{tag}: x={x:.4f} > max {MAX_X}"
            if w < MIN_W:
                return False, f"{tag}: w={w:.4f} < min {MIN_W}"
            if w > MAX_W:
                return False, f"{tag}: w={w:.4f} > max {MAX_W}"
            if g < MIN_G:
                return False, f"{tag}: g={g:.4f} < min {MIN_G}"
            if g > MAX_G:
                return False, f"{tag}: g={g:.4f} > max {MAX_G}"

            # --- derived geometry checks ---
            r1 = PITCH / 2.0 - x  # outer radius
            if r1 < MIN_R1:
                return False, (
                    f"{tag}: r1 = a/2 - x = {r1:.4f} < min {MIN_R1} "
                    f"(x={x:.4f} too large)"
                )

            r2 = r1 - w  # inner radius
            if r2 < MIN_R2:
                return False, (
                    f"{tag}: r2 = r1 - w = {r2:.4f} < min {MIN_R2} "
                    f"(x={x:.4f}, w={w:.4f})"
                )

            # --- cross-arm constraint ---
            # The CWC cross arm spans from (cx - r2) to (cx - g/2).
            # For a valid arm with positive length: r2 > g/2, i.e. g < 2*r2.
            if g >= 2.0 * r2:
                return False, (
                    f"{tag}: g={g:.4f} >= 2*r2={2*r2:.4f} "
                    f"(cross arm has zero/negative length; "
                    f"need g < 2*(a/2 - x - w) = {2*r2:.4f})"
                )

    return True, ""


if __name__ == "__main__":
    from design import DESIGN
    ok, reason = validate_design(DESIGN)
    if ok:
        print("Current design: VALID")
    else:
        print(f"Current design: INVALID -- {reason}")
