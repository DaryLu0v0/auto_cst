"""agent_1x1.py -- 1x1-informed broadband absorber optimization (v3).

Uses pre-computed 1x1 absorptance data (12-22 um wide range) to select
geometries whose absorption peaks tile the 14-18 um target band, then
iteratively refines by swapping cells that target spectral weak spots.

v3 improvements (edge-cluster reinforcement):
  - Edge-weighted bin scoring: 17-18 um bins get 3x weight in greedy tiling
  - Reserved slots for beyond-band (18-20 um) candidates whose absorption
    tails contribute to the 17-18 um edge region
  - Extended tiling range: 14-20 um (not just 14-18) to capture tail effects
  - Edge-cluster shuffle strategy: when 17-18 um is weak, replace multiple
    cells with a mix of 17-18 um and 18-20 um candidates simultaneously
  - Wider swap search for edge weakness (3.5 um radius, 7 cells x 15 cands)

v2 improvements (retained):
  - Wider candidate lookup: 12-22 um peaks (not just 14-18) for more options
  - Swap memory: tracks failed swaps to avoid oscillation
  - Multi-swap strategies on stagnation (shuffle, perturbation, random inject)
  - No external LLM API -- all reasoning is deterministic

Usage:
    python agent_1x1.py                  # default: seed + 10 iterations
    python agent_1x1.py --max-iter 20    # more iterations
    python agent_1x1.py --seed-only      # just seed, no iteration
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# Force UTF-8 stdout/stderr
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
DESIGN_PY = HERE / "design.py"
RESULTS_TSV = HERE / "results.tsv"
EXPORTS_DIR = HERE / "exports"
RUNNER_PY = HERE / "runner.py"
CSV_1X1 = Path(r"D:\Dary\agent\broad\RAG\CST 1by1\CST 1by1\absorptance_analysis_1by1.csv")

# ---------------------------------------------------------------------------
# Band and cell config
# ---------------------------------------------------------------------------
PITCH = 4.0
BAND_LO_UM = 14.0
BAND_HI_UM = 18.0
# Wider range for candidate lookup (gives more options at band edges)
LOOKUP_LO_UM = 12.0
LOOKUP_HI_UM = 22.0
N_CELLS = 25  # 5x5 grid

# Constraint bounds (from constraints.py)
MIN_X, MAX_X = 0.1, 1.8
MIN_W, MAX_W = 0.05, 1.5
MIN_G, MAX_G = 0.1, 3.5
MIN_R1 = 0.15
MIN_R2 = 0.02


# ---------------------------------------------------------------------------
# Swap memory -- prevents oscillation
# ---------------------------------------------------------------------------
class SwapMemory:
    """Tracks failed swaps to avoid repeating them."""

    def __init__(self):
        self._failed: Set[str] = set()   # "cell_idx|g|w|x" keys of failed swaps
        self._tried_combos: Set[str] = set()  # "cell_idx|new_g|new_w|new_x" tried

    def _key(self, cell_idx: int, cell: dict) -> str:
        return f"{cell_idx}|{cell['g']:.4f}|{cell['w']:.4f}|{cell['x']:.4f}"

    def record_swap(self, cell_idx: int, new_cell: dict):
        """Record a swap we're about to try."""
        self._tried_combos.add(self._key(cell_idx, new_cell))

    def record_failure(self, cell_idx: int, new_cell: dict):
        """Record that a swap was tried and didn't improve."""
        self._failed.add(self._key(cell_idx, new_cell))

    def is_failed(self, cell_idx: int, new_cell: dict) -> bool:
        """Check if this exact swap was previously tried and failed."""
        return self._key(cell_idx, new_cell) in self._failed

    def is_tried(self, cell_idx: int, new_cell: dict) -> bool:
        """Check if this swap was already attempted."""
        return self._key(cell_idx, new_cell) in self._tried_combos

    @property
    def n_failed(self) -> int:
        return len(self._failed)

    @property
    def n_tried(self) -> int:
        return len(self._tried_combos)

    def clear(self):
        """Reset memory (e.g., after a major restructure)."""
        self._failed.clear()
        self._tried_combos.clear()


# ---------------------------------------------------------------------------
# 1x1 lookup table
# ---------------------------------------------------------------------------

