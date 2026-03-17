"""constraints.py -- hard fabrication and geometry rules.

DO NOT MODIFY this file during agent runs.

These constraints encode physical fabrication limits and geometric
consistency rules.  The agent should never discover these limits by
crashing; they are checked BEFORE any CST simulation is launched.

All values in micrometers (um) to match the CST project units.
"""


# ---------------------------------------------------------------------------
# Fabrication limits (typical THz lithography on silicon)
# ---------------------------------------------------------------------------
MIN_GAP_UM = 0.4          # minimum resolvable gap
MIN_LINEWIDTH_UM = 1.0    # minimum metal trace width
MIN_METAL_THICKNESS_UM = 0.05   # thinnest depositable gold layer
MAX_METAL_THICKNESS_UM = 1.0    # practical upper bound
MIN_SUBSTRATE_UM = 5.0    # minimum substrate for mechanical handling
MAX_SUBSTRATE_UM = 100.0  # practical upper bound
MIN_PERIOD_UM = 10.0      # smallest useful unit cell
MAX_PERIOD_UM = 300.0     # largest before higher-order diffraction issues
MIN_ARM_LENGTH_UM = 2.0   # minimum coupling arm


def validate_design(d: dict) -> tuple[bool, str]:
    """Check all hard constraints.  Returns (ok, reason)."""

    # --- fabrication minimums ---
    if d["gap"] < MIN_GAP_UM:
        return False, f"gap ({d['gap']:.2f} um) < minimum {MIN_GAP_UM} um"

    if d["w"] < MIN_LINEWIDTH_UM:
        return False, f"linewidth w ({d['w']:.2f} um) < minimum {MIN_LINEWIDTH_UM} um"

    if d["t_m"] < MIN_METAL_THICKNESS_UM:
        return False, f"metal thickness ({d['t_m']:.3f} um) < minimum {MIN_METAL_THICKNESS_UM} um"

    if d["t_m"] > MAX_METAL_THICKNESS_UM:
        return False, f"metal thickness ({d['t_m']:.3f} um) > maximum {MAX_METAL_THICKNESS_UM} um"

    if d["st"] < MIN_SUBSTRATE_UM:
        return False, f"substrate ({d['st']:.1f} um) < minimum {MIN_SUBSTRATE_UM} um"

    if d["st"] > MAX_SUBSTRATE_UM:
        return False, f"substrate ({d['st']:.1f} um) > maximum {MAX_SUBSTRATE_UM} um"

    if d["p"] < MIN_PERIOD_UM:
        return False, f"period ({d['p']:.1f} um) < minimum {MIN_PERIOD_UM} um"

    if d["p"] > MAX_PERIOD_UM:
        return False, f"period ({d['p']:.1f} um) > maximum {MAX_PERIOD_UM} um"

    if d["length_arm"] < MIN_ARM_LENGTH_UM:
        return False, f"arm length ({d['length_arm']:.1f} um) < minimum {MIN_ARM_LENGTH_UM} um"

    # --- geometric consistency ---
    if d["outer_srr"] >= d["p"]:
        return False, (
            f"outer_srr ({d['outer_srr']:.1f} um) >= period ({d['p']:.1f} um): "
            "SRR exceeds unit cell"
        )

    if d["outer_srr"] <= 2 * d["w"]:
        return False, (
            f"outer_srr ({d['outer_srr']:.1f} um) <= 2*w ({2*d['w']:.1f} um): "
            "no interior space for SRR ring"
        )

    inner_srr = d["outer_srr"] - 2 * d["w"]
    if d["gap"] >= inner_srr:
        return False, (
            f"gap ({d['gap']:.2f} um) >= inner SRR dimension ({inner_srr:.1f} um): "
            "gap wider than inner ring"
        )

    # arm must fit between gap edge and ring edge
    arm_span = (d["outer_srr"] / 2 - d["w"]) - (d["gap"] / 2 + d["w"])
    if arm_span <= 0:
        return False, (
            f"no room for horizontal arm: (outer_srr/2 - w) - (gap/2 + w) = {arm_span:.2f} um"
        )

    if d["length_arm"] >= d["outer_srr"]:
        return False, (
            f"length_arm ({d['length_arm']:.1f} um) >= outer_srr ({d['outer_srr']:.1f} um)"
        )

    # --- all checks passed ---
    return True, ""


if __name__ == "__main__":
    # Quick self-test with the baseline design
    from design import DESIGN
    ok, reason = validate_design(DESIGN)
    if ok:
        print("Baseline design: VALID")
    else:
        print(f"Baseline design: INVALID -- {reason}")
