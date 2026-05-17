"""Parametric validation: run the corrected Schurig ELC topology at the PAPER's
exact published geometry (a = 3.333 mm, d = 3.0 mm, l = 1.0 mm, w = g = 0.25 mm)
and verify the resonance lands near the paper's reported peak.

Predictions (linear-scaling our v10 result of 11.98 GHz at a = 4.0905 mm back
to a = 3.333 mm):
    f_pred = 11.98 GHz * (4.0905 / 3.333) = 14.7 GHz

Paper's reported numbers (from the LR session):
    - operating frequency: 15.7 GHz (text)
    - eps_real peak from spectrum plot (VLM): 13.5 GHz

So we expect the v11 resonance to land in [13, 16] GHz. A landing in that
window is strong evidence that:
  (a) the topology in build_elc_11ghz.py matches Schurig's actual ELC, and
  (b) the linear-scaling assumption used by the LR is reliable.

This script monkey-patches DESIGN temporarily, runs build_elc_11ghz.main(),
restores DESIGN, and copies the results to a separate run_dir so the v10
artifacts aren't overwritten.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# Paper's exact geometry, in nm (Schurig 2006 APL 88, 041109).
PAPER_DESIGN = {
    "a":     3333000.0,   # 3.333 mm
    "d":     3000000.0,   # 3.000 mm
    "l":     1000000.0,   # 1.000 mm
    "w":      250000.0,   # 0.250 mm
    "g":      250000.0,   # 0.250 mm
    "h_FR4":  203000.0,   # 0.203 mm  (kept same, standard PCB stock)
    "t_Cu":    17000.0,   # 0.017 mm  (kept same)
}

# Save dir SEPARATE from v10's run_dir to avoid clobbering the production result.
RUN_DIR = Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design_paper_validation")
RUN_DIR.mkdir(parents=True, exist_ok=True)


def main():
    # Monkey-patch DESIGN before importing build_elc_11ghz so its top-level
    # `from nir.design_ELC import DESIGN` picks up the override.
    import nir.design_ELC as design_mod
    original_design = dict(design_mod.DESIGN)
    design_mod.DESIGN.clear()
    design_mod.DESIGN.update(PAPER_DESIGN)
    print(f"PAPER_DESIGN active: {design_mod.DESIGN}")

    try:
        # Also widen the sweep to capture the paper's expected ~15.7 GHz peak
        # plus margin. Use 10-22 GHz which brackets both candidate values.
        import build_elc_11ghz as builder
        builder.F_MIN_GHZ = 10.0
        builder.F_MAX_GHZ = 22.0
        builder.F_TARGET_GHZ = 14.7   # our linear-scaled prediction
        builder.TARGET_TOL_FRAC = 0.20  # widen to +/-20% to accept paper's
                                         # 13.5-15.7 GHz range comfortably
        builder.VBA_FREQ_RANGE = f'Solver.FrequencyRange "{builder.F_MIN_GHZ}", "{builder.F_MAX_GHZ}"\n'

        print(f"Sweep: {builder.F_MIN_GHZ}-{builder.F_MAX_GHZ} GHz, "
              f"target {builder.F_TARGET_GHZ} GHz +/- {builder.TARGET_TOL_FRAC*100:.0f}%")

        rc = builder.main([
            "--run-dir", str(RUN_DIR),
            "--version", "paper_validation",
        ])
        print(f"\nbuilder.main() returned {rc}")
    finally:
        # Always restore DESIGN.
        design_mod.DESIGN.clear()
        design_mod.DESIGN.update(original_design)
        print(f"DESIGN restored: a = {design_mod.DESIGN['a']/1_000_000:.4f} mm")


if __name__ == "__main__":
    main()