def load_1x1_candidates() -> List[dict]:
    """Load 1x1 absorptance CSV and build candidate list.

    Uses LOOKUP_LO_UM..LOOKUP_HI_UM (12-22 um) for wider coverage,
    then computes overlap with the actual target band (14-18 um).
    """
    rows = []
    with open(CSV_1X1, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    candidates = []
    for r in rows:
        if r["has_abs_above_0.9"] != "True":
            continue

        ranges_str = r["impulse_ranges_um"]
        peaks_str = r["impulse_peak_wavelengths_um"]
        if not ranges_str or not peaks_str:
            continue

        g = float(r["g"])
        w = float(r["w"])
        x = float(r["x"])

        # Check 5x5 constraints
        r1 = PITCH / 2.0 - x
        r2 = r1 - w
        if r1 < MIN_R1 or r2 < MIN_R2 or g >= 2.0 * r2:
            continue
        if x < MIN_X or x > MAX_X or w < MIN_W or w > MAX_W or g < MIN_G or g > MAX_G:
            continue

        ranges = []
        for rng in ranges_str.split(";"):
            lo, hi = rng.split("-")
            ranges.append((float(lo), float(hi)))
        peaks = [float(p) for p in peaks_str.split(";")]

        # Calculate overlap with TARGET band (14-18 um) for scoring
        band_coverage = 0.0
        band_peaks = []
        band_ranges = []
        for (rlo, rhi), pk in zip(ranges, peaks):
            overlap_lo = max(rlo, BAND_LO_UM)
            overlap_hi = min(rhi, BAND_HI_UM)
            if overlap_hi > overlap_lo:
                band_coverage += overlap_hi - overlap_lo
                band_peaks.append(pk)
                band_ranges.append((max(rlo, BAND_LO_UM), min(rhi, BAND_HI_UM)))

        # Calculate overlap with WIDE LOOKUP range (12-22 um)
        wide_coverage = 0.0
        wide_peaks = []
        wide_ranges = []
        for (rlo, rhi), pk in zip(ranges, peaks):
            overlap_lo = max(rlo, LOOKUP_LO_UM)
            overlap_hi = min(rhi, LOOKUP_HI_UM)
            if overlap_hi > overlap_lo:
                wide_coverage += overlap_hi - overlap_lo
                wide_peaks.append(pk)
                wide_ranges.append((overlap_lo, overlap_hi))

        # Include candidates with peaks in the wider 12-22 um range
        if wide_coverage <= 0 and band_coverage <= 0:
            continue

        all_peaks = peaks
        all_ranges = ranges

        candidates.append({
            "g": g, "w": w, "x": x,
            "r1": r1, "r2": r2,
            "arm_len": r2 - g / 2.0,
            "band_coverage_um": band_coverage,
            "band_peaks": band_peaks,
            "band_ranges": band_ranges,
            "wide_coverage_um": wide_coverage,
            "wide_peaks": wide_peaks,
            "wide_ranges": wide_ranges,
            "all_peaks": all_peaks,
            "all_ranges": all_ranges,
            "source": r["source_file"],
            "run_id": r["run_id"],
            "n_impulses": int(r["n_impulses_above_0.9"]),
        })

    return candidates


def _bin_weight(wl_center: float) -> float:
    """Edge-weighted scoring: bins near 17-18 um get higher weight.

    Physics rationale: band edges need MORE resonator density because
    each cell's absorption drops off rapidly away from its peak.
    The 17-18 um edge is historically the weakest sub-band.

    Weights tuned to avoid over-correction: must still allocate ~10-12
    cells to 14-17 um (mid-band) while reinforcing 17-18 um with ~8-10 cells.
    """
    if wl_center >= 17.5:
        return 2.0   # strong weight on 17.5-18 um (weakest zone)
    elif wl_center >= 17.0:
        return 1.8   # strong weight on 17-17.5 um
    elif wl_center >= 16.5:
        return 1.3   # moderate boost for transition
    elif wl_center >= 15.0:
        return 1.4   # boost 15-16.5 um -- sparse candidate zone, needs allocation
    elif wl_center <= 14.5:
        return 1.2   # slight boost for low-edge
    return 1.0       # nominal for 14.5-15 um


def greedy_band_tiling(candidates: List[dict], n_cells: int = N_CELLS) -> List[dict]:
    """Select n_cells geometries to maximally tile the 14-18 um band.

    v3 Strategy -- edge-cluster reinforcement:
    1. Divide band into fine bins (0.1 um) with EDGE WEIGHTS (17-18um gets 3x)
    2. EXTENDED band: include 18-20 um as "tail contribution" bins
       (candidates with peaks there contribute to 17-18 um via absorption tails)
    3. Greedily pick the candidate that covers the most weight-uncovered bins
    4. Reserve 3-4 slots specifically for 18-20 um tail candidates
    5. When in-band candidates exhaust, pick edge candidates with extra weight
    """
    # Extended bin range: 14-20 um (extra 18-20 um for tail contribution)
    EXTENDED_HI = 20.0
    bin_edges = np.arange(BAND_LO_UM, EXTENDED_HI + 0.05, 0.1)
    n_bins = len(bin_edges) - 1
    coverage = np.zeros(n_bins, dtype=float)

    # Precompute bin weights
    bin_weights = np.array([
        _bin_weight((bin_edges[bi] + bin_edges[bi + 1]) / 2.0)
        if bin_edges[bi + 1] <= BAND_HI_UM else
        0.8 if bin_edges[bi] < 19.0 else  # 18-19 um: tail zone (moderate)
        0.3  # 19-20 um: weak tail contribution (don't over-allocate)
        for bi in range(n_bins)
    ])

    selected = []
    used_indices = set()

    # Phase A: Force-allocate cells for each 1-um sub-band to ensure
    # spectral continuity for 2D coupling. Without this, the greedy
    # algorithm over-allocates to 17-18 um and leaves 15-16 um empty,
    # creating uncoupable vertical gaps in the 2D grid.
    #
    # Allocation targets (out of 25 cells):
    #   14-15 um:  4 cells (band edge, needs support)
    #   15-16 um:  4 cells (sparse candidate zone, needs forced allocation)
    #   16-17 um:  4 cells (transition, moderate)
    #   17-18 um:  8 cells (historically weakest, heaviest allocation)
    #   18-20 um:  3 cells (beyond-band tail contribution)
    #   spare:     2 cells (greedy fill)
    sub_band_targets = [
        (14.0, 15.0, 4),
        (15.0, 16.0, 4),
        (16.0, 17.0, 4),
        (17.0, 18.0, 8),
        (18.0, 20.0, 3),
    ]

    for sb_lo, sb_hi, n_target in sub_band_targets:
        # Find candidates with peaks in this sub-band
        sb_cands = []
        for ci, c in enumerate(candidates):
            if ci in used_indices:
                continue
            for pk in c["all_peaks"]:
                if sb_lo <= pk < sb_hi:
                    sb_cands.append((ci, c, abs(pk - (sb_lo + sb_hi) / 2.0), pk))
                    break
        sb_cands.sort(key=lambda t: t[2])  # closest to sub-band center first

        n_placed = 0
        for ci, c, _, pk in sb_cands:
            if n_placed >= n_target:
                break
            if ci in used_indices:
                continue
            selected.append(c)
            used_indices.add(ci)
            n_placed += 1
            # Update coverage
            for rlo, rhi in c["all_ranges"]:
                for bi in range(n_bins):
                    blo = bin_edges[bi]
                    bhi = bin_edges[bi + 1]
                    if rhi > blo and rlo < bhi:
                        coverage[bi] += 1.0

        print(f"  [sub-band {sb_lo:.0f}-{sb_hi:.0f} um] Placed {n_placed}/{n_target} cells"
              f" ({len(sb_cands)} candidates available)")

    # Phase B: Greedy fill remaining slots (spare cells)
    remaining = n_cells - len(selected)
    print(f"  [greedy fill] {remaining} remaining slots")
    for _ in range(remaining):
        best_idx = -1
        best_score = -1.0

        for ci, c in enumerate(candidates):
            if ci in used_indices:
                continue

            # Count weighted coverage contribution (in-band + extended)
            new_cov = 0.0
            total_cov = 0.0
            # Use all_ranges (not just band_ranges) to capture extended coverage
            all_relevant_ranges = c["band_ranges"][:]
            # Also include wide_ranges that fall in 14-20 um
            for rlo, rhi in c.get("wide_ranges", []):
                if rhi > BAND_LO_UM and rlo < EXTENDED_HI:
                    already = any(abs(rlo - br[0]) < 0.01 and abs(rhi - br[1]) < 0.01
                                  for br in all_relevant_ranges)
                    if not already:
                        all_relevant_ranges.append((max(rlo, BAND_LO_UM), min(rhi, EXTENDED_HI)))
            # Also check all_ranges for peaks in 18-20 um tail zone
            for rlo, rhi in c.get("all_ranges", []):
                if rhi > BAND_HI_UM and rlo < EXTENDED_HI:
                    clipped = (max(rlo, BAND_HI_UM), min(rhi, EXTENDED_HI))
                    already = any(abs(clipped[0] - br[0]) < 0.01 and abs(clipped[1] - br[1]) < 0.01
                                  for br in all_relevant_ranges)
                    if not already:
                        all_relevant_ranges.append(clipped)

            for rlo, rhi in all_relevant_ranges:
                for bi in range(n_bins):
                    blo = bin_edges[bi]
                    bhi = bin_edges[bi + 1]
                    if rhi > blo and rlo < bhi:
                        overlap = min(rhi, bhi) - max(rlo, blo)
                        w = bin_weights[bi]
                        total_cov += overlap * w
                        if coverage[bi] < 0.5:
                            new_cov += overlap * w

            # Score: weighted new coverage, then weighted total, then arm length
            score = new_cov * 10.0 + total_cov + c["arm_len"] * 0.1

            if score > best_score:
                best_score = score
                best_idx = ci

        if best_idx < 0 or best_score < 0.01:
            # No more in-band candidates; try wider-range candidates
            # Prefer those with peaks near band edges (14 um or 18 um)
            best_edge_score = -1.0
            for ci, c in enumerate(candidates):
                if ci in used_indices:
                    continue
                edge_score = 0.0
                for pk in c["all_peaks"]:
                    # Peaks in 12-14 um may couple with 14 um band edge
                    if LOOKUP_LO_UM <= pk < BAND_LO_UM:
                        edge_score += 3.0 - abs(pk - BAND_LO_UM)
                    # Peaks in 18-22 um: tail absorption helps 17-18 um
                    elif BAND_HI_UM < pk <= LOOKUP_HI_UM:
                        edge_score += 7.0 - abs(pk - BAND_HI_UM)  # stronger weight
                    # In-band near high edge
                    elif abs(pk - BAND_HI_UM) < 1.0:
                        edge_score += 4.0  # strong weight for 17-18um zone
                    elif abs(pk - BAND_LO_UM) < 1.0:
                        edge_score += 2.0

                if edge_score > best_edge_score:
                    best_edge_score = edge_score
                    best_idx = ci

        if best_idx < 0:
            break

        c = candidates[best_idx]
        selected.append(c)
        used_indices.add(best_idx)

        # Update coverage (all ranges in 14-20 um)
        for rlo, rhi in c.get("all_ranges", []):
            if rhi > BAND_LO_UM and rlo < EXTENDED_HI:
                for bi in range(n_bins):
                    blo = bin_edges[bi]
                    bhi = bin_edges[bi + 1]
                    if rhi > blo and rlo < bhi:
                        coverage[bi] += 1.0
        for rlo, rhi in c["band_ranges"]:
            for bi in range(n_bins):
                blo = bin_edges[bi]
                bhi = bin_edges[bi + 1]
                if rhi > blo and rlo < bhi:
                    if coverage[bi] == 0:
                        coverage[bi] += 1.0

    # Report edge-zone allocation
    edge_count = sum(1 for c in selected
                     if any(pk >= 16.5 for pk in c.get("all_peaks", [])))
    print(f"  Edge-zone cells (peaks >= 16.5 um): {edge_count}/{len(selected)}")

    return selected


# ---------------------------------------------------------------------------
# Design I/O
# ---------------------------------------------------------------------------

def write_design(params: dict) -> None:
    """Overwrite design.py with updated parameter values."""
    lines = [
        "# design.py -- the ONLY file the agent is allowed to edit",
        "# Ge broadband absorber with 5x5 CWC array.",
        "#",
        "# Each key maps 1:1 to a named CST parameter in the project.",
        "# Units: all lengths in micrometers (um).",
        "",
        "DESIGN = {",
    ]
    for i in range(5):
        for j in range(5):
            r1 = PITCH / 2.0 - params[f"x_{i}_{j}"]
            lines.append(f"    # Cell ({i},{j})  r1={r1:.4f}")
            for prefix in ("x", "g", "w"):
                key = f"{prefix}_{i}_{j}"
                val = params[key]
                lines.append(f'    "{key}": {val},')
            lines.append("")
    lines.append("}")
    lines.append("")
    DESIGN_PY.write_text("\n".join(lines), encoding="utf-8")


def read_design() -> dict:
    """Read current DESIGN dict from design.py."""
    import ast, re
    text = DESIGN_PY.read_text(encoding="utf-8")
    match = re.search(r"DESIGN\s*=\s*(\{.*\})", text, re.DOTALL)
    if not match:
        raise ValueError("Could not find DESIGN dict in design.py")
    return ast.literal_eval(match.group(1))


def _primary_peak(cell: dict) -> float:
    """Get the primary (longest-wavelength in-band) peak for a cell."""
    # Prefer band_peaks, then wide_peaks, then all_peaks
    for peaks_key in ("band_peaks", "wide_peaks", "all_peaks"):
        pks = cell.get(peaks_key, [])
        if pks:
            # Return the peak closest to the target band center (16 um)
            in_range = [p for p in pks if 12.0 <= p <= 22.0]
            if in_range:
                return max(in_range)  # longest wavelength = lowest freq
    return 16.0  # fallback


def _coupling_cost(arrangement: List[dict], size: int = 5) -> float:
    """Compute total 2D neighbor frequency mismatch (lower = better coupling).

    Sums |peak_i - peak_j| for all horizontal AND vertical neighbor pairs.
    """
    cost = 0.0
    for i in range(size):
        for j in range(size):
            pk = _primary_peak(arrangement[i * size + j])
            if j < size - 1:  # right neighbor
                npk = _primary_peak(arrangement[i * size + j + 1])
                cost += abs(pk - npk)
            if i < size - 1:  # bottom neighbor
                npk = _primary_peak(arrangement[(i + 1) * size + j])
                cost += abs(pk - npk)
    return cost


def arrange_cells_coupling_aware(selected: List[dict]) -> List[dict]:
    """Arrange 25 cells in the 5x5 grid to maximize 2D neighbor coupling.

    Physics: Adjacent CWCs with SIMILAR resonant frequencies couple strongly
    via near-field interaction in BOTH x and y directions, producing mode
    splitting that BROADENS the effective absorption bandwidth.

    A serpentine (1D) arrangement fails because vertical neighbors at row
    transitions can have huge frequency gaps (e.g. 14 um above 18 um).

    Instead, we use simulated annealing to minimize the total 2D neighbor
    frequency mismatch: sum of |peak_i - peak_j| over all horizontal AND
    vertical neighbor pairs. This finds a 2D-optimal placement where every
    cell is spectrally close to ALL its neighbors (up/down/left/right).
    """
    if len(selected) != N_CELLS:
        return selected

    # Start from a reasonable initial: sort by peak and lay in serpentine
    indexed = sorted(range(len(selected)), key=lambda k: _primary_peak(selected[k]))
    grid_order = []
    for row in range(5):
        cols = range(5) if row % 2 == 0 else range(4, -1, -1)
        for col in cols:
            grid_order.append(row * 5 + col)

    arranged = [None] * N_CELLS
    for k, orig_idx in enumerate(indexed):
        arranged[grid_order[k]] = selected[orig_idx]

    best_cost = _coupling_cost(arranged)
    best_arr = arranged[:]

    # Simulated annealing: swap pairs to minimize 2D coupling cost
    T = 5.0         # higher initial temp to escape local minima
    T_min = 0.005
    alpha = 0.9995   # slower cooling for thorough search
    n_swaps = 0
    n_iters = 0
    current_cost = best_cost

    rng = random.Random(42)  # deterministic for reproducibility
    while T > T_min and n_iters < 50000:
        n_iters += 1
        # Pick two random positions and try swapping
        a = rng.randint(0, N_CELLS - 1)
        b = rng.randint(0, N_CELLS - 1)
        if a == b:
            continue

        # Swap
        arranged[a], arranged[b] = arranged[b], arranged[a]
        new_cost = _coupling_cost(arranged)

        delta = new_cost - current_cost
        if delta < 0 or rng.random() < np.exp(-delta / T):
            # Accept this move
            current_cost = new_cost
            if new_cost < best_cost:
                best_cost = new_cost
                best_arr = arranged[:]
                n_swaps += 1
        else:
            # Reject: swap back
            arranged[a], arranged[b] = arranged[b], arranged[a]

        T *= alpha

    arranged = best_arr

    # Report the arrangement
    print(f"\n  2D coupling-aware arrangement (simulated annealing, {n_swaps} improving swaps):")
    print(f"  {'Pos':>5s}  {'(i,j)':>6s}  {'Peak um':>8s}  {'g':>7s}  {'w':>7s}  {'x':>7s}")
    for idx in range(N_CELLS):
        i, j = divmod(idx, 5)
        c = arranged[idx]
        pk = _primary_peak(c)
        print(f"  {idx:5d}  ({i},{j})  {pk:8.2f}  {c['g']:7.3f}  {c['w']:7.3f}  {c['x']:7.3f}")

    # Print 2D grid visualization
    print(f"\n  Peak wavelength grid (um):")
    for i in range(5):
        row_str = "    "
        for j in range(5):
            pk = _primary_peak(arranged[i * 5 + j])
            row_str += f"{pk:6.1f}"
        print(row_str)

    # Compute neighbor coupling quality metric
    total_coupling = 0.0
    n_pairs = 0
    max_gap = 0.0
    for i in range(5):
        for j in range(5):
            pk = _primary_peak(arranged[i * 5 + j])
            for di, dj in [(0, 1), (1, 0)]:
                ni, nj = i + di, j + dj
                if 0 <= ni < 5 and 0 <= nj < 5:
                    npk = _primary_peak(arranged[ni * 5 + nj])
                    gap = abs(pk - npk)
                    coupling = 1.0 / (1.0 + gap)
                    total_coupling += coupling
                    n_pairs += 1
                    max_gap = max(max_gap, gap)
    avg_coupling = total_coupling / n_pairs if n_pairs > 0 else 0
    print(f"\n  2D coupling metric: {avg_coupling:.3f} (1.0=perfect)")
    print(f"  Total 2D mismatch: {best_cost:.2f} um")
    print(f"  Max neighbor gap:  {max_gap:.2f} um")

    return arranged


def cells_to_design(selected: List[dict]) -> dict:
    """Convert list of 25 cell geometries to design dict."""
    design = {}
    for idx, cell in enumerate(selected):
        i, j = divmod(idx, 5)
        design[f"x_{i}_{j}"] = cell["x"]
        design[f"g_{i}_{j}"] = cell["g"]
        design[f"w_{i}_{j}"] = cell["w"]
    return design


# ---------------------------------------------------------------------------
# CST runner
# ---------------------------------------------------------------------------

def _kill_cst_processes():
    """Kill lingering CST user-session processes."""
    try:
        ps_cmd = (
            "Get-Process | Where-Object { $_.Name -like 'CST*' -and $_.SessionId -ne 0 } "
            "| ForEach-Object { Stop-Process -Id $_.Id -Force }"
        )
        subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
        )
        time.sleep(3)
    except Exception:
        pass


