"""agent.py -- Autonomous CST SRR optimization agent.

Uses OpenAI ChatGPT as the reasoning engine to drive an autoresearch-style
keep/revert loop over CST metamaterial simulations.

Usage:
    python agent.py                        # interactive: asks for target freq
    python agent.py --target 0.7           # non-interactive
    python agent.py --max-iter 20          # limit iterations
    python agent.py --model gpt-4o-mini    # use cheaper model
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
DEFAULT_MODEL = "gpt-4o"
SCORE_THRESHOLD = 0.005
MAX_ITERATIONS = 30
STAGNATION_LIMIT = 7
HISTORY_WINDOW = 15  # how many past results to send to ChatGPT

# Design parameter metadata
PARAM_ORDER = ["p", "outer_srr", "w", "gap", "t_m", "st", "length_arm"]
PARAM_COMMENTS = {
    "p":          "Unit cell period (um)",
    "outer_srr":  "Outer SRR square dimension (um)",
    "w":          "Metal trace width (um)",
    "gap":        "Split gap width (um) -- capacitive gap",
    "t_m":        "Metal (Gold) thickness (um)",
    "st":         "Substrate (Silicon) thickness (um)",
    "length_arm": "Coupling arm length (um)",
}

# Baseline design (original values from the template)
BASELINE_DESIGN = {
    "p": 50.0,
    "outer_srr": 45.0,
    "w": 2.0,
    "gap": 0.6,
    "t_m": 0.1,
    "st": 30.0,
    "length_arm": 25.0,
}


# ---------------------------------------------------------------------------
# Design file I/O
# ---------------------------------------------------------------------------

def read_design() -> dict:
    """Read current DESIGN dict from design.py without importing it."""
    text = DESIGN_PY.read_text(encoding="utf-8")
    match = re.search(r"DESIGN\s*=\s*(\{[^}]+\})", text, re.DOTALL)
    if not match:
        raise ValueError("Could not find DESIGN dict in design.py")
    return ast.literal_eval(match.group(1))


def write_design(params: dict) -> None:
    """Overwrite design.py with updated parameter values."""
    lines = [
        "# design.py -- the ONLY file the agent is allowed to edit",
        "# This is the CST equivalent of train.py in autoresearch.",
        "#",
        "# Each key maps 1:1 to a named CST parameter in the template project.",
        "# Units: all lengths in micrometers (um), matching CST project units.",
        "",
        "DESIGN = {",
    ]
    for key in PARAM_ORDER:
        val = params[key]
        # Format: integers as .0, small floats with enough precision
        if val == int(val) and val >= 1:
            val_str = f"{val:.1f}"
        else:
            val_str = f"{val}"
        lines.append(f"    # {PARAM_COMMENTS[key]}")
        lines.append(f'    "{key}": {val_str},')
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

def build_system_prompt(target_freq: float) -> str:
    """Build the static system prompt with physics knowledge."""
    return textwrap.dedent(f"""\
    You are an expert electromagnetic metamaterial designer optimizing a
    Split-Ring Resonator (SRR) unit cell to achieve a target THz resonance.

    TARGET: {target_freq} THz resonance (reflectance peak).

    TUNABLE PARAMETERS (all in micrometers):
    - p          : unit cell period (affects inter-cell coupling)
    - outer_srr  : outer SRR square size (STRONGEST lever for frequency)
    - w          : metal trace width (inductance / ohmic loss)
    - gap        : split gap width (capacitance -- smaller = lower freq)
    - t_m        : gold thickness (loss, minor freq effect)
    - st         : silicon substrate thickness (effective permittivity)
    - length_arm : coupling arm length (adds inductance)

    PHYSICS -- to LOWER resonance frequency:
    - Increase outer_srr (longer path = lower freq, strongest lever)
    - Increase length_arm (more inductance)
    - Decrease gap (more capacitance)
    - Increase st (higher effective permittivity)

    PHYSICS -- to RAISE resonance frequency:
    - Decrease outer_srr
    - Decrease length_arm
    - Increase gap
    - Decrease st

    PHYSICS -- to IMPROVE absorption/reflectance magnitude:
    - Increase w (wider traces, lower ohmic loss)
    - Fine-tune gap (LC coupling strength)
    - Tune st (impedance matching to free space)

    HARD CONSTRAINTS (violations waste a simulation):
    - gap >= 0.4 um
    - w >= 1.0 um
    - outer_srr < p
    - outer_srr > 2 * w
    - t_m in [0.05, 1.0] um
    - st in [5.0, 100.0] um
    - p in [10.0, 300.0] um
    - length_arm >= 2.0 um AND length_arm < outer_srr

    CRITICAL COUPLING: outer_srr MUST be < p. If you need a larger SRR to
    lower the frequency, you MUST ALSO increase p to make room. For example,
    if you want outer_srr=60, set p >= 62 (keep ~2 um margin). Increasing p
    alone does NOT significantly change frequency -- outer_srr is the driver.

    STRATEGY:
    - Prefer changing 1-2 parameters at a time to isolate effects.
    - Use small steps (5-15%) unless far from target (>0.1 THz away).
    - When far from target, take LARGE steps -- increase outer_srr AND p together.
    - Use linear interpolation from past results when possible.
    - If outer_srr is near p, increase p first to make room, then increase outer_srr.
    - If outer_srr is already well-tuned, try secondary levers (gap, st, length_arm).
    - Never propose values that violate the hard constraints.
    - ALWAYS check: outer_srr < p, length_arm < outer_srr before proposing.

    OUTPUT FORMAT: You MUST respond with valid JSON only, no markdown fences:
    {{
      "changes": {{"param_name": new_value, ...}},
      "reasoning": "One paragraph explaining WHY these changes should move the resonance toward {target_freq} THz and/or improve absorption."
    }}
    """)


def build_user_message(
    design: dict,
    best_score: float,
    target_freq: float,
    history: List[Dict[str, str]],
    last_result: Optional[Dict[str, str]] = None,
    agent_history: Optional[List[dict]] = None,
) -> str:
    """Build the per-iteration user message with current state."""
    params_str = json.dumps(design, indent=2)

    # Format history table
    hist_lines = []
    recent = history[-HISTORY_WINDOW:] if len(history) > HISTORY_WINDOW else history
    for row in recent:
        cid = row.get("candidate_id", "?")
        score = row.get("score", "?")
        f_res = row.get("f_res_thz", "?")
        absorb = row.get("abs_at_res", "?")
        note = row.get("note", "")[:60]
        status = row.get("status", "?")
        hist_lines.append(
            f"  #{cid}: score={score}, f_res={f_res} THz, "
            f"refl={absorb}, status={status}, note={note}"
        )
    hist_str = "\n".join(hist_lines) if hist_lines else "  (no history yet)"

    # Current score breakdown
    if last_result:
        score_detail = (
            f"Score: {last_result.get('score', '?')} "
            f"(freq_error={last_result.get('freq_error', '?')}, "
            f"abs_penalty={last_result.get('abs_penalty', '?')}, "
            f"f_res={last_result.get('f_res_thz', '?')} THz, "
            f"reflectance={last_result.get('abs_at_res', '?')})"
        )
    else:
        score_detail = f"Best score so far: {best_score}"

    # Summarize failed attempts so ChatGPT can learn from them
    failed_lines = ""
    if agent_history:
        reverts = [h for h in agent_history if h["action"] == "revert"]
        if reverts:
            failed_parts = []
            for h in reverts[-5:]:
                failed_parts.append(
                    f"  - Changes {h['changes']} -> f_res={h['f_res']} THz, "
                    f"score={h['score_after']:.4f} (WORSE, reverted)"
                )
            failed_lines = (
                "\n\n  FAILED ATTEMPTS (DO NOT repeat these -- try different approach):\n"
                + "\n".join(failed_parts)
            )

    return textwrap.dedent(f"""\
    Target frequency: {target_freq} THz
    Current best design parameters:
    {params_str}

    {score_detail}

    Experiment history (most recent {HISTORY_WINDOW}):
    {hist_str}{failed_lines}

    Based on the history and physics, what parameter(s) should be changed
    next to minimize the score? Remember: score = |f_res - {target_freq}| + 0.2 * max(0, 0.90 - reflectance).

    IMPORTANT: If previous attempts with larger outer_srr/p made the score WORSE
    (frequency jumped UP), do NOT keep increasing them. Instead try:
    - Smaller increments from the best design
    - Secondary levers: decrease gap, increase st, increase length_arm
    - Combinations of secondary levers

    Respond with JSON only.
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
    """Call ChatGPT and parse the JSON response.

    Returns dict with 'changes' and 'reasoning' keys.
    Retries up to 3 times on API errors.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)

            # Validate expected keys
            if "changes" not in parsed:
                parsed["changes"] = {}
            if "reasoning" not in parsed:
                parsed["reasoning"] = "(no reasoning provided)"

            # Ensure all values in changes are numeric
            for k, v in list(parsed["changes"].items()):
                parsed["changes"][k] = float(v)

            return parsed

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  [WARN] Bad ChatGPT response (attempt {attempt+1}): {e}")
            # Add a retry hint to the message
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

    # All retries exhausted -- return a no-op
    return {
        "changes": {},
        "reasoning": "API call failed after 3 attempts. Skipping this iteration.",
    }


# ---------------------------------------------------------------------------
# CST runner
# ---------------------------------------------------------------------------

def run_cst(
    target: float,
    parent_id: str = "root",
    note: str = "",
) -> Dict[str, Any]:
    """Invoke runner.py as a subprocess and return the latest result row."""
    cmd = [
        sys.executable,
        str(RUNNER_PY),
        "--target", str(target),
        "--parent-id", parent_id,
        "--note", note[:100],  # truncate long notes
    ]

    print(f"  [CST] Running simulation...", end=" ", flush=True)
    t0 = time.time()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(HERE),
        timeout=600,  # 10 min safety timeout
    )

    elapsed = time.time() - t0
    print(f"done ({elapsed:.1f}s)")

    if result.returncode != 0:
        # Print stderr for debugging
        stderr_tail = result.stderr.strip().split("\n")[-5:]
        for line in stderr_tail:
            print(f"  [CST stderr] {line}")

    # Read the latest row from results.tsv (authoritative source)
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
    target_freq: float,
    best_candidate_id: str,
) -> None:
    """Generate autoresearch-style optimization progress plot.

    Matches the visual style of karpathy/autoresearch:
    - Gray dots for discarded experiments
    - Green dots for kept improvements with annotation labels
    - Green step-line for running best score
    - Title: "CST AutoResearch Progress: N Experiments, M Kept Improvements"
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.lines import Line2D

    # --- Collect data ---
    kept = [h for h in history if h["action"] == "keep"]
    discarded = [h for h in history if h["action"] == "revert"]
    n_total = len(history)
    n_kept = len(kept)

    def _safe_freq(h):
        """Extract numeric f_res from history entry, return None if invalid."""
        v = h.get("f_res", None)
        if v is None or v == "?":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    fig, ax = plt.subplots(figsize=(14, 7))

    # --- Target frequency line (red dashed) ---
    ax.axhline(
        y=target_freq, color="#e74c3c", linestyle="--", linewidth=1.5,
        alpha=0.7, zorder=1, label=f"Target ({target_freq} THz)",
    )

    # --- Discarded points (gray, small) ---
    if discarded:
        disc_x = []
        disc_y = []
        for h in discarded:
            f = _safe_freq(h)
            if f is not None:
                disc_x.append(h["iteration"])
                disc_y.append(f)
        if disc_x:
            ax.scatter(disc_x, disc_y, color="#C0C0C0", s=40, zorder=2,
                       edgecolors="none", alpha=0.7)

    # --- Kept points (green, larger) ---
    if kept:
        kept_x = []
        kept_y = []
        for h in kept:
            f = _safe_freq(h)
            if f is not None:
                kept_x.append(h["iteration"])
                kept_y.append(f)
        if kept_x:
            ax.scatter(kept_x, kept_y, color="#2ecc71", s=80, zorder=4,
                       edgecolors="white", linewidths=0.8)

    # --- Running best line (green step line) ---
    # "Best" = frequency closest to target
    if kept:
        running_x = []
        running_y = []
        best_freq_so_far = None
        best_dist = float("inf")

        for h in history:
            f = _safe_freq(h)
            if f is None:
                continue
            if h["action"] == "keep":
                dist = abs(f - target_freq)
                if dist < best_dist:
                    best_dist = dist
                    best_freq_so_far = f
            if best_freq_so_far is not None:
                running_x.append(h["iteration"])
                running_y.append(best_freq_so_far)

        if running_x:
            ax.step(running_x, running_y, where="post", color="#2ecc71",
                    linewidth=2.0, zorder=3, alpha=0.9)

    # --- Annotate kept experiments with short labels ---
    if kept:
        for h in kept:
            f = _safe_freq(h)
            if f is None:
                continue
            # Build a short label from the changes dict
            changes = h.get("changes", {})
            if changes:
                parts = []
                for k, v in changes.items():
                    old = h.get("design_before", {}).get(k)
                    if old is not None:
                        old_s = f"{old:g}"
                        new_s = f"{v:g}" if isinstance(v, (int, float)) else str(v)
                        parts.append(f"{k} {old_s}\u2192{new_s}")
                    else:
                        parts.append(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}")
                label = ", ".join(parts)
            else:
                label = h.get("note", "")[:40]

            # Truncate if too long
            if len(label) > 55:
                label = label[:52] + "..."

            ax.annotate(
                label,
                xy=(h["iteration"], f),
                xytext=(6, 8),
                textcoords="offset points",
                fontsize=6.5,
                color="#27ae60",
                alpha=0.85,
                rotation=18,
                ha="left",
                va="bottom",
                fontweight="normal",
            )

    # --- Legend (matching autoresearch style) ---
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#C0C0C0",
               markersize=8, label="Discarded", linestyle="None"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2ecc71",
               markersize=10, label="Kept", linestyle="None"),
        Line2D([0], [0], color="#2ecc71", linewidth=2, label="Running best"),
        Line2D([0], [0], color="#e74c3c", linewidth=1.5, linestyle="--",
               label=f"Target ({target_freq} THz)"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=10,
              framealpha=0.9, edgecolor="#ddd")

    # --- Axis styling ---
    ax.set_xlabel("Experiment #", fontsize=12)
    ax.set_ylabel("Resonance Frequency (THz)", fontsize=12)
    ax.set_title(
        f"CST AutoResearch Progress: {n_total} Experiments, "
        f"{n_kept} Kept Improvements",
        fontsize=14, fontweight="bold",
    )
    ax.grid(True, alpha=0.15, linestyle="-")
    ax.set_axisbelow(True)

    # Set x-axis to start from 0
    if history:
        ax.set_xlim(-0.5, max(h["iteration"] for h in history) + 1)

    # Y-axis: auto-range from all frequencies, include target
    all_freqs = [f for f in (_safe_freq(h) for h in history) if f is not None]
    all_freqs.append(target_freq)
    y_min = min(all_freqs)
    y_max = max(all_freqs)
    y_margin = (y_max - y_min) * 0.10
    ax.set_ylim(y_min - y_margin, y_max + y_margin)

    # Clean up spines
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
        description="Autonomous CST SRR optimization agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", type=float, default=None,
                        help="Target resonance frequency in THz")
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

    # --- Target frequency ---
    target = args.target
    if target is None:
        target = float(input("Enter target resonance frequency (THz): "))

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
    print(f"  CST AutoResearch Agent")
    print(f"  Target: {target} THz")
    print(f"  Model: {args.model}")
    print(f"  Max iterations: {args.max_iter}")
    print(f"  Score threshold: {args.threshold}")
    print(f"{'='*60}\n")

    # --- Initialize state ---
    existing_rows = read_results_tsv()

    if not existing_rows:
        # Run baseline first
        print("No existing results. Running baseline simulation...")
        write_design(BASELINE_DESIGN)
        baseline_result = run_cst(target, parent_id="root", note="baseline")
        existing_rows = read_results_tsv()
        print(f"  Baseline: score={baseline_result.get('score')}, "
              f"f_res={baseline_result.get('f_res_thz')} THz\n")

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

    # If we found a best, load its design from the row note isn't enough;
    # use current design.py as the best (it was left at the best state)
    print(f"  Starting from candidate {best_candidate_id}, score={best_score}")
    print(f"  Current design: {json.dumps(best_design, indent=2)}\n")

    # --- Build system prompt (static) ---
    system_prompt = build_system_prompt(target)

    # --- Agent loop ---
    history = []
    no_improve_count = 0
    iteration = 0

    # Record baseline as experiment #0 so it appears on the plot
    history.append({
        "iteration": 0,
        "changes": {},
        "design_before": {},
        "reasoning": "baseline",
        "score_before": best_score,
        "score_after": best_score,
        "f_res": existing_rows[-1].get("f_res_thz", "?") if existing_rows else "?",
        "candidate_id": best_candidate_id,
        "note": "baseline",
        "action": "keep",
    })

    try:
        for iteration in range(1, args.max_iter + 1):
            print(f"\n{'─'*60}")
            print(f"  Iteration {iteration}/{args.max_iter}  |  "
                  f"Best score: {best_score:.6f}  |  "
                  f"No-improve streak: {no_improve_count}/{STAGNATION_LIMIT}")
            print(f"{'─'*60}")

            # Check termination
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
                best_design, best_score, target, all_rows, last_result,
                agent_history=history,
            )

            print("  [Agent] Thinking...", end=" ", flush=True)
            response = call_chatgpt(client, system_prompt, user_msg,
                                    model=args.model)
            print("done.")

            changes = response["changes"]
            reasoning = response["reasoning"]

            # Display reasoning
            print(f"\n  [Agent] Reasoning:")
            for line in textwrap.wrap(reasoning, width=70):
                print(f"    {line}")

            if not changes:
                print("  [Agent] No changes proposed. Skipping.")
                no_improve_count += 1
                continue

            # Display proposed changes
            print(f"\n  [Agent] Proposed changes:")
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

                # Full-context retry: include the original user message +
                # constraint error so agent doesn't lose track of the goal
                retry_msg = (
                    f"Your proposed changes {json.dumps(changes)} violate a "
                    f"constraint: {reason}.\n\n"
                    f"Current best design: {json.dumps(best_design, indent=2)}\n"
                    f"Target: {target} THz, current best f_res from history.\n\n"
                    f"KEY RULES:\n"
                    f"- outer_srr MUST be < p. If you need outer_srr=X, set p >= X+2.\n"
                    f"- length_arm MUST be < outer_srr.\n"
                    f"- gap >= 0.4, w >= 1.0, outer_srr > 2*w.\n\n"
                    f"Fix the proposal. Keep the same direction (toward {target} THz) "
                    f"but adjust values to satisfy ALL constraints. "
                    f"Respond with JSON only."
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
                print(f"  [INVALID] Could not fix: {reason}. Skipping iteration.")
                no_improve_count += 1
                continue

            if retry_count > 0:
                print(f"  [Agent] Revised changes: {changes}")
                print(f"  [Agent] Revised reasoning: {reasoning[:100]}...")

            # --- Write design and run CST ---
            write_design(proposed)

            # Build a short note for the log
            change_summary = ", ".join(
                f"{k}: {best_design[k]}->{v}" for k, v in changes.items()
            )
            note = f"{change_summary} | {reasoning[:60]}"

            result = run_cst(target, parent_id=best_candidate_id, note=note)

            # --- Evaluate ---
            new_score = float(result.get("score", "999.0"))
            new_f_res = result.get("f_res_thz", "?")
            new_refl = result.get("abs_at_res", "?")
            new_status = result.get("status", "?")
            new_cid = result.get("candidate_id", "?")

            print(f"\n  [Result] score={new_score:.6f}, f_res={new_f_res} THz, "
                  f"reflectance={new_refl}")

            entry = {
                "iteration": iteration,
                "changes": changes,
                "design_before": copy.deepcopy(best_design),
                "reasoning": reasoning,
                "score_before": best_score,
                "score_after": new_score,
                "f_res": new_f_res,
                "candidate_id": new_cid,
                "note": change_summary,
                "action": "",
            }

            valid = result.get("valid", "false") == "true"

            if valid and new_score < best_score:
                # KEEP
                best_design = proposed
                best_score = new_score
                best_candidate_id = new_cid
                no_improve_count = 0
                entry["action"] = "keep"
                improvement = entry["score_before"] - new_score
                print(f"  [Decision] KEEP  (improved by {improvement:.6f})")
            else:
                # REVERT
                write_design(best_design)
                no_improve_count += 1
                entry["action"] = "revert"
                print(f"  [Decision] REVERT  (score {new_score:.6f} >= "
                      f"best {best_score:.6f})")

            history.append(entry)

    except KeyboardInterrupt:
        print("\n\n  [INTERRUPTED] Generating report with current results...")

    # --- Final report ---
    print(f"\n{'='*60}")
    print(f"  OPTIMIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Target frequency: {target} THz")
    print(f"  Best score:       {best_score:.6f}")
    print(f"  Best candidate:   {best_candidate_id}")
    print(f"  Total iterations: {iteration}")
    print(f"  Final design:")
    for param in PARAM_ORDER:
        baseline = BASELINE_DESIGN[param]
        current = best_design[param]
        delta = current - baseline
        sign = "+" if delta >= 0 else ""
        print(f"    {param:>12s}: {current:>8.2f} um  "
              f"(baseline={baseline}, {sign}{delta:.2f})")
    print()

    # --- Generate plot ---
    if history:
        plot_results(history, target, best_candidate_id)


if __name__ == "__main__":
    main()
