"""evaluator.py -- fixed scoring function for CST autoresearch.

DO NOT MODIFY this file during agent runs.

Reads exported S-parameter data, detects the resonance, and returns a
single scalar score that the agent tries to minimize.

Score = frequency_error + weight_abs * absorption_penalty

Where:
  frequency_error   = |f_resonance - f_target|          (THz)
  absorption_penalty = max(0, threshold - absorption)    (dimensionless)

A perfect score of 0.0 means the resonance sits exactly at f_target
with absorption >= threshold.
"""

import csv
import sys
import numpy as np
from pathlib import Path


# ---------------------------------------------------------------------------
# Scoring weights (do not change during runs)
# ---------------------------------------------------------------------------
ABSORPTION_WEIGHT = 0.2    # how much to penalize weak resonance magnitude
ABSORPTION_THRESHOLD = 0.90  # minimum acceptable resonance magnitude

# Frequency search window: only look for resonance in this range (THz)
# Must be wide enough to find shifted resonances but narrow enough
# to exclude diffraction artifacts and higher-order modes.
FREQ_SEARCH_MIN = 0.3
FREQ_SEARCH_MAX = 1.0


def _load_spectrum(csv_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Load frequency (THz) and |S21|^2 magnitude from exported CSV.

    Expects a two-column CSV: frequency, S21_magnitude_linear.
    Lines starting with '#' or containing non-numeric data are skipped.

    Returns (freq_thz, s21_mag_squared) arrays.
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


def _apply_freq_window(
    freq: np.ndarray, data: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    """Restrict data to the search frequency window.

    Returns (freq_window, data_window, offset) where offset is the
    index of the first element in the window relative to the original array.
    """
    mask = (freq >= FREQ_SEARCH_MIN) & (freq <= FREQ_SEARCH_MAX)
    if not np.any(mask):
        # Fallback: use full range
        return freq, data, 0
    return freq[mask], data[mask], int(np.argmax(mask))


def detect_resonance_from_s11(
    freq: np.ndarray,
    reflection: np.ndarray,
) -> tuple[float, float]:
    """Find the dominant reflection peak (= SRR resonance).

    Searches only within [FREQ_SEARCH_MIN, FREQ_SEARCH_MAX] to
    exclude diffraction artifacts and higher-order modes.

    Returns (f_resonance_thz, peak_reflection_magnitude).
    """
    f_win, r_win, _ = _apply_freq_window(freq, reflection)
    idx_max = np.argmax(r_win)
    return float(f_win[idx_max]), float(r_win[idx_max])


def detect_resonance_from_reflectance(
    freq: np.ndarray,
    reflectance: np.ndarray,
) -> tuple[float, float]:
    """Find resonance from direct reflectance data within search window.

    Returns (f_resonance_thz, peak_reflectance).
    """
    f_win, r_win, _ = _apply_freq_window(freq, reflectance)
    idx_max = np.argmax(r_win)
    return float(f_win[idx_max]), float(r_win[idx_max])


def detect_resonance_from_rta(
    freq: np.ndarray,
    absorbance: np.ndarray,
) -> tuple[float, float]:
    """Find resonance from direct absorbance data within search window.

    Returns (f_resonance_thz, peak_absorption).
    """
    f_win, a_win, _ = _apply_freq_window(freq, absorbance)
    idx_max = np.argmax(a_win)
    return float(f_win[idx_max]), float(a_win[idx_max])


def evaluate_candidate(
    export_path: str,
    target_freq_thz: float,
    *,
    data_type: str = "s11",
) -> dict:
    """Score one candidate design.

    Parameters
    ----------
    export_path : str
        Path to exported spectrum CSV (tab-separated).
    target_freq_thz : float
        Desired resonance frequency in THz.
    data_type : str
        "s11" -- reflection |S11|^2, resonance = peak
        "reflectance" -- reflectance (0-1), resonance = peak
        "absorbance" -- direct absorbance (0-1), resonance = peak

    Returns
    -------
    dict with keys:
        score         : float -- the scalar to minimize
        f_res_thz     : float -- detected resonance frequency
        resonance_mag : float -- magnitude at resonance (reflectance or absorbance)
        freq_error    : float -- |f_res - f_target|
        mag_penalty   : float -- penalty if resonance is too weak
        valid         : bool  -- always True if we get here
    """
    freq, data = _load_spectrum(export_path)

    if data_type == "absorbance":
        f_res, res_mag = detect_resonance_from_rta(freq, data)
    elif data_type == "reflectance":
        f_res, res_mag = detect_resonance_from_reflectance(freq, data)
    else:  # s11
        f_res, res_mag = detect_resonance_from_s11(freq, data)

    freq_error = abs(f_res - target_freq_thz)
    # Penalize weak resonances (want strong reflection/absorption at resonance)
    mag_penalty = max(0.0, ABSORPTION_THRESHOLD - res_mag)
    score = freq_error + ABSORPTION_WEIGHT * mag_penalty

    return {
        "score": round(score, 6),
        "f_res_thz": round(f_res, 6),
        "abs_at_res": round(res_mag, 4),
        "freq_error": round(freq_error, 6),
        "abs_penalty": round(mag_penalty, 4),
        "valid": True,
    }


if __name__ == "__main__":
    # Quick test: python evaluator.py <csv_path> <target_freq>
    if len(sys.argv) < 3:
        print("Usage: python evaluator.py <spectrum.csv> <target_freq_thz>")
        sys.exit(1)
    result = evaluate_candidate(sys.argv[1], float(sys.argv[2]))
    for k, v in result.items():
        print(f"  {k}: {v}")