def run_cst(parent_id: str = "root", note: str = "") -> Dict[str, Any]:
    """Invoke runner.py and return the result row."""
    cmd = [
        sys.executable, "-u", str(RUNNER_PY),
        "--parent-id", parent_id,
        "--note", note[:100],
    ]
    print(f"  [CST] Running simulation...", end=" ", flush=True)
    t0 = time.time()

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(HERE), timeout=8000,
    )
    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    _kill_cst_processes()

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().split("\n")[-5:]
        for line in stderr_tail:
            print(f"  [CST stderr] {line}")

    # Read latest result
    if RESULTS_TSV.exists():
        with open(RESULTS_TSV, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)
        if rows:
            return rows[-1]

    return {"status": "error", "score": "999.0", "candidate_id": "0000"}


# ---------------------------------------------------------------------------
# Spectrum analysis
# ---------------------------------------------------------------------------

def analyze_spectrum(candidate_id: str) -> Optional[dict]:
    """Read absorptance spectrum and find weak spots in the 14-18 um band."""
    csv_path = EXPORTS_DIR / candidate_id / "Absorptance.csv"
    if not csv_path.exists():
        return None

    freq_list, abs_list = [], []
    with open(csv_path, "r") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            try:
                freq_list.append(float(parts[0]))
                abs_list.append(float(parts[1]))
            except (ValueError, IndexError):
                continue

    if not freq_list:
        return None

    freq = np.array(freq_list)
    absorptance = np.array(abs_list)

    # Filter to target band
    BAND_MIN_THZ = 300.0 / BAND_HI_UM
    BAND_MAX_THZ = 300.0 / BAND_LO_UM
    mask = (freq >= BAND_MIN_THZ) & (freq <= BAND_MAX_THZ)

    if not np.any(mask):
        return None

    f_band = freq[mask]
    a_band = absorptance[mask]
    wl_band = 300.0 / f_band

    mean_abs = float(np.mean(a_band))
    min_abs = float(np.min(a_band))
    min_idx = int(np.argmin(a_band))
    freq_at_min = float(f_band[min_idx])
    wl_at_min = 300.0 / freq_at_min

    # Find sub-band weaknesses (bin by 0.5 um)
    weak_spots = []
    for wl_lo in np.arange(BAND_LO_UM, BAND_HI_UM, 0.5):
        wl_hi = wl_lo + 0.5
        sub_mask = (wl_band >= wl_lo) & (wl_band < wl_hi)
        if np.any(sub_mask):
            sub_mean = float(np.mean(a_band[sub_mask]))
            if sub_mean < 0.85:
                weak_spots.append({
                    "wl_lo": wl_lo, "wl_hi": wl_hi,
                    "mean_abs": sub_mean,
                    "center_um": (wl_lo + wl_hi) / 2.0,
                })

    weak_spots.sort(key=lambda w: w["mean_abs"])

    return {
        "mean_abs": mean_abs,
        "min_abs": min_abs,
        "freq_at_min_thz": freq_at_min,
        "wl_at_min_um": wl_at_min,
        "weak_spots": weak_spots,
        "freq": freq,
        "absorptance": absorptance,
        "wl_band": wl_band,
        "a_band": a_band,
    }


