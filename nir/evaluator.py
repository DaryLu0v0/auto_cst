"""nir/evaluator.py -- spectrum scoring for the NIR disk-MIM absorber.

Two score formulas:

LEGACY (default, matches auto_cst/evaluator.py:466):
    score = |f_peak - target| + 0.2 * max(0, 0.90 - peak_abs)
  Pros: minimal, matches existing project convention.
  Cons: when there is no peak at all (peak_abs near 0), the abs_penalty
  is a constant offset and doesn't differentiate proposals -- the agent
  loses gradient. Also ignores FWHM entirely.

IMPROVED (opt-in via score_design(... formula='improved')):
    score = |f_peak - target| + alpha * (1 - peak_abs)^2
            + beta * |fwhm_thz - target_fwhm_thz|        if target_fwhm given
  Pros: quadratic abs term gives gradient even at low absorption (drives
  exploration when no clear peak is present); explicit FWHM term aligns
  the optimizer with the user's bandwidth target.
  Defaults: alpha=0.5 (heavier than legacy 0.2), beta=0.1.

Both formulas: lower is better, 0.0 = perfect.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Tuple

import numpy as np


# --- Scoring weights (do not change during a run) ---
ABSORPTION_WEIGHT = 0.2
ABSORPTION_THRESHOLD = 0.90

# --- Default search window (THz) -- matches runner.py defaults ---
DEFAULT_FREQ_MIN = 100.0
DEFAULT_FREQ_MAX = 300.0


def load_spectrum_csv(path: str | Path) -> Tuple[np.ndarray, np.ndarray]:
    """Read a tab-separated 2-column CSV (freq_THz, value). '#' lines are comments."""
    freqs: list[float] = []
    vals: list[float] = []
    with open(path, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or row[0].strip().startswith("#"):
                continue
            try:
                freqs.append(float(row[0].strip()))
                vals.append(float(row[1].strip()))
            except (ValueError, IndexError):
                continue
    if not freqs:
        raise ValueError(f"No valid data rows in {path}")
    return np.asarray(freqs), np.asarray(vals)


def _apply_window(freq: np.ndarray, data: np.ndarray,
                  freq_min: float, freq_max: float
                  ) -> Tuple[np.ndarray, np.ndarray]:
    mask = (freq >= freq_min) & (freq <= freq_max)
    if not np.any(mask):
        return freq, data
    return freq[mask], data[mask]


def detect_resonance(freq: np.ndarray, absorptance: np.ndarray,
                     *, freq_min: float = DEFAULT_FREQ_MIN,
                     freq_max: float = DEFAULT_FREQ_MAX
                     ) -> Tuple[float, float, float]:
    """Find the dominant absorption peak inside the search window.

    Returns (f_peak_thz, peak_absorptance, fwhm_thz). FWHM is NaN if the
    half-max crossings cannot be located inside the window.
    """
    f_win, a_win = _apply_window(freq, absorptance, freq_min, freq_max)
    if len(f_win) == 0:
        return float("nan"), 0.0, float("nan")

    idx_max = int(np.argmax(a_win))
    f_peak = float(f_win[idx_max])
    a_peak = float(a_win[idx_max])

    # FWHM: walk left and right until value drops below a_peak/2
    half = a_peak / 2.0
    if a_peak <= 0:
        return f_peak, a_peak, float("nan")

    # Left crossing
    left_idx = idx_max
    while left_idx > 0 and a_win[left_idx] > half:
        left_idx -= 1
    if left_idx == idx_max:
        # Peak is at the leftmost sample
        f_left = float(f_win[0])
    else:
        # Linear interpolate between samples [left_idx, left_idx+1]
        x1, x2 = f_win[left_idx], f_win[left_idx + 1]
        y1, y2 = a_win[left_idx], a_win[left_idx + 1]
        if y2 != y1:
            f_left = float(x1 + (half - y1) * (x2 - x1) / (y2 - y1))
        else:
            f_left = float(x2)

    # Right crossing
    right_idx = idx_max
    while right_idx < len(a_win) - 1 and a_win[right_idx] > half:
        right_idx += 1
    if right_idx == idx_max:
        f_right = float(f_win[-1])
    else:
        x1, x2 = f_win[right_idx - 1], f_win[right_idx]
        y1, y2 = a_win[right_idx - 1], a_win[right_idx]
        if y2 != y1:
            f_right = float(x1 + (half - y1) * (x2 - x1) / (y2 - y1))
        else:
            f_right = float(x1)

    # If we hit an edge without crossing half-max, FWHM is unreliable
    edge_hit_left = (a_win[0] > half)
    edge_hit_right = (a_win[-1] > half)
    if edge_hit_left or edge_hit_right:
        fwhm = float("nan")
    else:
        fwhm = float(f_right - f_left)

    return f_peak, a_peak, fwhm


def score_design(f_peak_thz: float, abs_peak: float,
                 *, target_thz: float = 193.41,
                 fwhm_thz: float = float("nan"),
                 target_fwhm_thz: float | None = None,
                 formula: str = "legacy",
                 alpha_abs: float = 0.5,
                 beta_fwhm: float = 0.1) -> float:
    """Single scalar score (lower is better).

    formula:
      'legacy'   -- score = |f - target| + 0.2 * max(0, 0.90 - peak_abs)
      'improved' -- score = |f - target| + alpha * (1 - peak_abs)^2
                            + beta * |fwhm - target_fwhm|  (if target_fwhm given)
    """
    if not np.isfinite(f_peak_thz):
        return 999.0
    freq_error = abs(f_peak_thz - target_thz)

    if formula == "improved":
        # Quadratic absorption penalty: gradient even at low abs.
        # 1.0 at abs=0; 0.0 at abs=1.0; rewards getting CLOSE to a real peak.
        abs_penalty = (1.0 - max(0.0, min(1.0, abs_peak))) ** 2
        score = freq_error + alpha_abs * abs_penalty
        if target_fwhm_thz is not None and np.isfinite(fwhm_thz):
            score += beta_fwhm * abs(fwhm_thz - target_fwhm_thz)
        return float(score)

    # legacy
    mag_penalty = max(0.0, ABSORPTION_THRESHOLD - abs_peak)
    return float(freq_error + ABSORPTION_WEIGHT * mag_penalty)


def evaluate_csv(absorptance_csv: str | Path,
                 *, target_thz: float = 193.41,
                 freq_min: float = DEFAULT_FREQ_MIN,
                 freq_max: float = DEFAULT_FREQ_MAX) -> dict:
    """End-to-end: load CSV, detect peak, score. Returns same shape as runner result."""
    freq, absorptance = load_spectrum_csv(absorptance_csv)
    f_peak, abs_peak, fwhm = detect_resonance(
        freq, absorptance, freq_min=freq_min, freq_max=freq_max,
    )
    score = score_design(f_peak, abs_peak, target_thz=target_thz)
    return {
        "f_peak_thz": f_peak,
        "abs_at_peak": abs_peak,
        "fwhm_thz": fwhm,
        "score": score,
        "freq_error": abs(f_peak - target_thz) if np.isfinite(f_peak) else float("nan"),
        "abs_penalty": max(0.0, ABSORPTION_THRESHOLD - abs_peak),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m nir.evaluator <Absorptance.csv> [target_thz]")
        sys.exit(1)
    csv_path = sys.argv[1]
    target = float(sys.argv[2]) if len(sys.argv) > 2 else 193.41
    res = evaluate_csv(csv_path, target_thz=target)
    for k, v in res.items():
        print(f"  {k}: {v}")
