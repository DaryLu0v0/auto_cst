"""nir/plot_final_report.py -- comparison plot of A/B/C final spectra."""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Locate the latest absorptance per hypothesis from the converged runs
RUNS = {
    "A (disk MIM)":        PROJECT_ROOT / "runs" / "2026-05-07_02-10-06" / "hypothesis_A_disk"   / "iteration_08" / "Absorptance.csv",
    "B (rect-patch MIM)":  PROJECT_ROOT / "runs" / "2026-05-07_03-18-13" / "hypothesis_B_ellipse"/ "iteration_10" / "Absorptance.csv",
    "C (planar MIM)":      PROJECT_ROOT / "runs" / "2026-05-07_03-39-25" / "hypothesis_C_planar" / "iteration_06" / "Absorptance.csv",
}

C_LIGHT_NMTHZ = 299.792458 * 1e3  # nm * THz

fig, (ax_thz, ax_nm) = plt.subplots(2, 1, figsize=(10, 7), sharey=True)

target_thz = 193.41
target_nm = C_LIGHT_NMTHZ / target_thz

colors = {"A (disk MIM)": "#1f77b4", "B (rect-patch MIM)": "#ff7f0e", "C (planar MIM)": "#2ca02c"}

for label, path in RUNS.items():
    if not path.exists():
        # Try iteration_NN folders
        ref = list(path.parent.parent.glob("iteration_*/Absorptance.csv"))
        if ref:
            path = sorted(ref)[-1]
            print(f"{label}: using {path}")
    if not path.exists():
        print(f"{label}: NO ABSORPTANCE FOUND, skipping")
        continue
    freq, ab = np.loadtxt(path, delimiter="\t", comments="#", unpack=True)
    wl = C_LIGHT_NMTHZ / freq
    color = colors[label]
    i_peak = int(np.argmax(ab))
    f_peak = freq[i_peak]
    a_peak = ab[i_peak]
    nm_peak = C_LIGHT_NMTHZ / f_peak
    legend = f"{label}: peak={nm_peak:.0f} nm ({f_peak:.1f} THz), abs={a_peak:.3f}"
    ax_thz.plot(freq, ab, color=color, linewidth=1.5, label=legend)
    ax_thz.axvline(f_peak, color=color, linestyle=":", alpha=0.4)
    ax_nm.plot(wl, ab, color=color, linewidth=1.5, label=legend)
    ax_nm.axvline(nm_peak, color=color, linestyle=":", alpha=0.4)

# Target lines
ax_thz.axvline(target_thz, color="red", linestyle="--", linewidth=2,
               label=f"Target: {target_thz} THz / {target_nm:.0f} nm")
ax_nm.axvline(target_nm, color="red", linestyle="--", linewidth=2)

for ax in (ax_thz, ax_nm):
    ax.set_ylabel("Absorptance")
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9)

ax_thz.set_xlabel("Frequency (THz)")
ax_thz.set_xlim(100, 300)
ax_thz.set_title("auto_cst NIR absorbers — A / B / C, final spectra")

ax_nm.set_xlabel("Wavelength (nm)")
ax_nm.set_xlim(1000, 3000)

plt.tight_layout()
out_path = PROJECT_ROOT / "runs" / "FINAL_REPORT_spectra.png"
plt.savefig(str(out_path), dpi=150, bbox_inches="tight")
print(f"Saved: {out_path}")