# ---------------------------------------------------------------------------
# Iterative refinement (with swap memory)
# ---------------------------------------------------------------------------

def find_best_swap(
    current_design: dict,
    candidates: List[dict],
    weak_center_um: float,
    current_cells: List[dict],
    swap_memory: SwapMemory,
) -> Optional[Tuple[int, dict]]:
    """Find the best cell to swap to improve absorption at weak_center_um.

    v3: When weak spot is in 17-18 um, uses a wider search radius (3.5 um)
    and prefers beyond-band candidates (18-20 um peaks) for tail contribution.

    Returns (cell_index_to_replace, new_cell_geometry) or None.
    """
    # Wider search for edge weak spots
    is_edge_weak = weak_center_um >= 17.0
    search_radius = 3.5 if is_edge_weak else 2.5

    # Find candidate geometries with peaks near the weak spot
    target_candidates = []
    for c in candidates:
        best_dist = 999.0
        best_pk = 0.0
        for pk in c["all_peaks"]:
            dist = abs(pk - weak_center_um)
            if dist < best_dist:
                best_dist = dist
                best_pk = pk
        if best_dist < search_radius:
            # For edge weakness: bonus for beyond-band candidates (tail absorption)
            adjusted_dist = best_dist
            if is_edge_weak and best_pk > 18.0:
                adjusted_dist *= 0.7  # prefer beyond-band for tail contribution
            target_candidates.append((c, adjusted_dist, best_pk))

    if not target_candidates:
        return None

    # Sort by adjusted proximity to weak spot
    target_candidates.sort(key=lambda t: t[1])

    # Find which current cell is the most expendable
    cell_scores = []
    for ci, cell in enumerate(current_cells):
        other_peaks = []
        for cj, other in enumerate(current_cells):
            if cj != ci:
                other_peaks.extend(other.get("all_peaks", []))

        min_dist_to_weak = min(
            (abs(pk - weak_center_um) for pk in cell.get("all_peaks", [99])),
            default=99.0,
        )

        # Cells with peaks redundant with other cells are more expendable
        redundancy = 0.0
        for pk in cell.get("all_peaks", []):
            for opk in other_peaks:
                if abs(pk - opk) < 0.5:
                    redundancy += 1.0

        # For edge weakness: cells with peaks far from 17-18 um AND
        # redundant in 14-16 um are most expendable
        if is_edge_weak:
            in_strong_zone = sum(1 for pk in cell.get("all_peaks", [])
                                 if 14.0 <= pk <= 16.0)
            redundancy += in_strong_zone * 0.5  # boost expendability

        cell_scores.append((ci, min_dist_to_weak, redundancy))

    # Pick cell to replace: most redundant and farthest from weak spot
    cell_scores.sort(key=lambda s: (-s[2], -s[1]))

    # Try top 7 most expendable cells with top 15 target candidates
    # (larger search space for edge weakness)
    n_cells_try = 7 if is_edge_weak else 5
    n_cands_try = 15 if is_edge_weak else 10

    for ci, _, _ in cell_scores[:n_cells_try]:
        for new_cell, dist, pk in target_candidates[:n_cands_try]:
            # Skip if this swap was already tried and failed
            if swap_memory.is_failed(ci, new_cell):
                continue

            # Check it's not already in the design
            already_used = False
            for existing in current_cells:
                if (abs(existing["g"] - new_cell["g"]) < 0.001 and
                    abs(existing["w"] - new_cell["w"]) < 0.001 and
                    abs(existing["x"] - new_cell["x"]) < 0.001):
                    already_used = True
                    break
            if already_used:
                continue

            return ci, new_cell

    return None


