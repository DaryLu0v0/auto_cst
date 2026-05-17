"""nir/constraints_ELC.py -- hard fabrication and geometry rules for the
Schurig 2006 ELC topology on FR4+Cu PCB at microwave frequencies.

Independent of the project-root `constraints.py` (which is THz-specific).
All values in NANOMETERS to match design_ELC.py.

Fab rules: standard PCB lithography (e.g. OSHPark 4-layer, Sunstone, etc.):
  - min linewidth and gap: 100 um (4 mil)
  - copper thickness from standard cladding weights (0.5 / 1 / 2 oz)
  - substrate thickness from common FR4 stock dimensions
"""

# ---------------------------------------------------------------------------
# PCB fabrication limits (standard photolithography on FR4)
# ---------------------------------------------------------------------------
MIN_LINEWIDTH_NM = 100_000.0   # 0.1 mm = 4 mil. Standard PCB rule.
MIN_GAP_NM       = 100_000.0   # 0.1 mm = 4 mil.

# Allowed substrate thicknesses (nm). Standard FR4 stock:
#   0.203 mm = 8 mil (used by Schurig 2006)
#   0.254 mm = 10 mil
#   0.508 mm = 20 mil
#   0.762 mm = 30 mil
#   1.524 mm = 60 mil (the most common "1/16 inch" stock)
ALLOWED_H_FR4_NM = {203_000.0, 254_000.0, 508_000.0, 762_000.0, 1_524_000.0}

# Allowed copper cladding thicknesses (nm). Half / one / two ounce weights:
#   0.017 mm = 17 um  = 0.5 oz/ft^2
#   0.035 mm = 35 um  = 1.0 oz/ft^2
#   0.070 mm = 70 um  = 2.0 oz/ft^2
ALLOWED_T_CU_NM = {17_000.0, 35_000.0, 70_000.0}

# Tolerance for matching against the discrete stock sets (nm).
STOCK_TOL_NM = 1_000.0   # 1 um -- PCB fab variability dwarfs this.

# ---------------------------------------------------------------------------
# Microwave / EM coherence bounds (electrical rather than fab)
# ---------------------------------------------------------------------------
# Period must stay below the first-order grating opening at f_max = 18 GHz on
# air-side, i.e. lambda_0/n_air = 16.7 mm. We are well below this with 4 mm,
# but enforce a soft upper bound to keep the design space sensible.
MIN_PERIOD_NM =  1_000_000.0     # 1 mm   (well above PCB fab limits)
MAX_PERIOD_NM = 10_000_000.0     # 10 mm  (below grating lobe at 18 GHz)

# Pattern outer extent d must fit inside the unit cell with margin.
MIN_PATTERN_MARGIN_NM = 100_000.0   # 0.1 mm clearance from neighbor cell

# Capacitor plate length and gap bounds (within fab + electrical sanity).
MIN_PLATE_LENGTH_NM =   200_000.0   # 0.2 mm -- below this the cap is too small
MAX_PLATE_LENGTH_NM = 5_000_000.0
MIN_GAP_PHYSICAL_NM = MIN_GAP_NM
MAX_GAP_NM          = 2_000_000.0   # 2 mm -- above this the cap is too weak


def _is_in_stock(value: float, allowed: set, tol: float = STOCK_TOL_NM) -> bool:
    """Return True if `value` (nm) matches any entry in `allowed` to within `tol`."""
    return any(abs(value - v) <= tol for v in allowed)


