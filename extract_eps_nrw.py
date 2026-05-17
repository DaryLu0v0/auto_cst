"""extract_eps_nrw.py -- NRW / Smith-Schultz-Markos-Soukoulis effective-medium
retrieval from complex S-parameters of a periodic metamaterial slab.

Reads `s_params_complex.csv` produced by build_elc_11ghz.py, computes effective
permittivity / permeability / refractive index / impedance on the frequency
grid, and writes `eff_params.csv` + `eff_params_summary.json` + a quick PNG.

References:
    Nicolson, Ross, Weir (1970): Phys. Rev. B 19, 6611.
    Smith, Schultz, Markos, Soukoulis (2002): PRB 65, 195104.
    Schurig, Mock, Smith (2006): APL 88, 041109 (uses Soukoulis 2002 retrieval).

Usage:
    python extract_eps_nrw.py --run-dir runs/elc_11ghz/Experiment/cst_design
        [--slab-thickness-nm 203000] [--target-ghz 11.0]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Tuple

import numpy as np


C0_NM_PER_NS = 2.997924580e8 * 1e9 * 1e-9   # = 299_792_458 nm/ns (kept for clarity)
C0_M_PER_S = 299_792_458.0


def read_complex_s_csv(csv_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Read s_params_complex.csv. Returns (freq_GHz, S11, S21, header_meta)."""
    meta = {}
    with csv_path.open() as f:
        header_lines = []
        for line in f:
            if line.startswith("#"):
                header_lines.append(line.rstrip("\n"))
            else:
                # Should be the column-header line `freq_GHz,Re_S11,...`
                col_header = line.rstrip("\n")
                break
        meta["header_comments"] = header_lines
        meta["columns"] = col_header.split(",")
        data = np.loadtxt(f, delimiter=",")

    freq = data[:, 0]
    s11 = data[:, 1] + 1j * data[:, 2]
    s21 = data[:, 3] + 1j * data[:, 4]
    return freq, s11, s21, meta


def nrw_retrieval(
    freq_ghz: np.ndarray,
    s11: np.ndarray,
    s21: np.ndarray,
    slab_thickness_m: float,
) -> dict:
    """Apply the Smith/Soukoulis 2002 retrieval algorithm.

    Returns a dict of arrays: eps, mu, n, z, Gamma, T, K (all complex, same
    shape as freq_ghz).
    """
    omega = 2.0 * np.pi * freq_ghz * 1e9
    k0 = omega / C0_M_PER_S
    L = slab_thickness_m

    # Step 1: K
    K = (s11**2 - s21**2 + 1.0) / (2.0 * s11)

    # Step 2: Gamma = K ± sqrt(K^2 - 1). Pick sign so |Gamma| <= 1.
    K2m1 = K**2 - 1.0
    sqrt_K2m1 = np.sqrt(K2m1)
    Gamma_plus = K + sqrt_K2m1
    Gamma_minus = K - sqrt_K2m1
    Gamma = np.where(np.abs(Gamma_plus) <= 1.0, Gamma_plus, Gamma_minus)

    # Step 3: T = (S11 + S21 - Gamma) / (1 - (S11 + S21)*Gamma)
    T = (s11 + s21 - Gamma) / (1.0 - (s11 + s21) * Gamma)

    # Step 4: n from ln(T). Principal branch (m=0). For thin slabs k0*L << pi
    # this is unambiguous; phase unwrapping would handle thicker slabs.
    log_T = np.log(T)  # complex log, principal branch
    # n = -i ln(T) / (k0 L)  with the e^{j omega t} convention CST uses by default.
    # (sign convention: ensure Im(n) >= 0 for a passive lossy medium.)
    n = (-1j * log_T) / (k0 * L)
    # If Im(n) is systematically < 0, flip sign (passive convention).
    if np.median(n.imag) < 0:
        n = -n

    # Step 5: z = sqrt(((1 + S11)^2 - S21^2) / ((1 - S11)^2 - S21^2))
    z_num = (1.0 + s11)**2 - s21**2
    z_den = (1.0 - s11)**2 - s21**2
    z2 = z_num / z_den
    z = np.sqrt(z2)
    # Pick sign so Re(z) >= 0 (passive medium).
    z = np.where(z.real >= 0, z, -z)

    # Step 6: eps and mu
    eps = n / z
    mu = n * z

    return {
        "freq_ghz": freq_ghz,
        "K": K,
        "Gamma": Gamma,
        "T": T,
        "n": n,
        "z": z,
        "eps": eps,
        "mu": mu,
        "k0_m_inv": k0,
        "slab_thickness_m": L,
    }


