"""nir/geometry_elc.py -- builder + renderer for the Schurig 2006 ELC unit cell.

Schurig/Mock/Smith APL 88, 041109 (2006), Fig 1(b) topology:

  - One CLOSED outer rectangular frame, size d x d, linewidth w
    (4 rails: top, bottom, left, right).
  - Two T-shaped fingers projecting INWARD from the top and bottom edges:
      - Top T:    vertical spine from top edge down to the central capacitor,
                  with a horizontal crossbar at its bottom = top capacitor plate.
      - Bottom T: mirror in y.
  - The two horizontal crossbars (capacitor plates) face each other vertically
    across gap g.

This module has THREE entry points:

  build_elc_geometry_vba(params)   -- emit the CST VBA for the unit cell solids
                                      (consumed by m3d.add_to_history)
  expected_solid_names()           -- list of solid names that should exist
                                      after build_elc_geometry_vba runs
                                      (used by HistoryBuilder.add(expects_solids=...))
  render_top_view(design, out_png) -- matplotlib top-view PNG of the geometry
                                      from the DESIGN dict, for pre-flight
                                      visual verification BEFORE running CST.
                                      Catches wrong-topology bugs in 1 second
                                      instead of 30 minutes of solver time.

All three consume the SAME symbolic brick spec (ELC_BRICK_SPEC below) so
changing the topology means editing ONE list, and the VBA + the render +
the expected-names list all update together.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple


# =========================================================================
# Single source of truth: symbolic brick specification.
# =========================================================================
# Each entry: (name, material, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi).
# Coordinates are symbolic VBA expressions that CST evaluates against the
# stored parameters (a, d, l, w, g, h_FR4, t_Cu) at meshing time.
# The renderer (render_top_view) substitutes numeric values from a Python
# dict instead.
#
# DO NOT introduce numeric literals here -- the entire point of the symbolic
# spec is that the same definition works for any (a, d, l, w, g) values.
ELC_BRICK_SPEC: List[Tuple[str, str, str, str, str, str, str, str]] = [
    # name             material  x_lo            x_hi          y_lo             y_hi          z_lo      z_hi
    # ---- FR4 substrate (full unit cell, below the metal) ----
    ("fr4",            "FR4",    "-a/2",         "a/2",        "-a/2",          "a/2",        "0",      "h_FR4"),
    # ---- Closed outer rectangular frame (4 rails) ----
    ("frame_top",      "PEC",    "-d/2",         "d/2",        "d/2 - w",       "d/2",        "h_FR4",  "h_FR4 + t_Cu"),
    ("frame_bottom",   "PEC",    "-d/2",         "d/2",        "-d/2",          "-d/2 + w",   "h_FR4",  "h_FR4 + t_Cu"),
    ("frame_left",     "PEC",    "-d/2",         "-d/2 + w",   "-d/2 + w",      "d/2 - w",    "h_FR4",  "h_FR4 + t_Cu"),
    ("frame_right",    "PEC",    "d/2 - w",      "d/2",        "-d/2 + w",      "d/2 - w",    "h_FR4",  "h_FR4 + t_Cu"),
    # ---- Top T-finger ----
    ("top_spine",      "PEC",    "-w/2",         "w/2",        "g/2 + w",       "d/2 - w",    "h_FR4",  "h_FR4 + t_Cu"),
    ("top_plate",      "PEC",    "-l/2",         "l/2",        "g/2",           "g/2 + w",    "h_FR4",  "h_FR4 + t_Cu"),
    # ---- Bottom T-finger (mirror of top in y) ----
    ("bottom_spine",   "PEC",    "-w/2",         "w/2",        "-d/2 + w",      "-g/2 - w",   "h_FR4",  "h_FR4 + t_Cu"),
    ("bottom_plate",   "PEC",    "-l/2",         "l/2",        "-g/2 - w",      "-g/2",       "h_FR4",  "h_FR4 + t_Cu"),
]


# =========================================================================
# Public entry points
# =========================================================================

def build_elc_geometry_vba(params: Dict[str, float]) -> str:
    """Emit CST VBA for the Schurig 2006 ELC unit cell solids.

    Consumed by m3d.add_to_history. Uses Component "component1" (the CST 2026
    new_mws() default) for all bricks. Materials "FR4" and "PEC" must be
    defined BEFORE this VBA executes (FR4 via the build script's material
    block; PEC is a CST 2026 built-in, no definition needed).

    Args:
        params: dict with keys a, d, l, w, g, h_FR4, t_Cu (units = whatever
                the project's Units.Length is set to; build script uses mm).
                Only used for the missing-key check; the actual numeric
                values are stored in CST via StoreParameter and looked up at
                mesh time. Passing wrong values here is OK; the VBA is unit-
                cell-shape-only, not unit-cell-numeric.

    Returns:
        A multi-line VBA string ready to pass to m3d.add_to_history(...).
    """
    required = {"a", "d", "l", "w", "g", "h_FR4", "t_Cu"}
    missing = required - set(params.keys())
    if missing:
        raise KeyError(f"build_elc_geometry_vba: missing params: {missing}")

    blocks = []
    for name, material, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi in ELC_BRICK_SPEC:
        blocks.append("\n".join([
            "With Brick",
            "    .Reset",
            f'    .Name "{name}"',
            '    .Component "component1"',
            f'    .Material "{material}"',
            f'    .Xrange "{x_lo}", "{x_hi}"',
            f'    .Yrange "{y_lo}", "{y_hi}"',
            f'    .Zrange "{z_lo}", "{z_hi}"',
            "    .Create",
            "End With",
        ]))
    return "\n\n".join(blocks)


def expected_solid_names() -> List[str]:
    """List of solid names that should exist after build_elc_geometry_vba runs.

    Used by HistoryBuilder.add(expects_solids=...) to verify the geometry
    step actually built all 9 bricks (FR4 substrate + 8 metal pieces).

    Returns the leaf names (e.g. "fr4", "frame_top"), not the
    "component1:fr4" prefixed form -- verify_solids_exist handles both.
    """
    return [name for name, _, *_ in ELC_BRICK_SPEC]


# =========================================================================
# Pre-flight renderer (no CST required)
# =========================================================================

def _eval_expr(expr: str, params_numeric: Dict[str, float]) -> float:
    """Evaluate a symbolic CST expression like '-d/2 + w' against a parameter dict.

    Restricted Python eval -- no builtins, only the parameter values are
    in scope. Safe for trusted inputs (we control ELC_BRICK_SPEC).
    """
    return float(eval(expr, {"__builtins__": {}}, params_numeric))


def render_top_view(design: Dict[str, float],
                    out_png: str | Path,
                    *,
                    unit_scale: float = 1e-6,
                    unit_label: str = "mm",
                    title: str = "Schurig 2006 ELC -- pre-flight top view"
                    ) -> None:
    """Render a top-view PNG of the ELC geometry for visual verification.

    Call this BEFORE running the CST build. If the render doesn't match
    the seed paper's figure, the build will reproduce that wrong topology
    in CST (silently, after 30+ min of solver time). 1-second sanity check
    that saves hours of debugging.

    Args:
        design: dict of parameter VALUES (numeric, not symbolic). Keys must
                include a, d, l, w, g, h_FR4, t_Cu. Values are in the unit
                given by unit_scale -- by default design values are in nm
                and unit_scale = 1e-6 converts to mm for display.
        out_png: output PNG path.
        unit_scale: multiplier to convert design values to display units.
                    Default 1e-6 = nm -> mm. Use 1.0 if design is already mm.
        unit_label: display unit string for axis labels.
        title: figure title.
    """
    # Defer matplotlib import so cst_helpers users don't pay the cost if
    # they don't render.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    # Convert design values to display units (e.g., nm -> mm).
    params_disp = {k: v * unit_scale for k, v in design.items()}
    a_disp = params_disp["a"]

    fig, ax = plt.subplots(figsize=(8, 8))

    # Unit cell outline (dashed black).
    ax.add_patch(mpatches.Rectangle(
        (-a_disp / 2, -a_disp / 2), a_disp, a_disp,
        linewidth=1.0, linestyle="--",
        edgecolor="black", facecolor="none",
    ))

    # Plot each brick. Metal bricks are copper-colored; substrate is green
    # tint and rendered first so the metal sits on top.
    substrate_alpha = 0.45
    metal_color = "#d2691e"   # chocolate / copper

    # Substrate first (under).
    for name, material, x_lo, x_hi, y_lo, y_hi, _z_lo, _z_hi in ELC_BRICK_SPEC:
        if material != "FR4":
            continue
        x0 = _eval_expr(x_lo, params_disp)
        x1 = _eval_expr(x_hi, params_disp)
        y0 = _eval_expr(y_lo, params_disp)
        y1 = _eval_expr(y_hi, params_disp)
        ax.add_patch(mpatches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            linewidth=0, facecolor="#c8e6c9", alpha=substrate_alpha,
        ))

    # Metal bricks on top.
    for name, material, x_lo, x_hi, y_lo, y_hi, _z_lo, _z_hi in ELC_BRICK_SPEC:
        if material == "FR4":
            continue
        x0 = _eval_expr(x_lo, params_disp)
        x1 = _eval_expr(x_hi, params_disp)
        y0 = _eval_expr(y_lo, params_disp)
        y1 = _eval_expr(y_hi, params_disp)
        ax.add_patch(mpatches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            linewidth=0.5, edgecolor="black",
            facecolor=metal_color, alpha=0.95,
        ))

    # Labeled dimension arrows for a, d, l, w, g.
    d_disp = params_disp["d"]
    l_disp = params_disp["l"]
    w_disp = params_disp["w"]
    g_disp = params_disp["g"]
    arrow_style = dict(arrowstyle="<->", color="#222", lw=1.2)

    ax.annotate("", xy=(-a_disp / 2, a_disp / 2 + a_disp * 0.05),
                xytext=(a_disp / 2, a_disp / 2 + a_disp * 0.05),
                arrowprops=arrow_style)
    ax.text(0, a_disp / 2 + a_disp * 0.08, f"a = {a_disp:.3f} {unit_label}",
            ha="center", va="bottom", fontsize=11)

    ax.annotate("", xy=(-d_disp / 2, -a_disp / 2 - a_disp * 0.05),
                xytext=(d_disp / 2, -a_disp / 2 - a_disp * 0.05),
                arrowprops=arrow_style)
    ax.text(0, -a_disp / 2 - a_disp * 0.10, f"d = {d_disp:.3f} {unit_label}",
            ha="center", va="top", fontsize=11)

    ax.annotate("", xy=(-l_disp / 2, g_disp / 2 + w_disp * 1.5),
                xytext=(l_disp / 2, g_disp / 2 + w_disp * 1.5),
                arrowprops=dict(arrowstyle="<->", color="white", lw=1.2))
    ax.text(0, g_disp / 2 + w_disp * 2.5, f"l = {l_disp:.3f} {unit_label}",
            ha="center", va="bottom", fontsize=10, color="#222")

    ax.annotate("", xy=(l_disp / 2 + a_disp * 0.07, -g_disp / 2),
                xytext=(l_disp / 2 + a_disp * 0.07, g_disp / 2),
                arrowprops=arrow_style)
    ax.text(l_disp / 2 + a_disp * 0.10, 0, f"g = {g_disp:.3f} {unit_label}",
            ha="left", va="center", fontsize=10)

    ax.annotate("", xy=(-d_disp / 2 - a_disp * 0.05, d_disp / 2 - w_disp),
                xytext=(-d_disp / 2 - a_disp * 0.05, d_disp / 2),
                arrowprops=arrow_style)
    ax.text(-d_disp / 2 - a_disp * 0.10, d_disp / 2 - w_disp / 2,
            f"w = {w_disp:.3f} {unit_label}",
            ha="right", va="center", fontsize=10)

    ax.set_xlim(-a_disp / 2 - a_disp * 0.22, a_disp / 2 + a_disp * 0.28)
    ax.set_ylim(-a_disp / 2 - a_disp * 0.17, a_disp / 2 + a_disp * 0.17)
    ax.set_aspect("equal")
    ax.set_xlabel(f"x ({unit_label})")
    ax.set_ylabel(f"y ({unit_label})")
    ax.set_title(
        f"{title}\n"
        f"a={a_disp:.3f}  d={d_disp:.3f}  l={l_disp:.3f}  "
        f"w={w_disp:.3f}  g={g_disp:.3f}  (all {unit_label})\n"
        f"Compare against the seed paper's figure BEFORE running CST."
    )
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