def multi_cell_shuffle(
    current_cells: List[dict],
    candidates: List[dict],
    weak_spots: List[dict],
    swap_memory: SwapMemory,
    n_shuffle: int = 5,
) -> List[dict]:
    """Aggressive strategy: shuffle multiple cells at once when stagnating.

    v3: When the weak spot is at 17-18 um, uses "edge cluster" strategy:
    replace cells with a MIX of 17-18 um peak candidates AND 18-20 um
    beyond-band candidates whose absorption tails reinforce the edge.
    """
    cells = [copy.deepcopy(c) for c in current_cells]

    # Sort weak spots by severity
    targets = sorted(weak_spots, key=lambda w: w["mean_abs"])[:n_shuffle]

    # Check if primary weakness is at the 17-18 um edge
    edge_crisis = any(ws.get("center_um", 0) >= 17.0 for ws in targets)

    replaced = set()

    if edge_crisis:
        print("  [v3] Edge-cluster strategy: reinforcing 17-18 um with mixed candidates")
        # Gather ALL candidates with peaks in 16.5-20 um (in-band + beyond-band)
        edge_cands = []
        for c in candidates:
            for pk in c["all_peaks"]:
                if 16.5 <= pk <= 20.0:
                    # Weight: closer to 18 um = better
                    weight = 1.0 / (1.0 + abs(pk - 18.0))
                    edge_cands.append((c, weight, pk))
                    break
        edge_cands.sort(key=lambda t: -t[1])  # best weight first

        # Find most expendable cells (far from 17-18 um, redundant in 14-16 um)
        expendable = []
        for ci in range(len(cells)):
            if ci in replaced:
                continue
            cell_peaks = cells[ci].get("all_peaks", [])
            # Skip cells already targeting 17+ um
            if any(pk >= 16.5 for pk in cell_peaks):
                continue
            # Redundancy score: how many other cells cover similar bands
            redundancy = 0.0
            for pk in cell_peaks:
                for cj, other in enumerate(cells):
                    if cj == ci:
                        continue
                    for opk in other.get("all_peaks", []):
                        if abs(pk - opk) < 0.5:
                            redundancy += 1.0
            expendable.append((ci, redundancy))
        expendable.sort(key=lambda t: -t[1])  # most redundant first

        # Replace up to n_shuffle expendable cells with edge candidates
        for ci, _ in expendable[:n_shuffle]:
            if ci in replaced:
                continue
            for cand, weight, pk in edge_cands:
                if swap_memory.is_failed(ci, cand):
                    continue
                already_used = any(
                    abs(c["g"] - cand["g"]) < 0.001 and
                    abs(c["w"] - cand["w"]) < 0.001 and
                    abs(c["x"] - cand["x"]) < 0.001
                    for c in cells
                )
                if already_used:
                    continue
                print(f"  Edge-cluster swap cell {ci}: "
                      f"(g={cells[ci]['g']:.3f},w={cells[ci]['w']:.3f},x={cells[ci]['x']:.3f}) -> "
                      f"(g={cand['g']:.3f},w={cand['w']:.3f},x={cand['x']:.3f})")
                print(f"    Edge candidate peak at {pk:.1f} um (weight={weight:.2f})")
                cells[ci] = copy.deepcopy(cand)
                replaced.add(ci)
                swap_memory.record_swap(ci, cand)
                break

    # Standard weak-spot targeting (non-edge or remaining slots)
    for ws in targets:
        if len(replaced) >= n_shuffle:
            break
        # Find candidates for this weak spot
        target_cands = []
        search_r = 3.0 if ws.get("center_um", 0) >= 17.0 else 2.0
        for c in candidates:
            for pk in c["all_peaks"]:
                if abs(pk - ws["center_um"]) < search_r:
                    target_cands.append((c, abs(pk - ws["center_um"])))
                    break
        target_cands.sort(key=lambda t: t[1])

        # Find most expendable cell not already replaced
        for ci in range(len(cells)):
            if ci in replaced:
                continue
            cell_near = any(
                abs(pk - ws["center_um"]) < 1.0
                for pk in cells[ci].get("all_peaks", [])
            )
            if cell_near:
                continue

            for cand, _ in target_cands[:8]:
                if swap_memory.is_failed(ci, cand):
                    continue
                already_used = any(
                    abs(c["g"] - cand["g"]) < 0.001 and
                    abs(c["w"] - cand["w"]) < 0.001 and
                    abs(c["x"] - cand["x"]) < 0.001
                    for c in cells
                )
                if already_used:
                    continue

                print(f"  Shuffle-swap cell {ci}: "
                      f"(g={cells[ci]['g']:.3f},w={cells[ci]['w']:.3f},x={cells[ci]['x']:.3f}) -> "
                      f"(g={cand['g']:.3f},w={cand['w']:.3f},x={cand['x']:.3f})")
                print(f"    Targeting weak spot at {ws['center_um']:.1f} um")
                cells[ci] = copy.deepcopy(cand)
                replaced.add(ci)
                swap_memory.record_swap(ci, cand)
                break
            break

    if not replaced:
        # Fallback: random injection of untried candidates
        print("  Shuffle fallback: random injection of untried candidates")
        available = [c for c in candidates
                     if c["wide_coverage_um"] > 0 or c["band_coverage_um"] > 0]
        random.shuffle(available)
        for _ in range(min(3, len(available))):
            ci = random.randint(0, N_CELLS - 1)
            while ci in replaced:
                ci = random.randint(0, N_CELLS - 1)
            for cand in available:
                if not swap_memory.is_tried(ci, cand):
                    cells[ci] = copy.deepcopy(cand)
                    replaced.add(ci)
                    swap_memory.record_swap(ci, cand)
                    print(f"  Random inject cell {ci}: "
                          f"(g={cand['g']:.3f},w={cand['w']:.3f},x={cand['x']:.3f})")
                    break

    return cells


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def design_to_cells(design: dict, candidates: List[dict]) -> List[dict]:
    """Convert design dict back to cell list, matching against known candidates."""
    cells = []
    for idx in range(N_CELLS):
        i, j = divmod(idx, 5)
        g = design[f"g_{i}_{j}"]
        w = design[f"w_{i}_{j}"]
        x = design[f"x_{i}_{j}"]
        r1 = PITCH / 2.0 - x
        r2 = r1 - w

        # Try to match against a known candidate
        matched = None
        for c in candidates:
            if (abs(c["g"] - g) < 0.001 and
                abs(c["w"] - w) < 0.001 and
                abs(c["x"] - x) < 0.001):
                matched = copy.deepcopy(c)
                break

        if matched:
            cells.append(matched)
        else:
            # Build a minimal cell dict for unmatched geometries
            cells.append({
                "g": g, "w": w, "x": x,
                "r1": r1, "r2": r2,
                "arm_len": r2 - g / 2.0,
                "band_coverage_um": 0.0,
                "band_peaks": [],
                "band_ranges": [],
                "wide_coverage_um": 0.0,
                "wide_peaks": [],
                "wide_ranges": [],
                "all_peaks": [],
                "all_ranges": [],
                "source": "resumed",
                "run_id": "?",
                "n_impulses": 0,
            })

    return cells


