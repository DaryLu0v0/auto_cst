"""compare_spectra.py -- Plot absorptance spectra across array scales.

Reads exported Absorptance.csv from each configuration and generates
comparison plots to study coupling effects vs. array scale.

Usage:
    python compare_spectra.py
    python compare_spectra.py --configs 1x1_a 1x1_b 2x2 4x4 8x8
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
EXPORTS_DIR = HERE / "exports"

# Reference peaks (from 1x1 database)
CELL_A_PEAK_UM = 10.308   # 29.1 THz
CELL_B_PEAK_UM = 18.803   # 16.0 THz
CELL_A_PEAK_THZ = 300.0 / CELL_A_PEAK_UM
CELL_B_PEAK_THZ = 300.0 / CELL_B_PEAK_UM

ALL_CONFIGS = ["1x1_a", "1x1_b", "2x2", "4x4", "8x8"]

CONFIG_LABELS = {
    "1x1_a": "1x1 cell A (10.3 um)",
    "1x1_b": "1x1 cell B (18.8 um)",
    "2x2":   "2x2 [a,b; b,a]",
    "4x4":   "4x4 [a₂,b₂; b₂,a₂]",
    "8x8":   "8x8 [a₄,b₄; b₄,a₄]",
}

CONFIG_COLORS = {
    "1x1_a": "#1f77b4",   # blue
    "1x1_b": "#ff7f0e",   # orange
    "2x2":   "#2ca02c",   # green
    "4x4":   "#d62728",   # red
    "8x8":   "#9467bd",   # purple
}

CONFIG_STYLES = {
    "1x1_a": "--",
    "1x1_b": "--",
    "2x2":   "-",
    "4x4":   "-",
    "8x8":   "-",
}


def load_spectrum(config: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Load absorptance spectrum for a config. Returns (freq_thz, absorptance) or None."""
    csv_path = EXPORTS_DIR / config / "Absorptance.csv"
    if not csv_path.exists():
        print(f"  [SKIP] {config}: no Absorptance.csv found")
        return None

    freq, absorptance = [], []
    with open(csv_path, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            try:
                freq.append(float(row[0].strip()))
                absorptance.append(float(row[1].strip()))
            except (ValueError, IndexError):
                continue

    if len(freq) == 0:
        print(f"  [SKIP] {config}: empty spectrum")
        return None

    return np.array(freq), np.array(absorptance)


def find_peaks(freq: np.ndarray, absorptance: np.ndarray,
               threshold: float = 0.3) -> list[tuple[float, float]]:
    """Find absorption peaks above threshold. Returns [(freq_thz, abs_val), ...]"""
    peaks = []
    for i in range(1, len(absorptance) - 1):
        if (absorptance[i] > absorptance[i-1] and
            absorptance[i] > absorptance[i+1] and
            absorptance[i] > threshold):
            peaks.append((freq[i], absorptance[i]))
    return peaks


def plot_all_spectra(configs: list[str]) -> None:
    """Plot 1: All absorptance spectra overlaid."""
    fig, ax = plt.subplots(figsize=(12, 6))

    for cfg in configs:
        data = load_spectrum(cfg)
        if data is None:
            continue
        freq, absorptance = data

        # Convert to wavelength for x-axis
        wavelength = 300.0 / freq  # um

        ax.plot(wavelength, absorptance,
                color=CONFIG_COLORS.get(cfg, "gray"),
                linestyle=CONFIG_STYLES.get(cfg, "-"),
                linewidth=2 if cfg in ("2x2", "4x4", "8x8") else 1.5,
                alpha=0.9,
                label=CONFIG_LABELS.get(cfg, cfg))

    # Mark reference peaks
    ax.axvline(CELL_A_PEAK_UM, color="#1f77b4", linestyle=":", alpha=0.4, linewidth=1)
    ax.axvline(CELL_B_PEAK_UM, color="#ff7f0e", linestyle=":", alpha=0.4, linewidth=1)
    ax.text(CELL_A_PEAK_UM + 0.2, 0.95, f"A peak\n{CELL_A_PEAK_UM:.1f} um",
            fontsize=8, color="#1f77b4", alpha=0.6)
    ax.text(CELL_B_PEAK_UM + 0.2, 0.95, f"B peak\n{CELL_B_PEAK_UM:.1f} um",
            fontsize=8, color="#ff7f0e", alpha=0.6)

    ax.set_xlabel("Wavelength (um)", fontsize=12)
    ax.set_ylabel("Absorptance", fontsize=12)
    ax.set_title("Coupling vs Scale: CWC Absorber Spectra", fontsize=14)
    ax.set_xlim(9, 22)
    ax.set_ylim(0, 1.05)
    ax.legend(loc="lower right", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    # Secondary x-axis: frequency
    ax2 = ax.secondary_xaxis("top", functions=(lambda x: 300/x, lambda f: 300/f))
    ax2.set_xlabel("Frequency (THz)", fontsize=10)

    plt.tight_layout()
    out_path = HERE / "coupling_spectra_overlay.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"  Saved: {out_path}")


def plot_coupling_effect(configs: list[str]) -> None:
    """Plot 2: Show how the spectrum changes with scale.

    For mixed configs (2x2, 4x4, 8x8), overlay with the
    ideal non-coupling reference (average of 1x1_a and 1x1_b).
    """
    data_a = load_spectrum("1x1_a")
    data_b = load_spectrum("1x1_b")

    if data_a is None or data_b is None:
        print("  [SKIP] Need both 1x1_a and 1x1_b for coupling effect plot")
        return

    mixed_configs = [c for c in configs if c in ("2x2", "4x4", "8x8")]
    if not mixed_configs:
        print("  [SKIP] No mixed configs available")
        return

    # Compute ideal non-coupling reference:
    # For a checkerboard with 50% a and 50% b, the no-coupling prediction
    # is simply the average of the two 1x1 spectra
    freq_a, abs_a = data_a
    freq_b, abs_b = data_b

    # Interpolate both onto a common frequency grid
    f_min = max(freq_a.min(), freq_b.min())
    f_max = min(freq_a.max(), freq_b.max())
    f_common = np.linspace(f_min, f_max, 500)
    abs_a_interp = np.interp(f_common, np.sort(freq_a),
                             abs_a[np.argsort(freq_a)])
    abs_b_interp = np.interp(f_common, np.sort(freq_b),
                             abs_b[np.argsort(freq_b)])
    abs_nocoupling = 0.5 * abs_a_interp + 0.5 * abs_b_interp
    wl_common = 300.0 / f_common

    n_plots = len(mixed_configs)
    fig, axes = plt.subplots(1, n_plots, figsize=(6 * n_plots, 5), sharey=True)
    if n_plots == 1:
        axes = [axes]

    for ax, cfg in zip(axes, mixed_configs):
        data = load_spectrum(cfg)
        if data is None:
            continue
        freq, absorptance = data
        wl = 300.0 / freq

        # Plot no-coupling reference
        ax.fill_between(wl_common, abs_nocoupling, alpha=0.15, color="gray",
                        label="No-coupling avg (1x1_a + 1x1_b)/2")
        ax.plot(wl_common, abs_nocoupling, color="gray", linestyle="--",
                linewidth=1.5, alpha=0.7)

        # Plot actual
        ax.plot(wl, absorptance,
                color=CONFIG_COLORS[cfg], linewidth=2.0,
                label=CONFIG_LABELS[cfg])

        # Coupling effect = actual - no_coupling_reference
        abs_actual_interp = np.interp(f_common, np.sort(freq),
                                       absorptance[np.argsort(freq)])
        coupling_delta = abs_actual_interp - abs_nocoupling

        # Annotate mean coupling effect
        mean_delta = np.mean(coupling_delta)
        ax.text(0.02, 0.02,
                f"Mean coupling effect: {mean_delta:+.3f}",
                transform=ax.transAxes, fontsize=9,
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

        ax.set_xlabel("Wavelength (um)", fontsize=11)
        ax.set_title(CONFIG_LABELS[cfg], fontsize=12)
        ax.set_xlim(9, 22)
        ax.set_ylim(0, 1.05)
        ax.legend(loc="lower right", fontsize=8)
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("Absorptance", fontsize=11)

    fig.suptitle("Coupling Effect: Actual vs Non-Coupling Reference", fontsize=14, y=1.02)
    plt.tight_layout()
    out_path = HERE / "coupling_effect_comparison.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_path}")


def plot_coupling_delta(configs: list[str]) -> None:
    """Plot 3: Coupling delta (actual - no-coupling reference) for each scale."""
    data_a = load_spectrum("1x1_a")
    data_b = load_spectrum("1x1_b")

    if data_a is None or data_b is None:
        return

    freq_a, abs_a = data_a
    freq_b, abs_b = data_b

    f_min = max(freq_a.min(), freq_b.min())
    f_max = min(freq_a.max(), freq_b.max())
    f_common = np.linspace(f_min, f_max, 500)
    abs_a_interp = np.interp(f_common, np.sort(freq_a), abs_a[np.argsort(freq_a)])
    abs_b_interp = np.interp(f_common, np.sort(freq_b), abs_b[np.argsort(freq_b)])
    abs_nocoupling = 0.5 * abs_a_interp + 0.5 * abs_b_interp
    wl_common = 300.0 / f_common

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.axhline(0, color="black", linewidth=0.5)

    mixed_configs = [c for c in configs if c in ("2x2", "4x4", "8x8")]
    for cfg in mixed_configs:
        data = load_spectrum(cfg)
        if data is None:
            continue
        freq, absorptance = data
        abs_interp = np.interp(f_common, np.sort(freq), absorptance[np.argsort(freq)])
        delta = abs_interp - abs_nocoupling

        ax.plot(wl_common, delta,
                color=CONFIG_COLORS[cfg], linewidth=2.0,
                label=f"{CONFIG_LABELS[cfg]} (mean={np.mean(delta):+.3f})")

        # Shade positive/negative regions
        ax.fill_between(wl_common, delta, 0,
                        where=delta > 0,
                        color=CONFIG_COLORS[cfg], alpha=0.1)
        ax.fill_between(wl_common, delta, 0,
                        where=delta < 0,
                        color=CONFIG_COLORS[cfg], alpha=0.05)

    ax.axvline(CELL_A_PEAK_UM, color="#1f77b4", linestyle=":", alpha=0.3)
    ax.axvline(CELL_B_PEAK_UM, color="#ff7f0e", linestyle=":", alpha=0.3)

    ax.set_xlabel("Wavelength (um)", fontsize=12)
    ax.set_ylabel("Coupling Delta (actual - no-coupling)", fontsize=12)
    ax.set_title("Coupling-Induced Absorption Change at Each Scale", fontsize=14)
    ax.set_xlim(9, 22)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    ax2 = ax.secondary_xaxis("top", functions=(lambda x: 300/x, lambda f: 300/f))
    ax2.set_xlabel("Frequency (THz)", fontsize=10)

    plt.tight_layout()
    out_path = HERE / "coupling_delta_vs_scale.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"  Saved: {out_path}")


def plot_peak_shifts(configs: list[str]) -> None:
    """Plot 4: Track how absorption peaks shift with array scale."""
    fig, ax = plt.subplots(figsize=(10, 6))

    scale_labels = []
    for cfg in configs:
        data = load_spectrum(cfg)
        if data is None:
            continue
        freq, absorptance = data
        peaks = find_peaks(freq, absorptance, threshold=0.3)

        if peaks:
            peak_freqs = [p[0] for p in peaks]
            peak_vals = [p[1] for p in peaks]
            peak_wls = [300.0 / f for f in peak_freqs]

            ax.scatter(peak_wls, [cfg] * len(peak_wls),
                       s=[v * 200 for v in peak_vals],  # size ~ absorption strength
                       c=CONFIG_COLORS.get(cfg, "gray"),
                       alpha=0.7, edgecolors="black", linewidths=0.5,
                       zorder=5)

    # Reference lines
    ax.axvline(CELL_A_PEAK_UM, color="#1f77b4", linestyle=":", alpha=0.4,
               label=f"Cell A 1x1 peak ({CELL_A_PEAK_UM:.1f} um)")
    ax.axvline(CELL_B_PEAK_UM, color="#ff7f0e", linestyle=":", alpha=0.4,
               label=f"Cell B 1x1 peak ({CELL_B_PEAK_UM:.1f} um)")

    ax.set_xlabel("Peak Wavelength (um)", fontsize=12)
    ax.set_ylabel("Configuration", fontsize=12)
    ax.set_title("Absorption Peak Positions vs Array Scale\n(bubble size = peak strength)",
                 fontsize=13)
    ax.set_xlim(8, 22)
    ax.legend(fontsize=9, loc="lower right")
    ax.grid(True, alpha=0.3, axis="x")

    plt.tight_layout()
    out_path = HERE / "peak_shifts_vs_scale.png"
    plt.savefig(out_path, dpi=200)
    plt.close()
    print(f"  Saved: {out_path}")


def print_summary_table(configs: list[str]) -> None:
    """Print a summary table of key metrics."""
    print(f"\n{'='*80}")
    print(f"  COUPLING STUDY SUMMARY")
    print(f"{'='*80}")
    print(f"  {'Config':<10} {'Cells':>5} {'Mean Abs':>10} {'Min Abs':>10} "
          f"{'A-band':>10} {'B-band':>10} {'Peaks'}")
    print(f"  {'-'*10} {'-'*5} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*20}")

    for cfg in configs:
        data = load_spectrum(cfg)
        if data is None:
            print(f"  {cfg:<10} {'---':>5} {'N/A':>10}")
            continue

        freq, absorptance = data
        n = {"1x1_a": 1, "1x1_b": 1, "2x2": 4, "4x4": 16, "8x8": 64}[cfg]

        mean_abs = np.mean(absorptance)
        min_abs = np.min(absorptance)

        # A band (10-13 um = 23.08-30.00 THz)
        mask_a = (freq >= 23.08) & (freq <= 30.00)
        mean_a = np.mean(absorptance[mask_a]) if np.any(mask_a) else 0.0

        # B band (18-20 um = 15.00-16.67 THz)
        mask_b = (freq >= 15.00) & (freq <= 16.67)
        mean_b = np.mean(absorptance[mask_b]) if np.any(mask_b) else 0.0

        peaks = find_peaks(freq, absorptance)
        peak_str = ", ".join([f"{300/p[0]:.1f}um" for p in peaks[:5]])
        if len(peaks) > 5:
            peak_str += f" +{len(peaks)-5} more"

        print(f"  {cfg:<10} {n:>5} {mean_abs:>10.4f} {min_abs:>10.4f} "
              f"{mean_a:>10.4f} {mean_b:>10.4f} {peak_str}")

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Compare absorptance spectra across array scales")
    parser.add_argument("--configs", nargs="+", default=ALL_CONFIGS,
                        choices=ALL_CONFIGS,
                        help="Configurations to compare")
    args = parser.parse_args()

    configs = args.configs

    # Check which configs have data
    available = [c for c in configs if (EXPORTS_DIR / c / "Absorptance.csv").exists()]
    print(f"  Available configs: {available}")
    print(f"  Missing configs: {[c for c in configs if c not in available]}")

    if len(available) < 2:
        print("  Need at least 2 configs to compare. Run build_and_run.py first.")
        sys.exit(1)

    # Generate plots
    print("\n  Generating plots...")
    plot_all_spectra(available)
    plot_coupling_effect(available)
    plot_coupling_delta(available)
    plot_peak_shifts(available)
    print_summary_table(available)

    print("  Done! All plots saved to coupling_study/")


if __name__ == "__main__":
    main()
