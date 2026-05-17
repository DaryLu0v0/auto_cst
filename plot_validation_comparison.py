"""Overlay |S21| and |S11| from v10 (target geometry @ a=4.09 mm) and the paper
validation case (a=3.333 mm). Shows that the SAME topology gives two cleanly-
shifted Lorentzian resonances, with the shift ratio matching the geometry ratio.
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUNS = {
    "v10 (target: a=4.0905 mm)": Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design/s_params_complex.csv"),
    "v_paper (a=3.333 mm)":      Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design_paper_validation/s_params_complex.csv"),
}


def load(p):
    data = np.loadtxt(p, delimiter=",", skiprows=4)
    return data[:, 0], np.abs(data[:, 1] + 1j*data[:, 2]), np.abs(data[:, 3] + 1j*data[:, 4])


fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

colors = {"v10 (target: a=4.0905 mm)": "C0", "v_paper (a=3.333 mm)": "C3"}
peaks = {}

for label, path in RUNS.items():
    f, s11, s21 = load(path)
    axes[0].plot(f, s11, color=colors[label], linewidth=2, label=label)
    axes[1].plot(f, s21, color=colors[label], linewidth=2, label=label)
    peak_idx = int(np.argmax(s11))
    peaks[label] = (float(f[peak_idx]), float(s11[peak_idx]), float(s21[int(np.argmin(s21))]))

# Mark resonance peak frequencies
for ax in axes:
    for label, (fpk, s11pk, s21nt) in peaks.items():
        ax.axvline(fpk, color=colors[label], linestyle=":", alpha=0.5)

# Annotate
axes[0].set_ylabel("|S11|")
axes[0].axhline(1, color="black", linewidth=0.5)
axes[0].legend(loc="lower right", fontsize=10)
axes[0].grid(True, alpha=0.3)
axes[0].set_title(
    "Schurig ELC -- validation: same topology, two geometries\n"
    f"v10 peak: {peaks['v10 (target: a=4.0905 mm)'][0]:.2f} GHz, "
    f"v_paper peak: {peaks['v_paper (a=3.333 mm)'][0]:.2f} GHz, "
    f"ratio = {peaks['v_paper (a=3.333 mm)'][0] / peaks['v10 (target: a=4.0905 mm)'][0]:.3f}  "
    f"(geometry ratio: 4.0905/3.333 = {4.0905/3.333:.3f}; "
    f"linear-scaling residual: "
    f"{(peaks['v_paper (a=3.333 mm)'][0] / peaks['v10 (target: a=4.0905 mm)'][0] - 4.0905/3.333) / (4.0905/3.333) * 100:+.1f}%)"
)

axes[1].set_xlabel("Frequency (GHz)")
axes[1].set_ylabel("|S21|")
axes[1].legend(loc="upper right", fontsize=10)
axes[1].grid(True, alpha=0.3)

# Add target band shading on v10 (9.9-12.1)
for ax in axes:
    ax.axvspan(9.9, 12.1, alpha=0.1, color="C0", label=None)
    ax.text(11.0, ax.get_ylim()[1] * 0.95 if ax == axes[0] else 0.05, "v10 target band\n[9.9, 12.1] GHz",
            ha="center", va="top" if ax == axes[0] else "bottom",
            fontsize=8, color="C0", alpha=0.7)

fig.tight_layout()
out = Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design/validation_overlay.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print(f"Wrote {out}")
print()
print("Summary:")
for label, (fpk, s11pk, s21nt) in peaks.items():
    print(f"  {label}:")
    print(f"    S11 peak at f = {fpk:.3f} GHz, |S11| = {s11pk:.4f}")
    print(f"    deepest |S21| notch: {s21nt:.4f}")
print()
print(f"  Resonance ratio (paper/v10) = {peaks['v_paper (a=3.333 mm)'][0] / peaks['v10 (target: a=4.0905 mm)'][0]:.4f}")
print(f"  Geometry  ratio (v10/paper) = {4.0905/3.333:.4f}")
print(f"  Linear-scaling residual:      {(peaks['v_paper (a=3.333 mm)'][0] / peaks['v10 (target: a=4.0905 mm)'][0] - 4.0905/3.333) / (4.0905/3.333) * 100:+.2f}%")