def find_zero_crossing(freq: np.ndarray, values: np.ndarray, direction: str = "descending") -> float | None:
    """Find the first frequency at which `values` crosses zero in the given
    direction. Linear interpolation between samples. Returns None if no
    crossing detected.
    """
    n = len(values)
    for i in range(n - 1):
        v0, v1 = values[i], values[i + 1]
        if direction == "descending" and v0 > 0 and v1 <= 0:
            t = v0 / (v0 - v1)
            return float(freq[i] + t * (freq[i + 1] - freq[i]))
        if direction == "ascending" and v0 < 0 and v1 >= 0:
            t = -v0 / (v1 - v0)
            return float(freq[i] + t * (freq[i + 1] - freq[i]))
    return None


def make_plot(freq: np.ndarray, eff: dict, out_path: Path, target_ghz: float) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not installed; skipping plot.")
        return

    fig, axes = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

    ax = axes[0]
    ax.plot(freq, eff["eps"].real, label="Re(ε)", color="C0", linewidth=2)
    ax.plot(freq, eff["eps"].imag, label="Im(ε)", color="C0", linestyle="--", alpha=0.7)
    ax.plot(freq, eff["mu"].real,  label="Re(μ)", color="C3", linewidth=2)
    ax.plot(freq, eff["mu"].imag,  label="Im(μ)", color="C3", linestyle="--", alpha=0.7)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.axvline(target_ghz, color="green", linestyle=":", label=f"target {target_ghz:.1f} GHz")
    ax.set_ylabel("ε, μ  (effective)")
    ax.set_title("Schurig 2006 ELC -- effective parameters from NRW retrieval")
    ax.legend(loc="best", ncol=3, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-20, 20)   # clip wild excursions for readability

    ax = axes[1]
    ax.plot(freq, np.abs(eff["T"])**2,                 label="|T|² (transmission)", color="C2")
    ax.plot(freq, np.abs(eff["Gamma"])**2,             label="|Γ|² (reflection)",   color="C1")
    ax.axvline(target_ghz, color="green", linestyle=":")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|T|², |Γ|²")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1.05)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Plot saved: {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=Path("D:/Claude/MetaClaw/runs/elc_11ghz/Experiment/cst_design"),
    )
    ap.add_argument(
        "--slab-thickness-nm",
        type=float,
        default=203_000.0,
        help="Effective slab thickness L (nm). Default = h_FR4 from DESIGN. "
             "NRW result scales linearly with this; pick a consistent value.",
    )
    ap.add_argument(
        "--target-ghz",
        type=float,
        default=11.0,
    )
    ap.add_argument(
        "--no-plot",
        action="store_true",
    )
    args = ap.parse_args(argv)

    csv_path = args.run_dir / "s_params_complex.csv"
    if not csv_path.exists():
        print(f"[ERROR] {csv_path} not found. Run build_elc_11ghz.py first.")
        return 2

    print(f"Reading {csv_path}...")
    freq_ghz, s11, s21, meta = read_complex_s_csv(csv_path)
    print(f"  {len(freq_ghz)} freq points from {freq_ghz[0]:.2f} to {freq_ghz[-1]:.2f} GHz")

    L_m = args.slab_thickness_nm * 1e-9   # nm -> m
    print(f"Applying Smith/Soukoulis 2002 retrieval with L = {args.slab_thickness_nm/1e6:.3f} mm...")
    eff = nrw_retrieval(freq_ghz, s11, s21, slab_thickness_m=L_m)

    # Write per-frequency effective params CSV.
    out_csv = args.run_dir / "eff_params.csv"
    with out_csv.open("w") as f:
        f.write(f"# NRW retrieval, slab L = {args.slab_thickness_nm:.1f} nm "
                f"({args.slab_thickness_nm/1e6:.3f} mm)\n")
        f.write("# Reference: Smith/Schultz/Markos/Soukoulis PRB 65, 195104 (2002)\n")
        f.write("freq_GHz,Re_eps,Im_eps,Re_mu,Im_mu,Re_n,Im_n,Re_z,Im_z\n")
        for i in range(len(freq_ghz)):
            f.write(
                f"{freq_ghz[i]:.6f},"
                f"{eff['eps'][i].real:.6e},{eff['eps'][i].imag:.6e},"
                f"{eff['mu'][i].real:.6e},{eff['mu'][i].imag:.6e},"
                f"{eff['n'][i].real:.6e},{eff['n'][i].imag:.6e},"
                f"{eff['z'][i].real:.6e},{eff['z'][i].imag:.6e}\n"
            )
    print(f"Wrote {out_csv}")

    # Detect zero-crossings of Re(eps) -- this is the negative-permittivity band.
    f_zero_desc = find_zero_crossing(freq_ghz, eff["eps"].real, "descending")
    f_zero_asc  = find_zero_crossing(freq_ghz, eff["eps"].real, "ascending")
    # And the |S21| dip (transmission notch).
    s21_mag = np.abs(s21)
    idx_min = int(np.argmin(s21_mag))
    f_S21_dip = float(freq_ghz[idx_min])
    S21_at_dip = float(s21_mag[idx_min])

    # Detect a "peak" in Re(eps): the high-magnitude excursion near the
    # resonance pole. Within the swept band, the maximum of Re(eps) is a
    # decent proxy. (For Lorentzian, Re(eps) actually crosses 0 then dips
    # to -inf then comes back through 0; finite Q smooths this.)
    re_eps_in_band = eff["eps"].real[(freq_ghz > 6) & (freq_ghz < 18)]
    fr_in_band = freq_ghz[(freq_ghz > 6) & (freq_ghz < 18)]
    idx_eps_peak = int(np.argmax(re_eps_in_band))
    f_eps_peak = float(fr_in_band[idx_eps_peak]) if len(re_eps_in_band) else None
    eps_peak_val = float(re_eps_in_band[idx_eps_peak]) if len(re_eps_in_band) else None

    summary = {
        "slab_thickness_nm": args.slab_thickness_nm,
        "freq_band_ghz": [float(freq_ghz[0]), float(freq_ghz[-1])],
        "n_points": int(len(freq_ghz)),
        "re_eps_zero_crossing_descending_ghz": f_zero_desc,
        "re_eps_zero_crossing_ascending_ghz":  f_zero_asc,
        "negative_eps_band_ghz": (
            [f_zero_desc, f_zero_asc]
            if (f_zero_desc is not None and f_zero_asc is not None
                and f_zero_asc > f_zero_desc)
            else None
        ),
        "S21_dip_ghz": f_S21_dip,
        "S21_at_dip": S21_at_dip,
        "re_eps_peak_in_band_ghz": f_eps_peak,
        "re_eps_peak_value": eps_peak_val,
        "target_ghz": args.target_ghz,
        "target_in_negative_eps_band": (
            f_zero_desc is not None and f_zero_asc is not None
            and f_zero_desc <= args.target_ghz <= f_zero_asc
        ),
    }
    summary_path = args.run_dir / "eff_params_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {summary_path}")
    print(json.dumps(summary, indent=2))

    if not args.no_plot:
        plot_path = args.run_dir / "eff_params_plot.png"
        make_plot(freq_ghz, eff, plot_path, args.target_ghz)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