def validate_design(d: dict) -> tuple[bool, str]:
    """Check all hard constraints. Returns (ok, reason).

    Expected keys (all in nm): a, d, l, w, g, h_FR4, t_Cu.
    """
    required = {"a", "d", "l", "w", "g", "h_FR4", "t_Cu"}
    missing = required - set(d.keys())
    if missing:
        return False, f"missing keys: {missing}"

    # --- Fabrication: linewidth + gap ---
    if d["w"] < MIN_LINEWIDTH_NM:
        return False, (
            f"line width w ({d['w']/1000:.1f} um) < min "
            f"{MIN_LINEWIDTH_NM/1000:.0f} um (PCB fab limit)"
        )
    if d["g"] < MIN_GAP_NM:
        return False, (
            f"capacitor gap g ({d['g']/1000:.1f} um) < min "
            f"{MIN_GAP_NM/1000:.0f} um (PCB fab limit)"
        )

    # --- Fabrication: discrete stock thicknesses ---
    if not _is_in_stock(d["h_FR4"], ALLOWED_H_FR4_NM):
        allowed_mm = sorted(v / 1_000_000.0 for v in ALLOWED_H_FR4_NM)
        return False, (
            f"FR4 thickness h_FR4 ({d['h_FR4']/1_000_000.0:.3f} mm) not in "
            f"allowed PCB stock {allowed_mm} mm"
        )
    if not _is_in_stock(d["t_Cu"], ALLOWED_T_CU_NM):
        allowed_um = sorted(v / 1000.0 for v in ALLOWED_T_CU_NM)
        return False, (
            f"Cu thickness t_Cu ({d['t_Cu']/1000.0:.1f} um) not in "
            f"allowed cladding stock {allowed_um} um"
        )

    # --- EM-coherence bounds ---
    if d["a"] < MIN_PERIOD_NM:
        return False, f"period a ({d['a']/1_000_000.0:.2f} mm) < min {MIN_PERIOD_NM/1_000_000.0:.2f} mm"
    if d["a"] > MAX_PERIOD_NM:
        return False, f"period a ({d['a']/1_000_000.0:.2f} mm) > max {MAX_PERIOD_NM/1_000_000.0:.2f} mm (grating lobe risk)"

    if d["l"] < MIN_PLATE_LENGTH_NM:
        return False, f"plate length l ({d['l']/1000.0:.0f} um) < min {MIN_PLATE_LENGTH_NM/1000.0:.0f} um"
    if d["l"] > MAX_PLATE_LENGTH_NM:
        return False, f"plate length l ({d['l']/1000.0:.0f} um) > max {MAX_PLATE_LENGTH_NM/1000.0:.0f} um"

    if d["g"] > MAX_GAP_NM:
        return False, f"capacitor gap g ({d['g']/1000.0:.0f} um) > max {MAX_GAP_NM/1000.0:.0f} um"

    # --- Geometric consistency (Schurig 2006 Fig 1(b) topology) ---
    # 1. Pattern extent must fit inside unit cell with margin.
    margin = (d["a"] - d["d"]) / 2.0
    if margin < MIN_PATTERN_MARGIN_NM:
        return False, (
            f"pattern margin (a - d)/2 = {margin/1000.0:.0f} um < "
            f"{MIN_PATTERN_MARGIN_NM/1000.0:.0f} um: ELC pattern too close to "
            f"neighbor cell, will couple unphysically. Increase a or decrease d."
        )

    # 2. T-finger spine must have positive length.
    # Top spine y-range: [g/2 + w, d/2 - w]. Length = (d - g - 4w) / 2 > 0.
    spine_length = (d["d"] - d["g"] - 4.0 * d["w"]) / 2.0
    if spine_length <= 0:
        return False, (
            f"T-finger spine length = (d - g - 4w)/2 = "
            f"{spine_length/1000.0:.0f} um <= 0: spine collapses. Reduce g/w "
            f"or increase d."
        )

    # 3. Capacitor plate must fit between the left and right outer rails.
    # Plate x-range: [-l/2, l/2]. Must satisfy l/2 + w (rail) <= d/2 - w (margin).
    # i.e. l <= d - 4w (leave one linewidth clearance on each side).
    max_plate_length = d["d"] - 4.0 * d["w"]
    if d["l"] > max_plate_length:
        return False, (
            f"plate length l ({d['l']/1000.0:.0f} um) > d - 4w "
            f"({max_plate_length/1000.0:.0f} um): plate would touch or "
            f"overlap the left/right outer rails. Decrease l or increase d."
        )

    # 4. Capacitor plates must be above the bottom rail and below the top rail.
    # Top plate y-range: [g/2, g/2 + w]. Must satisfy g/2 + w <= d/2 - w (= top rail bottom edge).
    # i.e. g <= d - 4w. (Same constraint as #3 if l < d - 4w. Implied.)
    # Already enforced by spine_length > 0 above.

    return True, ""


# Hard bounds exposed for the agent prompt + runtime sampling. The (lo, hi)
# tuples mirror PARAM_BOUNDS in constraints_A.py.
PARAM_BOUNDS = {
    "a":     (MIN_PERIOD_NM,       MAX_PERIOD_NM),
    "d":     (MIN_PERIOD_NM - 2.0 * MIN_PATTERN_MARGIN_NM,
              MAX_PERIOD_NM - 2.0 * MIN_PATTERN_MARGIN_NM),
    "l":     (MIN_PLATE_LENGTH_NM, MAX_PLATE_LENGTH_NM),
    "w":     (MIN_LINEWIDTH_NM,    1_000_000.0),     # cap at 1 mm linewidth
    "g":     (MIN_GAP_PHYSICAL_NM, MAX_GAP_NM),
    "h_FR4": (min(ALLOWED_H_FR4_NM), max(ALLOWED_H_FR4_NM)),
    "t_Cu":  (min(ALLOWED_T_CU_NM),  max(ALLOWED_T_CU_NM)),
}


if __name__ == "__main__":
    from design_ELC import DESIGN
    ok, reason = validate_design(DESIGN)
    if ok:
        print("Baseline ELC design (Schurig 2006, scaled to 11 GHz): VALID")
        for k, v in DESIGN.items():
            if k in ("h_FR4", "t_Cu"):
                print(f"  {k}: {v/1000.0:.1f} um")
            else:
                print(f"  {k}: {v/1000.0:.1f} um = {v/1_000_000.0:.3f} mm")
    else:
        print(f"Baseline ELC design: INVALID -- {reason}")
