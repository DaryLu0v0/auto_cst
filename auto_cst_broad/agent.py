"""agent.py -- Autonomous broadband Ge CWC absorber optimization agent.

Uses OpenAI ChatGPT to drive a keep/revert loop over CST simulations,
optimizing 75 geometric parameters across a 5x5 CWC array for maximum
broadband absorption over 14-18 um (16.67-21.43 THz).

Usage:
    python agent.py                        # default settings
    python agent.py --max-iter 20          # limit iterations
    python agent.py --model gpt-4o-mini    # use cheaper model
    python agent.py --reset                # reset to baseline design
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai

# Force UTF-8 stdout/stderr to avoid cp1252 encoding errors from LLM output
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

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = "gpt-5.4"
SCORE_THRESHOLD = 0.02       # stop when score < 0.02 (mean_abs > 0.98)
MAX_ITERATIONS = 30
STAGNATION_LIMIT = 10
HISTORY_WINDOW = 15

# ---------------------------------------------------------------------------
# Parameter metadata
# ---------------------------------------------------------------------------
PITCH = 4.0  # fixed for all cells

# Generate parameter order: iterate cells (i,j), then x/g/w within each
PARAM_ORDER = []
for _i in range(5):
    for _j in range(5):
        PARAM_ORDER.extend([f"x_{_i}_{_j}", f"g_{_i}_{_j}", f"w_{_i}_{_j}"])

PARAM_COMMENTS = {}
for _i in range(5):
    for _j in range(5):
        PARAM_COMMENTS[f"x_{_i}_{_j}"] = f"Margin cell ({_i},{_j}) um"
        PARAM_COMMENTS[f"g_{_i}_{_j}"] = f"Gap cell ({_i},{_j}) um"
        PARAM_COMMENTS[f"w_{_i}_{_j}"] = f"Width cell ({_i},{_j}) um"

# Baseline design (initial values from CST Parameters.json)
BASELINE_DESIGN = {
    "x_0_0": 0.612176, "g_0_0": 2.312922, "w_0_0": 0.221363,
    "x_0_1": 0.57817, "g_0_1": 0.930084, "w_0_1": 0.289548,
    "x_0_2": 0.734925, "g_0_2": 1.931786, "w_0_2": 0.289182,
    "x_0_3": 0.842, "g_0_3": 1.756, "w_0_3": 0.27,
    "x_0_4": 0.63333, "g_0_4": 0.890376, "w_0_4": 0.297083,
    "x_1_0": 0.49594, "g_1_0": 2.39482, "w_1_0": 0.29665,
    "x_1_1": 0.659848, "g_1_1": 1.20972, "w_1_1": 0.261248,
    "x_1_2": 0.777514, "g_1_2": 1.831314, "w_1_2": 0.296829,
    "x_1_3": 0.599324, "g_1_3": 2.288396, "w_1_3": 0.246478,
    "x_1_4": 0.622531, "g_1_4": 1.01655, "w_1_4": 0.240514,
    "x_2_0": 0.503884, "g_2_0": 2.377638, "w_2_0": 0.297297,
    "x_2_1": 0.686582, "g_2_1": 2.011018, "w_2_1": 0.297909,
    "x_2_2": 0.672568, "g_2_2": 2.067414, "w_2_2": 0.283725,
    "x_2_3": 0.739631, "g_2_3": 1.976696, "w_2_3": 0.262021,
    "x_2_4": 0.561951, "g_2_4": 0.907197, "w_2_4": 0.297458,
    "x_3_0": 0.604264, "g_3_0": 0.942585, "w_3_0": 0.285364,
    "x_3_1": 0.633691, "g_3_1": 1.24422, "w_3_1": 0.265817,
    "x_3_2": 0.607951, "g_3_2": 2.197768, "w_3_2": 0.283165,
    "x_3_3": 0.603431, "g_3_3": 1.16959, "w_3_3": 0.29239,
    "x_3_4": 0.612578, "g_3_4": 0.927284, "w_3_4": 0.298114,
    "x_4_0": 0.646842, "g_4_0": 0.887877, "w_4_0": 0.296742,
    "x_4_1": 0.602956, "g_4_1": 1.14672, "w_4_1": 0.291359,
    "x_4_2": 0.671005, "g_4_2": 2.043782, "w_4_2": 0.297104,
    "x_4_3": 0.837, "g_4_3": 1.726, "w_4_3": 0.29,
    "x_4_4": 0.619471, "g_4_4": 0.875487, "w_4_4": 0.233181,
}


# ---------------------------------------------------------------------------
# Design file I/O
# ---------------------------------------------------------------------------

def read_design() -> dict:
    """Read current DESIGN dict from design.py without importing it."""
    text = DESIGN_PY.read_text(encoding="utf-8")
    # Find the DESIGN = { ... } block (may span many lines)
    match = re.search(r"DESIGN\s*=\s*(\{.*\})", text, re.DOTALL)
    if not match:
        raise ValueError("Could not find DESIGN dict in design.py")
    return ast.literal_eval(match.group(1))


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


# ---------------------------------------------------------------------------
# Results TSV I/O
# ---------------------------------------------------------------------------

def read_results_tsv() -> List[Dict[str, str]]:
    """Parse results.tsv into a list of row dicts."""
    if not RESULTS_TSV.exists():
        return []
    with open(RESULTS_TSV, "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


# ---------------------------------------------------------------------------
# ChatGPT prompts
# ---------------------------------------------------------------------------

def _build_cell_table(design: dict) -> str:
    """Build a compact table of cell parameters sorted by outer radius r1."""
    rows = []
    for i in range(5):
        for j in range(5):
            x = design[f"x_{i}_{j}"]
            g = design[f"g_{i}_{j}"]
            w = design[f"w_{i}_{j}"]
            r1 = PITCH / 2.0 - x
            r2 = r1 - w
            arm = r2 - g / 2.0  # cross-arm length
            rows.append((i, j, x, g, w, r1, r2, arm))

    # Sort by r1 descending (largest radius = lowest resonance freq)
    rows.sort(key=lambda r: -r[5])

    lines = ["  Cell    x       g       w       r1      r2     arm_len"]
    lines.append("  " + "-" * 62)
    for i, j, x, g, w, r1, r2, arm in rows:
        flag = " !" if arm < 0.10 else ""
        lines.append(
            f"  ({i},{j})  {x:7.4f} {g:7.4f} {w:7.4f} {r1:7.4f} {r2:7.4f} {arm:7.4f}{flag}"
        )
    lines.append("")
    lines.append("  (!) = arm_length < 0.10 um — cross arms effectively absent, weak resonance")
    return "\n".join(lines)


def _read_spectrum_summary(candidate_id: str) -> str:
    """Read absorptance spectrum and return a sampled summary for the target band."""
    csv_path = EXPORTS_DIR / candidate_id / "Absorptance.csv"
    if not csv_path.exists():
        return "  (no spectrum data available)"

    import numpy as np

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
        return "  (no valid spectrum data)"

    freq = np.array(freq_list)
    absorptance = np.array(abs_list)

    BAND_MIN = 300.0 / 18.0   # 16.667 THz
    BAND_MAX = 300.0 / 14.0   # 21.429 THz

    lines = ["  freq_THz  wavelen_um  absorptance"]
    lines.append("  " + "-" * 38)

    # Sample at 0.5 THz intervals across the target band
    for f_target in np.arange(BAND_MIN, BAND_MAX + 0.25, 0.5):
        idx = np.argmin(np.abs(freq - f_target))
        f_actual = freq[idx]
        a_actual = absorptance[idx]
        lam = 300.0 / f_actual
        bar = "#" * int(a_actual * 40)
        lines.append(f"  {f_actual:8.3f}  {lam:9.2f}     {a_actual:.4f}  |{bar}")

    # Also show band-edge values
    mask = (freq >= BAND_MIN) & (freq <= BAND_MAX)
    if np.any(mask):
        f_band = freq[mask]
        a_band = absorptance[mask]
        lines.append("")
        lines.append(f"  Band mean absorptance: {np.mean(a_band):.4f}")
        lines.append(f"  Band min absorptance:  {np.min(a_band):.4f} "
                     f"at {f_band[np.argmin(a_band)]:.2f} THz "
                     f"({300.0/f_band[np.argmin(a_band)]:.1f} um)")
        lines.append(f"  Band max absorptance:  {np.max(a_band):.4f} "
                     f"at {f_band[np.argmax(a_band)]:.2f} THz "
                     f"({300.0/f_band[np.argmax(a_band)]:.1f} um)")

    return "\n".join(lines)


def build_system_prompt() -> str:
    """Build the static system prompt with broadband absorber physics."""
    return textwrap.dedent("""\
    You are an expert photonic metamaterial designer optimizing a 5x5 array of
    Complementary Wire Circle (CWC) resonators for broadband mid-infrared
    absorption on a Germanium (Ge) substrate.

    GOAL: Maximize mean absorptance over the 14-18 um wavelength band
    (16.667-21.429 THz in frequency).
    SCORE = 1 - mean(absorptance in band). Lower is better. Target: < 0.02.

    ================================================================
    PHYSICAL STRUCTURE (Metal-Insulator-Metal Perfect Absorber)
    ================================================================

    Layer stack (bottom to top, ALL FIXED — you CANNOT change these):
      1. Au ground plane:       thickness t_gp = 0.1 um (optically thick reflector)
      2. Ge dielectric spacer:  thickness t = 0.6 um (n_Ge ~ 4 in mid-IR)
      3. Au CWC resonator layer: thickness t_mm = 0.1 um (patterned metamaterial)
      4. Vacuum superstrate:     height Z = 10 um

    The full array is 5x5 unit cells = 20 um x 20 um with periodic boundary
    conditions (simulates infinite array). Each cell has fixed pitch a = 4.0 um.

    ================================================================
    CWC UNIT CELL GEOMETRY (what you optimize)
    ================================================================

    Each cell (i,j) contains a single Au CWC resonator made of TWO parts:

    (A) A RING (annulus) centered in the unit cell:
        - Outer radius:  r1 = a/2 - x = 2.0 - x   (um)
        - Inner radius:  r2 = r1 - w               (um)
        - The ring metal width is w.

    (B) FOUR CROSS ARMS forming a '+' pattern INSIDE the ring:
        - Each arm is a rectangular bar with width = w (same as ring width).
        - Each arm extends INWARD from the inner ring edge (at radius r2)
          toward the center, stopping at distance g/2 from the center.
        - Arm length = r2 - g/2.
        - The 4 arms are at 0 deg, 90 deg, 180 deg, 270 deg.
        - Ring + 4 arms are merged into a single Au solid.

    So the CWC looks like a ring with an internal cross/plus pattern.
    The central void has diameter g (where no metal exists).

    The 3 tunable parameters per cell (75 total for 25 cells):

      x_i_j : margin (um) — gap between cell edge and outer ring edge.
              Determines outer radius: r1 = 2.0 - x.
              SMALLER x -> LARGER r1 -> LOWER resonance frequency.
              LARGER x  -> SMALLER r1 -> HIGHER resonance frequency.

      w_i_j : width (um) — metal width of BOTH the ring and cross arms.
              Determines inner radius: r2 = r1 - w.
              Affects impedance matching to free space.
              Wider w -> better coupling to incident radiation.

      g_i_j : gap (um) — diameter of the central void.
              Controls cross-arm length: arm_length = r2 - g/2.
              SMALLER g -> LONGER arms -> more inductance -> lower freq, broader BW.
              LARGER g  -> SHORTER arms -> less inductance -> higher freq, narrower BW.
              CRITICAL: if g approaches 2*r2, arms vanish and the CWC degrades
              to a bare ring with much weaker, narrower resonance.

    ================================================================
    RESONANCE PHYSICS
    ================================================================

    This is a metal-insulator-metal (MIM) perfect absorber:
    - The Au ground plane reflects all transmitted light back through the Ge spacer.
    - The CWC pattern provides frequency-selective coupling to the cavity mode.
    - At resonance, the structure impedance-matches to free space -> near-unity absorption.
    - Off resonance, the structure is mostly reflective.

    Key physics of each parameter:
    - r1 (via x): PRIMARY control of resonance wavelength. The CWC effective
      electrical size scales as ~r1 * n_eff. With the high-index Ge spacer in
      the MIM cavity, the resonance wavelength is much LONGER than the physical
      circumference alone would suggest.
    - w: Controls the ring-to-arm capacitance and the coupling efficiency to
      incident radiation. Too narrow -> poor coupling, low absorption peak.
      Optimal w provides near-unity absorption at resonance.
    - g: Controls the cross-arm INDUCTANCE, which is the CWC's distinguishing
      feature vs a simple ring. The cross arms create a strong LC resonance.
      Without substantial arms (g too large), the CWC loses its broadband
      absorption capability and becomes a narrowband ring resonator.
      ENSURE arm_length = r2 - g/2 is substantial (ideally > 0.2 um).

    ================================================================
    OPTIMIZATION STRATEGY
    ================================================================

    The 25 cells should have DIVERSE resonance frequencies spanning the
    entire 14-18 um (16.667-21.429 THz) target band. Strategy:

    1. SPREAD r1 values: Distribute outer radii so resonances tile the band
       evenly. You want cells resonating at low, middle, and high frequencies
       within the band. Not all cells should have similar r1.

    2. ENSURE STRONG ARMS: Keep g well below 2*r2 for all cells.
       Arm length = r2 - g/2 should be > 0.15 um for effective coupling.
       Cells with tiny arm_length will have weak, narrowband response.

    3. OPTIMIZE w FOR MATCHING: Ring width w should provide good impedance
       matching. Typical good values are w ~ 0.15-0.40 um.

    4. USE SPECTRUM DATA: The absorption spectrum sampled across the target
       band is provided. Identify frequency ranges with LOW absorption and
       adjust cells to fill those gaps.

    5. CHANGE SIZE: If mean_abs is far below target, make LARGER changes
       (10-30%) to multiple cells. Only use small 1-5% tweaks when the
       design is already good (mean_abs > 0.80).

    CONSTRAINTS:
    - x_i_j  in [0.1, 1.8] um
    - w_i_j  in [0.05, 1.5] um
    - g_i_j  in [0.1, 3.5] um
    - r1 = 2.0 - x >= 0.15 um
    - r2 = r1 - w  >= 0.02 um
    - g < 2 * r2    (cross arm must have positive length)

    ================================================================
    OUTPUT FORMAT
    ================================================================

    Respond with valid JSON only, no markdown fences:
    {
      "changes": {"param_name": new_value, ...},
      "reasoning": "One paragraph explaining your physical reasoning."
    }
    """)


def build_user_message(
    design: dict,
    best_score: float,
    history: List[Dict[str, str]],
    last_result: Optional[Dict[str, str]] = None,
    agent_history: Optional[List[dict]] = None,
    best_candidate_id: Optional[str] = None,
) -> str:
    """Build the per-iteration user message with current state."""
    cell_table = _build_cell_table(design)

    # Spectrum summary from latest best candidate
    spectrum_str = "  (no spectrum data)"
    if best_candidate_id:
        spectrum_str = _read_spectrum_summary(best_candidate_id)

    # Format history table
    hist_lines = []
    recent = history[-HISTORY_WINDOW:] if len(history) > HISTORY_WINDOW else history
    for row in recent:
        cid = row.get("candidate_id", "?")
        score = row.get("score", "?")
        mean_abs = row.get("mean_abs", "?")
        min_abs = row.get("min_abs", "?")
        freq_min = row.get("freq_at_min_thz", "?")
        coverage = row.get("band_coverage_90", "?")
        note = row.get("note", "")[:60]
        status = row.get("status", "?")
        hist_lines.append(
            f"  #{cid}: score={score}, mean_abs={mean_abs}, "
            f"min_abs={min_abs}, freq@min={freq_min} THz, "
            f"cov90={coverage}, status={status}"
        )
    hist_str = "\n".join(hist_lines) if hist_lines else "  (no history yet)"

    # Current score breakdown
    if last_result:
        score_detail = (
            f"Score: {last_result.get('score', '?')} "
            f"(mean_abs={last_result.get('mean_abs', '?')}, "
            f"min_abs={last_result.get('min_abs', '?')}, "
            f"freq@min={last_result.get('freq_at_min_thz', '?')} THz, "
            f"band_cov90={last_result.get('band_coverage_90', '?')})"
        )
    else:
        score_detail = f"Best score so far: {best_score}"

    # Adaptive strategy guidance based on current performance
    mean_abs_val = 0.0
    try:
        if last_result:
            mean_abs_val = float(last_result.get("mean_abs", 0))
    except (ValueError, TypeError):
        pass

    if mean_abs_val < 0.30:
        strategy_hint = (
            "  CURRENT ABSORPTION IS VERY LOW (<30%). The design needs MAJOR changes.\n"
            "  - Consider large adjustments (20-50%) to multiple cells.\n"
            "  - Check arm_length: cells with arm_len < 0.10 have effectively no cross arms.\n"
            "  - Reduce g significantly on cells with tiny arm_length to restore cross arms.\n"
            "  - Spread r1 values more diversely across the range to cover the full band."
        )
    elif mean_abs_val < 0.70:
        strategy_hint = (
            "  ABSORPTION IS MODERATE (30-70%). Make medium adjustments (5-20%).\n"
            "  - Look at the spectrum: which frequency ranges are weak?\n"
            "  - Adjust cells to fill gaps in spectral coverage.\n"
            "  - Ensure all cells have healthy arm_length > 0.15."
        )
    else:
        strategy_hint = (
            "  ABSORPTION IS GOOD (>70%). Fine-tune with small changes (1-5%).\n"
            "  - Focus on the weakest absorption point (freq@min).\n"
            "  - Make surgical adjustments to a few cells."
        )

    # Summarize failed attempts
    failed_lines = ""
    if agent_history:
        reverts = [h for h in agent_history if h["action"] == "revert"]
        if reverts:
            failed_parts = []
            for h in reverts[-5:]:
                n_changes = len(h.get("changes", {}))
                chg_summary = ", ".join(
                    f"{k}={v:.3f}" for k, v in list(h.get("changes", {}).items())[:4]
                )
                failed_parts.append(
                    f"  - {n_changes} changes ({chg_summary}...) -> "
                    f"mean_abs={h.get('mean_abs', '?')}, "
                    f"score={h['score_after']:.4f} (WORSE, reverted)"
                )
            failed_lines = (
                "\n\n  FAILED ATTEMPTS (avoid similar changes):\n"
                + "\n".join(failed_parts)
            )

    return textwrap.dedent(f"""\
    ============================================================
    CURRENT BEST DESIGN (cells sorted by r1 descending)
    ============================================================
    {cell_table}

    ============================================================
    ABSORPTANCE SPECTRUM IN TARGET BAND (14-18 um)
    ============================================================
    {spectrum_str}

    ============================================================
    SCORE & HISTORY
    ============================================================
    {score_detail}

    Experiment history (most recent {HISTORY_WINDOW}):
    {hist_str}{failed_lines}

    ============================================================
    STRATEGY GUIDANCE
    ============================================================
    {strategy_hint}

    Based on the cell table, arm lengths, and absorption spectrum above,
    what parameter changes will improve broadband absorption over 14-18 um?
    You may change as many cells as needed. Respond with JSON only.
    """)


# ---------------------------------------------------------------------------
# ChatGPT API
# ---------------------------------------------------------------------------

def call_chatgpt(
    client: openai.OpenAI,
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Call ChatGPT and parse the JSON response."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Build API kwargs — reasoning models use different params
    is_reasoning = model.startswith(("gpt-5", "o1", "o3", "o4"))
    api_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if is_reasoning:
        api_kwargs["max_completion_tokens"] = 16384
        api_kwargs["reasoning_effort"] = "high"
    else:
        api_kwargs["max_tokens"] = 4096
        api_kwargs["temperature"] = 0.3

    for attempt in range(3):
        try:
            response = client.chat.completions.create(**api_kwargs)
            content = response.choices[0].message.content
            if content is None or content.strip() == "":
                raise ValueError("Empty response from reasoning model")
            parsed = json.loads(content)

            if "changes" not in parsed:
                parsed["changes"] = {}
            if "reasoning" not in parsed:
                parsed["reasoning"] = "(no reasoning provided)"

            for k, v in list(parsed["changes"].items()):
                parsed["changes"][k] = float(v)

            return parsed

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"  [WARN] Bad ChatGPT response (attempt {attempt+1}): {e}")
            messages.append({
                "role": "user",
                "content": "Your previous response was not valid JSON with "
                           "'changes' and 'reasoning' keys. Please try again.",
            })

        except openai.APIError as e:
            wait = 2 ** (attempt + 1)
            print(f"  [WARN] OpenAI API error (attempt {attempt+1}): {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)

    return {
        "changes": {},
        "reasoning": "API call failed after 3 attempts. Skipping.",
    }


# ---------------------------------------------------------------------------
# CST runner
# ---------------------------------------------------------------------------

def _kill_cst_processes():
    """Kill any lingering CST user-session processes to release project locks."""
    try:
        # Use PowerShell to find and kill user-session CST processes (SessionId != 0)
        ps_cmd = (
            "Get-Process | Where-Object { $_.Name -like 'CST*' -and $_.SessionId -ne 0 } "
            "| ForEach-Object { Stop-Process -Id $_.Id -Force }"
        )
        subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
        )
        time.sleep(3)  # give OS time to release file locks
    except Exception:
        pass


def run_cst(
    parent_id: str = "root",
    note: str = "",
) -> Dict[str, Any]:
    """Invoke runner.py as a subprocess and return the latest result row."""
    cmd = [
        sys.executable,
        "-u",  # unbuffered output
        str(RUNNER_PY),
        "--parent-id", parent_id,
        "--note", note[:100],
    ]

    print(f"  [CST] Running simulation...", end=" ", flush=True)
    t0 = time.time()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(HERE),
        timeout=8000,  # generous timeout for optical solver
    )

    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    # Kill lingering CST processes to ensure project lock is released
    _kill_cst_processes()

    if result.returncode != 0:
        stderr_tail = result.stderr.strip().split("\n")[-5:]
        for line in stderr_tail:
            print(f"  [CST stderr] {line}")

    rows = read_results_tsv()
    if rows:
        return rows[-1]
    else:
        return {"status": "error", "score": "999.0", "candidate_id": "0000"}


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_results(
    history: list,
    best_candidate_id: str,
) -> None:
    """Generate optimization progress plot."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    kept = [h for h in history if h["action"] == "keep"]
    discarded = [h for h in history if h["action"] == "revert"]
    n_total = len(history)
    n_kept = len(kept)

    def _safe_mean_abs(h):
        v = h.get("mean_abs", None)
        if v is None or v == "?":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    fig, ax = plt.subplots(figsize=(14, 7))

    # Target line at 1.0 (perfect absorption)
    ax.axhline(y=1.0, color="#e74c3c", linestyle="--", linewidth=1.5,
               alpha=0.5, zorder=1, label="Perfect (1.0)")

    # 0.98 target line
    ax.axhline(y=0.98, color="#f39c12", linestyle=":", linewidth=1.0,
               alpha=0.5, zorder=1, label="Target (0.98)")

    # Discarded points
    if discarded:
        disc_x = []
        disc_y = []
        for h in discarded:
            ma = _safe_mean_abs(h)
            if ma is not None:
                disc_x.append(h["iteration"])
                disc_y.append(ma)
        if disc_x:
            ax.scatter(disc_x, disc_y, color="#C0C0C0", s=40, zorder=2,
                       edgecolors="none", alpha=0.7)

    # Kept points
    if kept:
        kept_x = []
        kept_y = []
        for h in kept:
            ma = _safe_mean_abs(h)
            if ma is not None:
                kept_x.append(h["iteration"])
                kept_y.append(ma)
        if kept_x:
            ax.scatter(kept_x, kept_y, color="#2ecc71", s=80, zorder=4,
                       edgecolors="white", linewidths=0.8)

    # Running best line
    if kept:
        running_x = []
        running_y = []
        best_abs = 0.0

        for h in history:
            ma = _safe_mean_abs(h)
            if ma is None:
                continue
            if h["action"] == "keep" and ma > best_abs:
                best_abs = ma
            if best_abs > 0:
                running_x.append(h["iteration"])
                running_y.append(best_abs)

        if running_x:
            ax.step(running_x, running_y, where="post", color="#2ecc71",
                    linewidth=2.0, zorder=3, alpha=0.9)

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#C0C0C0",
               markersize=8, label="Discarded", linestyle="None"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ecc71",
               markersize=10, label="Kept", linestyle="None"),
        Line2D([0], [0], color="#2ecc71", linewidth=2, label="Running best"),
        Line2D([0], [0], color="#f39c12", linewidth=1, linestyle=":",
               label="Target (0.98)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=10,
              framealpha=0.9, edgecolor="#ddd")

    ax.set_xlabel("Experiment #", fontsize=12)
    ax.set_ylabel("Mean Absorptance (14-18 um)", fontsize=12)
    ax.set_title(
        f"Broadband Absorber Optimization: {n_total} Experiments, "
        f"{n_kept} Kept Improvements",
        fontsize=14, fontweight="bold",
    )
    ax.grid(True, alpha=0.15, linestyle="-")
    ax.set_axisbelow(True)

    if history:
        ax.set_xlim(-0.5, max(h["iteration"] for h in history) + 1)

    ax.set_ylim(0.7, 1.02)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    out_path = HERE / "optimization_report.png"
    plt.savefig(str(out_path), dpi=150, bbox_inches="tight")
    print(f"\n  Plot saved to: {out_path}")
    plt.close()


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Autonomous broadband absorber optimization agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS,
                        help=f"Maximum iterations (default {MAX_ITERATIONS})")
    parser.add_argument("--threshold", type=float, default=SCORE_THRESHOLD,
                        help=f"Score threshold to stop (default {SCORE_THRESHOLD})")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"OpenAI model (default {DEFAULT_MODEL})")
    parser.add_argument("--api-key", type=str, default=None,
                        help="OpenAI API key")
    parser.add_argument("--reset", action="store_true",
                        help="Reset design.py to baseline and clear results")
    args = parser.parse_args()

    # --- API key ---
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or DEFAULT_API_KEY
    client = openai.OpenAI(api_key=api_key)

    # --- Optional reset ---
    if args.reset:
        print("Resetting to baseline design...")
        write_design(BASELINE_DESIGN)
        if RESULTS_TSV.exists():
            RESULTS_TSV.unlink()
        print("  design.py and results.tsv reset.")

    print(f"\n{'='*60}")
    print(f"  Broadband Absorber Optimization Agent")
    print(f"  Band: 14-18 um (16.67-21.43 THz)")
    print(f"  Model: {args.model}")
    print(f"  Max iterations: {args.max_iter}")
    print(f"  Score threshold: {args.threshold}")
    print(f"{'='*60}\n")

    # --- Initialize state ---
    existing_rows = read_results_tsv()

    if not existing_rows:
        print("No existing results. Running baseline simulation...")
        write_design(BASELINE_DESIGN)
        baseline_result = run_cst(parent_id="root", note="baseline")
        existing_rows = read_results_tsv()
        print(f"  Baseline: score={baseline_result.get('score')}, "
              f"mean_abs={baseline_result.get('mean_abs')}\n")

    # Start from the best result so far
    best_score = float("inf")
    best_candidate_id = "root"
    best_design = read_design()

    for row in existing_rows:
        try:
            s = float(row["score"])
            if s < best_score and row.get("valid") == "true":
                best_score = s
                best_candidate_id = row["candidate_id"]
        except (ValueError, KeyError):
            pass

    print(f"  Starting from candidate {best_candidate_id}, score={best_score}")

    # --- Build system prompt (static) ---
    system_prompt = build_system_prompt()

    # --- Agent loop ---
    history = []
    no_improve_count = 0
    iteration = 0

    # Record baseline as experiment #0
    last_row = existing_rows[-1] if existing_rows else {}
    history.append({
        "iteration": 0,
        "changes": {},
        "design_before": {},
        "reasoning": "baseline",
        "score_before": best_score,
        "score_after": best_score,
        "mean_abs": last_row.get("mean_abs", "?"),
        "candidate_id": best_candidate_id,
        "note": "baseline",
        "action": "keep",
    })

    try:
        for iteration in range(1, args.max_iter + 1):
            print(f"\n{'-'*60}")
            print(f"  Iteration {iteration}/{args.max_iter}  |  "
                  f"Best score: {best_score:.6f}  |  "
                  f"No-improve streak: {no_improve_count}/{STAGNATION_LIMIT}")
            print(f"{'-'*60}")

            if best_score < args.threshold:
                print(f"\n  Score {best_score:.6f} < threshold {args.threshold}. "
                      f"Target achieved!")
                break

            if no_improve_count >= STAGNATION_LIMIT:
                print(f"\n  No improvement for {STAGNATION_LIMIT} consecutive "
                      f"iterations. Stopping.")
                break

            # --- Ask ChatGPT ---
            all_rows = read_results_tsv()
            last_result = all_rows[-1] if all_rows else None
            user_msg = build_user_message(
                best_design, best_score, all_rows, last_result,
                agent_history=history,
                best_candidate_id=best_candidate_id,
            )

            print("  [Agent] Thinking...", end=" ", flush=True)
            response = call_chatgpt(client, system_prompt, user_msg,
                                    model=args.model)
            print("done.")

            changes = response["changes"]
            reasoning = response["reasoning"]

            print(f"\n  [Agent] Reasoning:")
            for line in textwrap.wrap(reasoning, width=70):
                print(f"    {line}")

            if not changes:
                print("  [Agent] No changes proposed. Skipping.")
                no_improve_count += 1
                continue

            print(f"\n  [Agent] Proposed {len(changes)} change(s):")
            for param, new_val in changes.items():
                old_val = best_design.get(param, "?")
                print(f"    {param}: {old_val} -> {new_val}")

            # --- Apply changes ---
            proposed = copy.deepcopy(best_design)
            for param, new_val in changes.items():
                if param in proposed:
                    proposed[param] = new_val
                else:
                    print(f"  [WARN] Unknown parameter '{param}', ignoring.")

            # --- Pre-validate (up to 2 retries) ---
            sys.path.insert(0, str(HERE))
            from constraints import validate_design
            ok, reason = validate_design(proposed)
            retry_count = 0
            while not ok and retry_count < 2:
                retry_count += 1
                print(f"\n  [INVALID] {reason}")
                print(f"  Asking ChatGPT to fix (attempt {retry_count}/2)...")

                retry_msg = (
                    f"Your proposed changes {json.dumps(changes)} violate a "
                    f"constraint: {reason}.\n\n"
                    f"CONSTRAINTS:\n"
                    f"- x in [0.1, 1.8], w in [0.05, 1.5], g in [0.1, 3.5]\n"
                    f"- r1 = 2.0 - x > 0.15\n"
                    f"- r2 = r1 - w > 0.02\n"
                    f"- g < 2*r2 (cross arm positive length)\n\n"
                    f"Fix the proposal. Keep the same direction but adjust "
                    f"values to satisfy ALL constraints. JSON only."
                )
                response = call_chatgpt(client, system_prompt, retry_msg,
                                        model=args.model)
                changes = response["changes"]
                reasoning = response["reasoning"]

                if not changes:
                    break

                proposed = copy.deepcopy(best_design)
                for param, new_val in changes.items():
                    if param in proposed:
                        proposed[param] = new_val

                ok, reason = validate_design(proposed)

            if not ok:
                print(f"  [INVALID] Could not fix: {reason}. Skipping.")
                no_improve_count += 1
                continue

            if retry_count > 0:
                print(f"  [Agent] Revised changes: {len(changes)} params")

            # --- Write design and run CST ---
            write_design(proposed)

            change_summary = ", ".join(
                f"{k}: {best_design[k]:.4f}->{v:.4f}" for k, v in changes.items()
            )
            note = f"{change_summary[:80]} | {reasoning[:40]}"

            result = run_cst(parent_id=best_candidate_id, note=note)

            # --- Evaluate ---
            new_score = float(result.get("score", "999.0"))
            new_mean_abs = result.get("mean_abs", "?")
            new_min_abs = result.get("min_abs", "?")
            new_cid = result.get("candidate_id", "?")

            print(f"\n  [Result] score={new_score:.6f}, "
                  f"mean_abs={new_mean_abs}, min_abs={new_min_abs}")

            entry = {
                "iteration": iteration,
                "changes": changes,
                "design_before": copy.deepcopy(best_design),
                "reasoning": reasoning,
                "score_before": best_score,
                "score_after": new_score,
                "mean_abs": new_mean_abs,
                "candidate_id": new_cid,
                "note": change_summary[:60],
                "action": "",
            }

            valid = result.get("valid", "false") == "true"

            if valid and new_score < best_score:
                best_design = proposed
                best_score = new_score
                best_candidate_id = new_cid
                no_improve_count = 0
                entry["action"] = "keep"
                improvement = entry["score_before"] - new_score
                print(f"  [Decision] KEEP  (improved by {improvement:.6f})")
            else:
                write_design(best_design)
                no_improve_count += 1
                entry["action"] = "revert"
                print(f"  [Decision] REVERT  (score {new_score:.6f} >= "
                      f"best {best_score:.6f})")

            history.append(entry)

    except KeyboardInterrupt:
        print("\n\n  [INTERRUPTED] Generating report...")

    # --- Final report ---
    print(f"\n{'='*60}")
    print(f"  OPTIMIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Band: 14-18 um (16.67-21.43 THz)")
    print(f"  Best score:     {best_score:.6f}")
    print(f"  Best mean_abs:  {1.0 - best_score:.4f}")
    print(f"  Best candidate: {best_candidate_id}")
    print(f"  Total iterations: {iteration}")
    print()

    if history:
        plot_results(history, best_candidate_id)


if __name__ == "__main__":
    main()