def main():
    parser = argparse.ArgumentParser(
        description="1x1-informed broadband absorber optimization (v2)",
    )
    parser.add_argument("--max-iter", type=int, default=10,
                        help="Maximum refinement iterations (default 10)")
    parser.add_argument("--seed-only", action="store_true",
                        help="Only generate initial seed, don't iterate")
    parser.add_argument("--swaps-per-iter", type=int, default=3,
                        help="Max cell swaps per iteration (default 3)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from current design.py instead of re-seeding")
    parser.add_argument("--resume-score", type=float, default=None,
                        help="Starting best score when resuming (default: inf)")
    parser.add_argument("--resume-candidate", type=str, default=None,
                        help="Candidate ID of the current best when resuming")
    parser.add_argument("--report-interval", type=int, default=10,
                        help="Print milestone report every N iterations (default 10)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  1x1-Informed Broadband Absorber Optimization (v2)")
    print(f"  Target band: {BAND_LO_UM}-{BAND_HI_UM} um")
    print(f"  Lookup range: {LOOKUP_LO_UM}-{LOOKUP_HI_UM} um")
    print(f"  Max iterations: {args.max_iter}")
    if args.resume:
        print(f"  Mode: RESUME from current design.py")
    print(f"{'='*60}\n")

    # --- Load 1x1 lookup table ---
    print("Loading 1x1 absorptance data...")
    candidates = load_1x1_candidates()
    in_band = [c for c in candidates if c["band_coverage_um"] > 0]
    near_band = [c for c in candidates if c["wide_coverage_um"] > 0 and c["band_coverage_um"] == 0]
    print(f"  Total valid candidates (12-22 um): {len(candidates)}")
    print(f"  Candidates with peaks in {BAND_LO_UM}-{BAND_HI_UM} um: {len(in_band)}")
    print(f"  Near-band candidates (12-14 or 18-22 um only): {len(near_band)}")

    # Peak distribution summary
    peak_bins = {}
    for c in candidates:
        for pk in c["all_peaks"]:
            if LOOKUP_LO_UM <= pk <= LOOKUP_HI_UM:
                bin_key = f"{int(pk)}-{int(pk)+1}"
                peak_bins[bin_key] = peak_bins.get(bin_key, 0) + 1
    print(f"\n  Peak distribution (12-22 um):")
    for k in sorted(peak_bins.keys()):
        bar = "#" * min(peak_bins[k] // 2, 40)
        print(f"    {k:>6s} um: {peak_bins[k]:4d}  {bar}")

    if args.resume:
        # --- Resume from existing design.py ---
        print(f"\nResuming from current design.py...")
        design = read_design()
        selected = design_to_cells(design, candidates)
        matched = sum(1 for c in selected if c["source"] != "resumed")
        print(f"  Loaded {N_CELLS} cells ({matched} matched to 1x1 candidates)")
    else:
        # --- Phase 1: Greedy band-coverage seeding ---
        print(f"\nPhase 1: Greedy band-tiling seed ({N_CELLS} cells)...")
        selected = greedy_band_tiling(candidates, N_CELLS)
        print(f"  Selected {len(selected)} cells")

        # Show coverage summary
        print(f"\n  {'Cell':>4s}  {'g':>7s}  {'w':>7s}  {'x':>7s}  {'r1':>7s}  {'arm':>7s}  "
              f"{'band_peaks':>20s}  {'all_peaks':>25s}  {'band_cov':>8s}")
        print(f"  {'-'*110}")
        total_cov = 0.0
        for idx, c in enumerate(selected):
            bp = ",".join(f"{p:.1f}" for p in c["band_peaks"]) if c["band_peaks"] else "-"
            ap = ",".join(f"{p:.1f}" for p in c["all_peaks"])
            total_cov += c["band_coverage_um"]
            print(f"  {idx:4d}  {c['g']:7.4f}  {c['w']:7.4f}  {c['x']:7.4f}  "
                  f"{c['r1']:7.4f}  {c['arm_len']:7.4f}  {bp:>20s}  {ap:>25s}  {c['band_coverage_um']:7.2f}")

        # Arrange cells in grid for optimal neighbor coupling
        print(f"\nPhase 1b: Coupling-aware spatial arrangement...")
        selected = arrange_cells_coupling_aware(selected)

        # Convert to design dict
        design = cells_to_design(selected)
        write_design(design)
        print(f"\n  Seed design written to design.py")

    if args.seed_only:
        print("\n  --seed-only: stopping here.")
        return

    # --- Phase 2: Run CST and iterate ---
    print(f"\n{'='*60}")
    print(f"  Phase 2: CST Simulation + Iterative Refinement")
    print(f"  (with swap memory to prevent oscillation)")
    print(f"{'='*60}")

    swap_memory = SwapMemory()
    best_score = args.resume_score if args.resume_score is not None else float("inf")
    best_design = copy.deepcopy(design)
    best_candidate_id = args.resume_candidate if args.resume_candidate else "root"
    best_cells = [copy.deepcopy(c) for c in selected]
    current_cells = [copy.deepcopy(c) for c in selected]
    no_improve = 0
    total_no_improve = 0

    # Milestone tracking
    milestones = []  # list of (iter, score, mean_abs, min_abs, candidate_id)

    # Track swaps pending evaluation
    pending_swaps: List[Tuple[int, dict]] = []

    start_iter = 0 if not args.resume else 1  # skip iter 0 eval if resuming with known score

    for iteration in range(start_iter, args.max_iter + 1):
        print(f"\n{'-'*60}")
        if iteration == 0:
            print(f"  Iteration 0: Initial seed evaluation")
        else:
            print(f"  Iteration {iteration}/{args.max_iter}  |  "
                  f"Best score: {best_score:.6f}  |  "
                  f"No-improve streak: {no_improve}  |  "
                  f"Swap memory: {swap_memory.n_failed} failed / {swap_memory.n_tried} tried")
        print(f"{'-'*60}")

        # Run CST
        note = f"1x1v2 iter={iteration}"
        result = run_cst(parent_id=best_candidate_id, note=note)

        new_score = float(result.get("score", "999.0"))
        new_cid = result.get("candidate_id", "?")
        valid = result.get("valid", "false") == "true"

        print(f"  Result: score={new_score:.6f}, mean_abs={result.get('mean_abs', '?')}, "
              f"min_abs={result.get('min_abs', '?')}, "
              f"cov90={result.get('band_coverage_90', '?')}")

        if valid and new_score < best_score:
            improvement = best_score - new_score
            best_score = new_score
            best_design = read_design()
            best_candidate_id = new_cid
            best_cells = [copy.deepcopy(c) for c in current_cells]
            no_improve = 0
            total_no_improve = 0
            pending_swaps.clear()
            print(f"  >>> NEW BEST (improved by {improvement:.6f})")
        else:
            no_improve += 1
            total_no_improve += 1

            # Record pending swaps as failed
            for ci, nc in pending_swaps:
                swap_memory.record_failure(ci, nc)
                print(f"  [swap memory] Recorded failed swap: cell {ci} -> "
                      f"(g={nc['g']:.3f},w={nc['w']:.3f},x={nc['x']:.3f})")

            # Revert to best design
            write_design(best_design)
            current_cells = [copy.deepcopy(c) for c in best_cells]
            print(f"  Reverted to best design (score {best_score:.6f})")

        pending_swaps.clear()

        # Check termination
        if best_score < 0.02:
            print(f"\n  Target achieved! score={best_score:.6f} < 0.02")
            break

        if iteration >= args.max_iter:
            break

        # --- Analyze spectrum and plan swaps ---
        spectrum = analyze_spectrum(best_candidate_id)
        if spectrum is None:
            print("  Cannot analyze spectrum, using random swap")
            ci = random.randint(0, N_CELLS - 1)
            new_cell = random.choice(in_band) if in_band else random.choice(candidates)
            current_cells[ci] = copy.deepcopy(new_cell)
            pending_swaps.append((ci, new_cell))
            swap_memory.record_swap(ci, new_cell)
            design = cells_to_design(current_cells)
            write_design(design)
            continue

        print(f"\n  Spectrum analysis:")
        print(f"    Mean abs: {spectrum['mean_abs']:.4f}")
        print(f"    Min abs:  {spectrum['min_abs']:.4f} at {spectrum['wl_at_min_um']:.2f} um")
        if spectrum["weak_spots"]:
            print(f"    Weak sub-bands (<85% abs):")
            for ws in spectrum["weak_spots"][:5]:
                print(f"      {ws['wl_lo']:.1f}-{ws['wl_hi']:.1f} um: "
                      f"mean_abs={ws['mean_abs']:.4f}")
        else:
            print(f"    No sub-bands below 85% -- fine-tuning needed")

        # --- Stagnation handler ---
        if no_improve >= 5:
            print(f"\n  Stagnation detected ({no_improve} consecutive failures)")
            print(f"  Attempting multi-cell shuffle...")
            current_cells = multi_cell_shuffle(
                current_cells, candidates,
                spectrum["weak_spots"] if spectrum["weak_spots"] else [
                    {"center_um": spectrum["wl_at_min_um"], "mean_abs": spectrum["min_abs"]}
                ],
                swap_memory,
                n_shuffle=min(5, 2 + total_no_improve // 5),  # escalate with stagnation
            )
            design = cells_to_design(current_cells)
            write_design(design)
            no_improve = 0
            continue

        # --- Plan swaps targeting weak spots ---
        n_swaps = 0
        swapped = set()
        weak_targets = spectrum["weak_spots"][:args.swaps_per_iter] if spectrum["weak_spots"] else []

        if not weak_targets:
            weak_targets = [{
                "center_um": spectrum["wl_at_min_um"],
                "mean_abs": spectrum["min_abs"],
            }]

        for ws in weak_targets:
            if n_swaps >= args.swaps_per_iter:
                break

            swap_result = find_best_swap(
                best_design, candidates,
                ws["center_um"], current_cells,
                swap_memory,
            )
            if swap_result is None:
                continue

            ci, new_cell = swap_result
            if ci in swapped:
                continue

            old = current_cells[ci]
            print(f"\n  Swap cell {ci}: "
                  f"(g={old['g']:.3f},w={old['w']:.3f},x={old['x']:.3f}) -> "
                  f"(g={new_cell['g']:.3f},w={new_cell['w']:.3f},x={new_cell['x']:.3f})")
            print(f"    Targeting weak spot at {ws['center_um']:.1f} um")
            if new_cell["band_peaks"]:
                print(f"    New cell peaks: {[f'{p:.1f}' for p in new_cell['band_peaks']]}")
            if new_cell.get("wide_peaks"):
                wide_only = [p for p in new_cell["wide_peaks"] if p not in new_cell["band_peaks"]]
                if wide_only:
                    print(f"    Near-band peaks: {[f'{p:.1f}' for p in wide_only]}")

            current_cells[ci] = copy.deepcopy(new_cell)
            swap_memory.record_swap(ci, new_cell)
            pending_swaps.append((ci, new_cell))
            swapped.add(ci)
            n_swaps += 1

        if n_swaps == 0:
            # No good swaps found -- try small perturbation of parameters
            print("  No swap candidates found (all tried/failed), applying perturbation")
            ci = random.randint(0, N_CELLS - 1)
            cell = current_cells[ci]
            # Perturb g and x by +-10% (wider than v1's 5%)
            new_g = cell["g"] * (1.0 + random.uniform(-0.10, 0.10))
            new_x = cell["x"] * (1.0 + random.uniform(-0.10, 0.10))
            new_w = cell["w"] * (1.0 + random.uniform(-0.05, 0.05))
            new_g = max(MIN_G, min(MAX_G, new_g))
            new_x = max(MIN_X, min(MAX_X, new_x))
            new_w = max(MIN_W, min(MAX_W, new_w))
            r1 = PITCH / 2.0 - new_x
            r2 = r1 - new_w
            if r1 >= MIN_R1 and r2 >= MIN_R2 and new_g < 2.0 * r2:
                perturbed = {**cell, "g": new_g, "x": new_x, "w": new_w}
                current_cells[ci] = perturbed
                swap_memory.record_swap(ci, perturbed)
                pending_swaps.append((ci, perturbed))
                print(f"  Perturbed cell {ci}: g={cell['g']:.4f}->{new_g:.4f}, "
                      f"x={cell['x']:.4f}->{new_x:.4f}, w={cell['w']:.4f}->{new_w:.4f}")

        design = cells_to_design(current_cells)
        write_design(design)

        # --- Milestone report every N iterations ---
        if iteration > 0 and iteration % args.report_interval == 0:
            milestones.append((iteration, best_score, 1.0 - best_score,
                               result.get("min_abs", "?"), best_candidate_id))
            print(f"\n  {'='*60}")
            print(f"  MILESTONE REPORT (iter {iteration}/{args.max_iter})")
            print(f"  {'='*60}")
            print(f"  {'Iter':>6s}  {'Score':>10s}  {'Mean Abs':>10s}  {'Min Abs':>10s}  {'Candidate':>10s}")
            print(f"  {'-'*50}")
            for m_iter, m_score, m_mean, m_min, m_cid in milestones:
                print(f"  {m_iter:6d}  {m_score:10.6f}  {m_mean:10.4f}  {str(m_min):>10s}  {m_cid:>10s}")
            print(f"  {'='*60}")

    # --- Final report ---
    milestones.append((iteration, best_score, 1.0 - best_score,
                       "?", best_candidate_id))
    print(f"\n{'='*60}")
    print(f"  OPTIMIZATION COMPLETE (v2)")
    print(f"{'='*60}")
    print(f"  Target band: {BAND_LO_UM}-{BAND_HI_UM} um")
    print(f"  Lookup range: {LOOKUP_LO_UM}-{LOOKUP_HI_UM} um")
    print(f"  Best score:     {best_score:.6f}")
    print(f"  Best mean_abs:  {1.0 - best_score:.4f}")
    print(f"  Best candidate: {best_candidate_id}")
    print(f"  Swap memory: {swap_memory.n_failed} failed / {swap_memory.n_tried} tried")

    print(f"\n  MILESTONE SUMMARY:")
    print(f"  {'Iter':>6s}  {'Score':>10s}  {'Mean Abs':>10s}  {'Candidate':>10s}")
    print(f"  {'-'*40}")
    for m_iter, m_score, m_mean, m_min, m_cid in milestones:
        print(f"  {m_iter:6d}  {m_score:10.6f}  {m_mean:10.4f}  {m_cid:>10s}")


if __name__ == "__main__":
    main()
