"""evaluator.py -- broadband absorption scoring for Ge CWC absorber.

DO NOT MODIFY this file during agent runs.

Reads exported Absorptance spectrum and computes a broadband score
over the 14-18 um wavelength band (16.67-21.43 THz).

Score = 1 - mean(absorptance in band)

A perfect score of 0.0 means 100% average absorption across the band.
"""

import csv
import sys
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Band definition (14-18 um wavelength -> THz frequency)
# f = c / lambda = 300 / lambda_um  (with c in um*THz)
# ---------------------------------------------------------------------------
BAND_FREQ_MIN_THZ = 300.0 / 18.0   # 16.667 THz  (18 um)
BAND_FREQ_MAX_THZ = 300.0 / 14.0   # 21.429 THz  (14 um)


def _load_spectrum(csv_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Load frequency (THz) and absorptance from exported CSV.

    Expects a two-column tab-separated file: frequency, absorptance.
    Lines starting with '#' or containing non-numeric data are skipped.

    Returns (freq_thz, absorptance) arrays.
    """
    freq = []
    mag = []
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"Spectrum file not found: {csv_path}")

    with open(p, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            try:
                f_val = float(row[0].strip())
                m_val = float(row[1].strip())
                freq.append(f_val)
                mag.append(m_val)
            except (ValueError, IndexError):
                continue

    if len(freq) == 0:
        raise ValueError(f"No valid data rows in {csv_path}")

    return np.array(freq), np.array(mag)


def evaluate_candidate(export_path: str) -> dict:
    """Score one candidate design for broadband absorption.

    Parameters
    ----------
    export_path : str
        Path to exported Absorptance CSV (tab-separated).

    Returns
    -------
    dict with keys:
        score           : float -- 1 - mean_abs (minimize this)
        mean_abs        : float -- mean absorptance in band
        min_abs         : float -- minimum absorptance in band
        freq_at_min_thz : float -- frequency of minimum absorption
        band_coverage_90: float -- fraction of band with abs > 0.9
        valid           : bool  -- True if evaluation succeeded
    """
    freq, absorptance = _load_spectrum(export_path)

    # Filter to target band
    mask = (freq >= BAND_FREQ_MIN_THZ) & (freq <= BAND_FREQ_MAX_THZ)
    if not np.any(mask):
        # No data in target band -- try full range as fallback
        return {
            "score": 1.0,
            "mean_abs": 0.0,
            "min_abs": 0.0,
            "freq_at_min_thz": 0.0,
            "band_coverage_90": 0.0,
            "valid": False,
        }

    f_band = freq[mask]
    a_band = absorptance[mask]

    mean_abs = float(np.mean(a_band))
    min_abs = float(np.min(a_band))
    idx_min = int(np.argmin(a_band))
    freq_at_min = float(f_band[idx_min])
    band_coverage_90 = float(np.mean(a_band >= 0.90))

    score = 1.0 - mean_abs

    return {
        "score": round(score, 6),
        "mean_abs": round(mean_abs, 4),
        "min_abs": round(min_abs, 4),
        "freq_at_min_thz": round(freq_at_min, 4),
        "band_coverage_90": round(band_coverage_90, 4),
        "valid": True,
    }


if __name__ == "__main__":
    # Quick test: python evaluator.py <absorptance.csv>
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <absorptance.csv>")
        sys.exit(1)
    result = evaluate_candidate(sys.argv[1])
    for k, v in result.items():
        print(f"  {k}: {v}")
