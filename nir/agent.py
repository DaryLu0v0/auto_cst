"""nir/agent.py -- LLM-in-loop optimizer for the NIR disk-MIM absorber.

Cloned + adapted from auto_cst/agent.py. Same control flow:
  read history -> ChatGPT -> validate -> run CST -> score -> keep/revert -> terminate

Differences from the original:
  - Reads/writes nir/design_A.py instead of design.py
  - Calls `python -m nir.runner ...` as the CST subprocess
  - System prompt has disk-MIM physics (not SRR THz)
  - Operates in NIR units: nm for geometry, THz for frequency
  - Results ledger and per-iteration outputs live under the caller-supplied
    run_dir (one timestamped session per run), not the package dir.

Usage:
    python -m nir.agent --target 193.41 --max-iter 15 --run-dir <path>
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
HERE = Path(__file__).resolve().parent          # D:/Claude/auto_cst/nir
PROJECT_ROOT = HERE.parent                      # D:/Claude/auto_cst

# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------
DEFAULT_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = "gpt-4o"

# Score threshold (THz of frequency error). At 193.41 THz target, 0.5 THz ~= 0.26 %.
# That corresponds to ~4 nm wavelength accuracy at 1550 nm.
SCORE_THRESHOLD = 0.5
MAX_ITERATIONS = 15
STAGNATION_LIMIT = 5
HISTORY_WINDOW = 12

CST_SUBPROCESS_TIMEOUT_S = 2100.0   # 35 min: 30 min CST internal cap + buffer


# ---------------------------------------------------------------------------
# Hypothesis dispatch
# ---------------------------------------------------------------------------

def _hypothesis_config(name: str):
    """Return per-hypothesis design metadata for the agent loop."""
    name = name.upper()
    if name == "A":
        return {
            "name": "A",
            "design_py": HERE / "design_A.py",
            "baseline": {"p": 993.59, "r": 457.05, "h": 105.98, "d": 112.61, "t_ground": 100.0},
            "param_order": ["p", "r", "h", "d", "t_ground"],
            "param_comments": {
                "p":        "Unit cell period (nm) -- square lattice",
                "r":        "Ag disk radius (nm) -- strongest lever on resonance position",
                "h":        "Ag disk thickness (nm) -- weak lever, mostly affects Q",
                "d":        "SiO2 spacer thickness (nm) -- secondary lever (cavity-disk coupling)",
                "t_ground": "Au ground thickness (nm) -- fixed; just needs to be opaque (>= 50 nm)",
            },
            "validate_module": "nir.constraints_A",
            "design_header": [
                "# nir/design_A.py -- the editable design for hypothesis A (metallic disk MIM).",
                "#",
                "# Each key maps 1:1 to a named CST parameter in the working project.",
                "# Units: all lengths in NANOMETERS (nm).",
            ],
        }
    elif name == "B":
        return {
            "name": "B",
            "design_py": HERE / "design_B.py",
            "baseline": {"p": 1300.0, "lx": 1100.0, "ly": 900.0, "h": 100.0, "d": 100.0, "t_ground": 100.0},
            "param_order": ["p", "lx", "ly", "h", "d", "t_ground"],
            "param_comments": {
                "p":        "Unit cell period (nm) -- square lattice",
                "lx":       "Patch full length along x (nm) -- LONG axis, tunes one polarization",
                "ly":       "Patch full length along y (nm) -- SHORT axis, tunes the other polarization",
                "h":        "Ag patch thickness (nm) -- weak lever",
                "d":        "SiO2 spacer thickness (nm) -- secondary lever",
                "t_ground": "Au ground thickness (nm) -- fixed",
            },
            "validate_module": "nir.constraints_B",
            "design_header": [
                "# nir/design_B.py -- editable design for hypothesis B (rectangular-patch MIM).",
                "#",
                "# Polarization-sensitive (lx != ly). Unit: NANOMETERS.",
            ],
        }
    elif name == "C":
        return {
            "name": "C",
            "design_py": HERE / "design_C.py",
            "baseline": {"p": 500.0, "t_top": 12.0, "d": 267.0, "t_ground": 100.0},
            "param_order": ["p", "t_top", "d", "t_ground"],
            "param_comments": {
                "p":        "Unit cell period (nm) -- arbitrary; planar structure is uniform",
                "t_top":    "Ag top layer thickness (nm) -- secondary lever (controls Q)",
                "d":        "SiO2 cavity thickness (nm) -- STRONGEST lever (Fabry-Perot peak)",
                "t_ground": "Au ground thickness (nm) -- fixed",
            },
            "validate_module": "nir.constraints_C",
            "design_header": [
                "# nir/design_C.py -- editable design for hypothesis C (planar Au/SiO2/Cr MIM).",
                "#",
                "# Lithography-free Fabry-Perot absorber, no lateral patterning.",
                "# Units: NANOMETERS.",
            ],
        }
    else:
        raise ValueError(f"Unknown hypothesis '{name}'")


# ---------------------------------------------------------------------------
# Design file I/O
# ---------------------------------------------------------------------------

def read_design(cfg: dict) -> dict:
    """Read DESIGN dict from the hypothesis's design_X.py (no import cache)."""
    text = cfg["design_py"].read_text(encoding="utf-8")
    match = re.search(r"DESIGN\s*=\s*(\{[^}]+\})", text, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find DESIGN dict in {cfg['design_py']}")
    return ast.literal_eval(match.group(1))


def write_design(params: dict, cfg: dict) -> None:
    lines = list(cfg["design_header"]) + ["", "DESIGN = {"]
    for key in cfg["param_order"]:
        val = params[key]
        if isinstance(val, float) and val.is_integer():
            val_str = f"{val:.1f}"
        else:
            val_str = f"{val}"
        lines.append(f"    # {cfg['param_comments'][key]}")
        lines.append(f'    "{key}": {val_str},')
        lines.append("")
    lines.append("}")
    lines.append("")
    cfg["design_py"].write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Results TSV I/O
# ---------------------------------------------------------------------------

def read_results_tsv(results_tsv: Path) -> List[Dict[str, str]]:
    if not results_tsv.exists():
        return []
    with open(results_tsv, "r") as f:
        return list(csv.DictReader(f, delimiter="\t"))


# ---------------------------------------------------------------------------
# ChatGPT prompts (NIR disk-MIM physics)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_A = """\
You are an expert nanophotonics engineer optimizing a NIR metamaterial
absorber to peak at {target_thz} THz ({target_nm:.0f} nm).

UNIT CELL (top to bottom):
  Ag disk (cylinder, radius r, thickness h)  ->  SiO2 spacer (thickness d)
  ->  Au ground plane (t_ground, opaque).
Square lattice, period p. Au ground blocks transmission, so
Absorptance = 1 - |S11|^2.

TUNABLE PARAMETERS (NANOMETERS):
- p          : unit cell period
- r          : Ag disk radius (STRONGEST lever for peak position)
- h          : Ag disk thickness (weak; mainly affects Q)
- d          : SiO2 spacer thickness (secondary; cavity-disk coupling)
- t_ground   : Au ground thickness (FIXED -- do NOT propose changes)

PHYSICS:
- Peak wavelength scales ~linearly with disk RADIUS r.
  Larger r -> longer wavelength = lower frequency. ~5 % r -> ~5 % wavelength.
- d (spacer): thinner -> stronger coupling -> redshift; thicker -> blueshift.
- p (period): keep > 800 nm to avoid 1st-order grating diffraction at 1550 nm.
  Larger p -> slight redshift + lower absorption strength.
- h (disk thickness): weak; mostly tweaks Q.

HARD CONSTRAINTS (violations waste a simulation):
- p in [700, 1500] nm
- r in [200, (p - 50) / 2] nm    <-- 2*r + 50 nm <= p (clearance)
- h in [30, 200] nm
- d in [50, 400] nm
- t_ground = 100 nm (do not change)

STRATEGY:
- Change 1-2 parameters at a time.
- 3-10 % steps when within 5 % of target; 10-20 % when far off.
- First tune r (peak position), then d, then p.
- If r near the bound, increase p first to make room.
"""

_SYSTEM_PROMPT_B = """\
You are an expert nanophotonics engineer optimizing a RECTANGULAR-PATCH NIR
metamaterial absorber to peak at {target_thz} THz ({target_nm:.0f} nm).

UNIT CELL (top to bottom):
  Ag rectangular patch (lx by ly, thickness h)  ->  SiO2 spacer (d)
  ->  Au ground plane (t_ground, opaque).
Square lattice with period p. The patch breaks 4-fold symmetry when
lx != ly, so the two polarizations resonate at DIFFERENT frequencies.
We optimize S11 from the Floquet Zmax(1) port (one polarization only).

TUNABLE PARAMETERS (NANOMETERS):
- p          : unit cell period
- lx         : patch length along x (one polarization peak)
- ly         : patch length along y (the other polarization peak)
- h          : Ag patch thickness (weak)
- d          : SiO2 spacer thickness (secondary)
- t_ground   : Au ground thickness (FIXED)

PHYSICS:
- Each patch dimension controls a separate plasmonic resonance. The peak
  in measured S11 is dominated by whichever axis aligns with the incident
  E-field. As a rule of thumb, peak wavelength ~= 2 * n_eff * lx (or ly)
  where n_eff is the effective index of the disk-cavity mode (~1.7 for
  Ag/SiO2/Au at NIR). So a 1550 nm peak needs the relevant axis ~ 450 nm.
- Increase the relevant axis to redshift; decrease to blueshift.
- d (spacer): thinner -> stronger coupling -> redshift; thicker -> blueshift.
- p (period): keep > 800 nm to avoid grating diffraction at 1550 nm.
- h (thickness): weak; mostly tweaks Q.

HARD CONSTRAINTS:
- p in [700, 1700] nm
- lx, ly in [200, p - 50] nm     <-- patch must clear neighbors
- h in [30, 200] nm
- d in [50, 400] nm
- t_ground = 100 nm (do not change)

STRATEGY:
- First, learn which axis the dominant peak responds to: change lx alone
  by ~10 % and observe direction. Then converge using that axis.
- Optionally adjust the OTHER axis to introduce / tune polarization split.
- 3-10 % steps when close, 10-20 % when far.
"""

_SYSTEM_PROMPT_C = """\
You are an expert nanophotonics engineer optimizing a PLANAR NIR
Fabry-Perot absorber to peak at {target_thz} THz ({target_nm:.0f} nm).

STACK (top to bottom):
  Thin Ag semi-transparent layer (t_top)  ->  SiO2 cavity (d)
  ->  Au ground (t_ground, opaque).
NO lateral patterning; the structure is a uniform thin-film stack.
Polarization-insensitive at normal incidence.

TUNABLE PARAMETERS (NANOMETERS):
- p          : unit cell period (irrelevant; structure is uniform). Leave as is.
- t_top      : Ag layer thickness (secondary lever; controls Q / amplitude).
- d          : SiO2 cavity thickness (STRONGEST lever for peak position).
- t_ground   : Au ground thickness (FIXED).

PHYSICS:
- Quarter-wave resonance: peak wavelength = 4 * n_SiO2 * d, with n_SiO2 ~= 1.45.
  So d ~= lambda / (4 * 1.45) = 1550/5.8 ~= 267 nm gives 1550 nm peak.
  (CST's effective index may differ slightly; tune d empirically.)
- Larger d -> longer wavelength (lower frequency). Roughly linear.
- t_top (thin Ag) controls Q-factor and absorption peak amplitude:
  too thin (< 5 nm) -> weak interaction, low absorption;
  too thick (> 30 nm) -> highly reflective, peak disappears.
  Optimal is typically 8-15 nm for Ag at NIR.
- p is irrelevant (planar structure). Do not change.

HARD CONSTRAINTS:
- t_top in [3, 50] nm
- d in [80, 600] nm
- p, t_ground -- do not change.

STRATEGY:
- d is the dominant knob. Adjust ratiometrically: if peak at f_now and target
  is f_target, scale d by f_now / f_target (linear approx).
- If amplitude < 0.9, tune t_top (try 8, 12, 16 nm; pick the best).
"""

_SYSTEM_PROMPT_TEMPLATES = {"A": _SYSTEM_PROMPT_A, "B": _SYSTEM_PROMPT_B, "C": _SYSTEM_PROMPT_C}


def build_system_prompt(target_thz: float, hypothesis: str) -> str:
    target_nm = 1e3 * 299.792458 / target_thz
    body = _SYSTEM_PROMPT_TEMPLATES[hypothesis.upper()].format(
        target_thz=target_thz, target_nm=target_nm,
    )
    common_tail = textwrap.dedent(f"""\

    SCORE = |f_peak - {target_thz}| + 0.2 * max(0, 0.90 - peak_absorptance)
    Lower is better. Goal: drive score below {SCORE_THRESHOLD}.

    OUTPUT: valid JSON only, no markdown fences:
    {{
      "changes": {{"param_name": new_value, ...}},
      "reasoning": "One paragraph explaining why these changes should move the peak toward {target_thz} THz."
    }}
    Only include parameters that you actually want to change.
    All values must be numeric (not strings).
    """)
    return body + common_tail


def _detect_mode_hop(agent_history: Optional[List[dict]],
                     freq_jump_thz: float = 30.0,
                     max_param_change_pct: float = 10.0) -> Optional[str]:
    """If the most recent iteration's peak frequency jumped by more than
    `freq_jump_thz` while the largest parameter change was under
    `max_param_change_pct` of its previous value, return a warning string.
    Otherwise return None.

    Mode-hops typically indicate that the peak detection is now tracking
    a different resonance mode (higher-order, lattice mode, etc.) than the
    previous iter -- so the LLM should NOT extrapolate the previous trend.
    """
    if not agent_history or len(agent_history) < 2:
        return None
    last = agent_history[-1]
    prev_kept = None
    for h in reversed(agent_history[:-1]):
        if h.get("action") == "keep":
            prev_kept = h
            break
    if prev_kept is None:
        return None

    try:
        f_now = float(last.get("f_peak", "nan"))
        f_prev = float(prev_kept.get("f_peak", "nan"))
    except (ValueError, TypeError):
        return None
    if not (f_now == f_now and f_prev == f_prev):  # NaN check
        return None

    df = abs(f_now - f_prev)
    if df < freq_jump_thz:
        return None

    # Find max relative parameter change in the latest 'changes' dict
    changes = last.get("changes", {}) or {}
    design_before = last.get("design_before", {}) or {}
    max_pct = 0.0
    for k, v_new in changes.items():
        try:
            v_old = float(design_before.get(k, 0.0))
            v_new = float(v_new)
        except (ValueError, TypeError):
            continue
        if v_old == 0:
            continue
        pct = 100.0 * abs(v_new - v_old) / abs(v_old)
        if pct > max_pct:
            max_pct = pct

    if max_pct > max_param_change_pct:
        return None

    return (
        f"WARNING: peak frequency jumped {df:.1f} THz "
        f"({f_prev:.1f} -> {f_now:.1f} THz) on a parameter change of only "
        f"~{max_pct:.1f} %. This usually means the detector is now tracking "
        f"a DIFFERENT resonance mode (higher-order, lattice-coupled, edge-of-window). "
        f"Do NOT extrapolate the previous trend; consider stepping BACK toward "
        f"the previous parameter values and trying a smaller perturbation in a "
        f"different direction."
    )


def build_user_message(design: dict,
                       best_score: float,
                       target_thz: float,
                       history: List[Dict[str, str]],
                       last_result: Optional[Dict[str, str]] = None,
                       agent_history: Optional[List[dict]] = None) -> str:
    params_str = json.dumps(design, indent=2)

    hist_lines = []
    recent = history[-HISTORY_WINDOW:] if len(history) > HISTORY_WINDOW else history
    for row in recent:
        cid = row.get("candidate_id", "?")
        score = row.get("score", "?")
        f_peak = row.get("f_peak_thz", "?")
        abs_at_peak = row.get("abs_at_peak", "?")
        note = (row.get("note", "") or "")[:60]
        status = row.get("status", "?")
        hist_lines.append(
            f"  #{cid}: score={score}, f_peak={f_peak} THz, "
            f"abs={abs_at_peak}, status={status}, note={note}"
        )
    hist_str = "\n".join(hist_lines) if hist_lines else "  (no history yet)"

    if last_result:
        score_detail = (
            f"Score: {last_result.get('score', '?')} "
            f"(freq_error={last_result.get('freq_error', '?')} THz, "
            f"abs_penalty={last_result.get('abs_penalty', '?')}, "
            f"f_peak={last_result.get('f_peak_thz', '?')} THz, "
            f"abs_at_peak={last_result.get('abs_at_peak', '?')})"
        )
    else:
        score_detail = f"Best score so far: {best_score}"

    failed_block = ""
    if agent_history:
        reverts = [h for h in agent_history if h.get("action") == "revert"]
        if reverts:
            parts = []
            for h in reverts[-5:]:
                parts.append(
                    f"  - Changes {h['changes']} -> f_peak={h.get('f_peak', '?')} THz, "
                    f"score={h.get('score_after', '?'):.4f} (WORSE, reverted)"
                )
            failed_block = (
                "\n\n  FAILED ATTEMPTS (do not repeat these directions):\n"
                + "\n".join(parts)
            )

    mode_hop_warning = _detect_mode_hop(agent_history)
    mode_hop_block = f"\n\n  {mode_hop_warning}" if mode_hop_warning else ""

    return textwrap.dedent(f"""\
    Target: {target_thz} THz.
    Current best design (nm):
    {params_str}

    {score_detail}

    Experiment history (most recent {HISTORY_WINDOW}):
    {hist_str}{failed_block}{mode_hop_block}

    Based on the history and physics, what parameter(s) should change next
    to lower the score? Score = |f_peak - {target_thz}| + 0.2 * max(0, 0.90 - peak_abs).

    Respond with JSON only.
    """)


# ---------------------------------------------------------------------------
# OpenAI call
# ---------------------------------------------------------------------------

def call_chatgpt(client: openai.OpenAI,
                 system_prompt: str,
                 user_message: str,
                 model: str = DEFAULT_MODEL) -> dict:
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
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            if "changes" not in parsed:
                parsed["changes"] = {}
            if "reasoning" not in parsed:
                parsed["reasoning"] = "(no reasoning)"
            for k, v in list(parsed["changes"].items()):
                parsed["changes"][k] = float(v)
            return parsed
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  [WARN] Bad ChatGPT response (attempt {attempt + 1}): {e}")
            messages.append({
                "role": "user",
                "content": "Your previous response was not valid JSON with "
                           "'changes' and 'reasoning' keys. Try again.",
            })
        except openai.APIError as e:
            wait = 2 ** (attempt + 1)
            print(f"  [WARN] OpenAI API error (attempt {attempt + 1}): {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
    return {"changes": {}, "reasoning": "API failed after 3 attempts. Skipping."}


# ---------------------------------------------------------------------------
# CST runner subprocess
# ---------------------------------------------------------------------------

def run_cst(target_thz: float,
            iter_dir: Path,
            results_tsv: Path,
            candidate_id: str,
            hypothesis: str,
            parent_id: str = "root",
            note: str = "") -> Dict[str, Any]:
    """Invoke `python -m nir.runner ...` as a subprocess, parse RESULT_JSON."""
    cmd = [
        sys.executable, "-m", "nir.runner",
        "--hypothesis", hypothesis,
        "--target", str(target_thz),
        "--iter-dir", str(iter_dir),
        "--results-tsv", str(results_tsv),
        "--candidate-id", candidate_id,
        "--parent-id", parent_id,
        "--note", note[:180],
    ]
    print(f"  [CST] subprocess: candidate {candidate_id}, iter_dir={iter_dir.name}")
    t0 = time.time()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        timeout=CST_SUBPROCESS_TIMEOUT_S,
    )
    elapsed = time.time() - t0
    print(f"  [CST] done ({elapsed:.1f}s, returncode={proc.returncode})")

    if proc.returncode != 0:
        for line in proc.stderr.strip().splitlines()[-8:]:
            print(f"  [CST stderr] {line}")

    # Try to parse RESULT_JSON line from stdout
    result_json = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON: "):
            try:
                result_json = json.loads(line[len("RESULT_JSON: "):])
            except json.JSONDecodeError:
                pass

    if result_json is not None:
        return result_json

    # Fallback: read the latest row from the TSV
    rows = read_results_tsv(results_tsv)
    if rows:
        return dict(rows[-1])
    return {"status": "error", "valid": "false", "score": "999.0",
            "candidate_id": candidate_id}


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _cleanup_iter_dirs(run_dir: Path,
                       results_tsv: Path,
                       *, keep_best: int = 0,
                       keep_recent: int = 0) -> int:
    """Trim per-iteration CST artifacts to save disk.

    keep_best=0 and keep_recent=0 (the defaults) means KEEP EVERYTHING -- safe
    backward-compatible behavior, matches the user's earlier preference.

    Iteration dirs not in the keep set have their working_*.cst project files
    AND their working_* result folders deleted. CSV spectra and
    iteration_record.json are always preserved (they are the small files that
    matter for plotting / re-analysis).

    Returns the number of iter dirs trimmed.
    """
    if keep_best <= 0 and keep_recent <= 0:
        return 0

    rows = []
    if results_tsv.exists():
        with open(results_tsv, "r") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))

    # Map candidate_id -> score (lowest = best); missing/invalid -> +inf
    cid_score: Dict[str, float] = {}
    cid_order: List[str] = []
    for row in rows:
        cid = row.get("candidate_id", "")
        cid_order.append(cid)
        try:
            s = float(row.get("score", "999"))
        except ValueError:
            s = 999.0
        valid = (row.get("valid", "false").lower() == "true")
        cid_score[cid] = s if valid else 999.0

    best_cids = sorted(cid_score, key=lambda c: cid_score[c])[:max(0, keep_best)]
    recent_cids = cid_order[-max(0, keep_recent):] if keep_recent > 0 else []
    keep_set = set(best_cids) | set(recent_cids)

    iter_dirs = sorted(run_dir.glob("iteration_*"))
    trimmed = 0
    for d in iter_dirs:
        rec = d / "iteration_record.json"
        if not rec.exists():
            continue
        try:
            with open(rec) as f:
                cid = json.load(f).get("candidate_id", "")
        except Exception:
            continue
        if cid in keep_set:
            continue
        # Delete the .cst file and its companion folder; keep CSVs and record
        for cst_file in d.glob("working_*.cst"):
            try:
                cst_file.unlink()
            except Exception:
                pass
        for sub in d.iterdir():
            if sub.is_dir() and sub.name.startswith("working_"):
                import shutil
                shutil.rmtree(sub, ignore_errors=True)
        trimmed += 1
    return trimmed


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-in-loop NIR optimizer (A/B/C)")
    parser.add_argument("--hypothesis", type=str, default="A", choices=["A", "B", "C"],
                        help="Which hypothesis to optimize")
    parser.add_argument("--target", type=float, default=193.41,
                        help="Target peak frequency in THz (default 193.41 = 1550 nm)")
    parser.add_argument("--max-iter", type=int, default=MAX_ITERATIONS,
                        help=f"Maximum iterations (default {MAX_ITERATIONS})")
    parser.add_argument("--threshold", type=float, default=SCORE_THRESHOLD,
                        help=f"Score threshold to stop (default {SCORE_THRESHOLD})")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"OpenAI model (default {DEFAULT_MODEL})")
    parser.add_argument("--api-key", type=str, default=None,
                        help="OpenAI API key (overrides env / CLAUDE.md memory)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset design_<hypothesis>.py to baseline before starting")
    parser.add_argument("--run-dir", type=str, required=True,
                        help="Output directory for this run")
    parser.add_argument("--keep-best", type=int, default=0,
                        help="At end of run, delete CST projects for all but "
                             "the top-N best iters (0 = keep all). CSVs preserved.")
    parser.add_argument("--keep-recent", type=int, default=0,
                        help="At end of run, also keep the N most-recent iters "
                             "regardless of score (0 = keep all).")
    args = parser.parse_args()

    cfg = _hypothesis_config(args.hypothesis)
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    results_tsv = run_dir / f"results_{cfg['name']}.tsv"
    iteration_log_path = run_dir / "iteration_log.json"

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY") or DEFAULT_API_KEY
    client = openai.OpenAI(api_key=api_key)

    if args.reset:
        print(f"Resetting {cfg['design_py'].name} to baseline...")
        write_design(cfg["baseline"], cfg)
        if results_tsv.exists():
            results_tsv.unlink()

    target = args.target
    target_nm = 1e3 * 299.792458 / target
    print(f"\n{'='*60}")
    print(f"  NIR optimization agent  --  hypothesis {cfg['name']}")
    print(f"  Target: {target} THz ({target_nm:.1f} nm)")
    print(f"  Model: {args.model}")
    print(f"  Max iterations: {args.max_iter}")
    print(f"  Score threshold: {args.threshold} THz")
    print(f"  Run dir: {run_dir}")
    print(f"{'='*60}\n")

    # --- Baseline ---
    existing = read_results_tsv(results_tsv)
    if not existing:
        print("No existing results. Running baseline simulation...")
        baseline_iter_dir = run_dir / "iteration_00"
        baseline_iter_dir.mkdir(parents=True, exist_ok=True)
        baseline_result = run_cst(
            target_thz=target,
            iter_dir=baseline_iter_dir,
            results_tsv=results_tsv,
            candidate_id="0001",
            hypothesis=cfg["name"],
            parent_id="root",
            note="baseline",
        )
        existing = read_results_tsv(results_tsv)
        print(f"  Baseline: score={baseline_result.get('score')}, "
              f"f_peak={baseline_result.get('f_peak_thz')} THz\n")

    best_score = float("inf")
    best_candidate_id = "root"
    best_design = read_design(cfg)
    for row in existing:
        try:
            s = float(row["score"])
            if s < best_score and row.get("valid") == "true":
                best_score = s
                best_candidate_id = row["candidate_id"]
        except (ValueError, KeyError):
            pass

    print(f"  Starting best: candidate={best_candidate_id}, score={best_score}")
    print(f"  Design: {json.dumps(best_design, indent=2)}\n")

    system_prompt = build_system_prompt(target, cfg["name"])

    history: List[dict] = []
    no_improve = 0
    iteration = 0

    history.append({
        "iteration": 0,
        "changes": {},
        "design_before": {},
        "reasoning": "baseline",
        "score_before": best_score,
        "score_after": best_score,
        "f_peak": existing[-1].get("f_peak_thz", "?") if existing else "?",
        "candidate_id": best_candidate_id,
        "note": "baseline",
        "action": "keep",
    })

    try:
        for iteration in range(1, args.max_iter + 1):
            print(f"\n{'─'*60}")
            print(f"  Iteration {iteration}/{args.max_iter}  |  "
                  f"Best score: {best_score:.6f}  |  "
                  f"No-improve: {no_improve}/{STAGNATION_LIMIT}")
            print(f"{'─'*60}")

            if best_score < args.threshold:
                print(f"\n  Score {best_score:.6f} < threshold {args.threshold}. Done!")
                break
            if no_improve >= STAGNATION_LIMIT:
                print(f"\n  No improvement for {STAGNATION_LIMIT} iters. Stopping.")
                break

            all_rows = read_results_tsv(results_tsv)
            last_result = all_rows[-1] if all_rows else None
            user_msg = build_user_message(
                best_design, best_score, target, all_rows, last_result,
                agent_history=history,
            )
            print("  [Agent] Thinking...", end=" ", flush=True)
            response = call_chatgpt(client, system_prompt, user_msg, model=args.model)
            print("done.")

            changes = response["changes"]
            reasoning = response["reasoning"]

            print("\n  [Agent] Reasoning:")
            for line in textwrap.wrap(reasoning, width=70):
                print(f"    {line}")

            if not changes:
                print("  [Agent] No changes proposed. Skipping.")
                no_improve += 1
                continue

            print("\n  [Agent] Proposed changes:")
            for k, v in changes.items():
                print(f"    {k}: {best_design.get(k, '?')} -> {v}")

            proposed = copy.deepcopy(best_design)
            for k, v in changes.items():
                if k in proposed:
                    proposed[k] = v
                else:
                    print(f"  [WARN] Unknown parameter '{k}', ignoring.")

            # --- Validate (up to 2 retries) ---
            import importlib
            validate_design = importlib.import_module(cfg["validate_module"]).validate_design
            ok, reason = validate_design(proposed)
            retry = 0
            while not ok and retry < 2:
                retry += 1
                print(f"\n  [INVALID] {reason}")
                print(f"  Asking ChatGPT to fix (attempt {retry}/2)...")
                retry_msg = (
                    f"Your proposed changes {json.dumps(changes)} violate a "
                    f"constraint: {reason}.\n\n"
                    f"Current best design: {json.dumps(best_design, indent=2)}\n"
                    f"Target: {target} THz.\n\n"
                    f"Refer to the hard constraints in the system prompt; the "
                    f"violated rule is shown above. Fix the proposal in the same "
                    f"intended direction. Respond with JSON only."
                )
                response = call_chatgpt(client, system_prompt, retry_msg, model=args.model)
                changes = response["changes"]
                reasoning = response["reasoning"]
                if not changes:
                    break
                proposed = copy.deepcopy(best_design)
                for k, v in changes.items():
                    if k in proposed:
                        proposed[k] = v
                ok, reason = validate_design(proposed)

            if not ok:
                print(f"  [INVALID] Could not fix: {reason}. Skipping.")
                no_improve += 1
                continue

            if retry > 0:
                print(f"  [Agent] Revised changes: {changes}")

            # --- Write design and run CST ---
            write_design(proposed, cfg)
            change_summary = ", ".join(
                f"{k}: {best_design[k]}->{v}" for k, v in changes.items()
            )
            note = f"{change_summary} | {reasoning[:60]}"

            iter_dir = run_dir / f"iteration_{iteration:02d}"
            new_cid = f"{iteration + 1:04d}"
            result = run_cst(target, iter_dir, results_tsv, new_cid,
                             hypothesis=cfg["name"],
                             parent_id=best_candidate_id, note=note)

            try:
                new_score = float(result.get("score", "999.0"))
            except (ValueError, TypeError):
                new_score = 999.0
            new_f_peak = result.get("f_peak_thz", "?")
            new_abs = result.get("abs_at_peak", "?")
            new_status = result.get("status", "?")
            new_cid_actual = result.get("candidate_id", new_cid)

            print(f"\n  [Result] score={new_score:.6f}, f_peak={new_f_peak} THz, "
                  f"abs={new_abs}")

            entry = {
                "iteration": iteration,
                "changes": changes,
                "design_before": copy.deepcopy(best_design),
                "reasoning": reasoning,
                "score_before": best_score,
                "score_after": new_score,
                "f_peak": new_f_peak,
                "candidate_id": new_cid_actual,
                "note": change_summary,
                "action": "",
            }

            valid = (str(result.get("valid", "false")).lower() in ("true", "1"))
            if valid and new_score < best_score:
                best_design = proposed
                best_score = new_score
                best_candidate_id = new_cid_actual
                no_improve = 0
                entry["action"] = "keep"
                improvement = entry["score_before"] - new_score
                print(f"  [Decision] KEEP  (improved by {improvement:.6f})")
            else:
                write_design(best_design, cfg)   # revert design_X.py to best
                no_improve += 1
                entry["action"] = "revert"
                print(f"  [Decision] REVERT  (score {new_score:.6f} >= "
                      f"best {best_score:.6f})")

            history.append(entry)

            # Persist iteration log every iter (resilient to crashes)
            with open(iteration_log_path, "w") as f:
                json.dump({
                    "target_thz": target,
                    "model": args.model,
                    "history": history,
                    "best": {
                        "candidate_id": best_candidate_id,
                        "score": best_score,
                        "design": best_design,
                    },
                }, f, indent=2, default=str)

    except KeyboardInterrupt:
        print("\n\n  [INTERRUPTED] Saving partial state...")

    # --- Final report ---
    print(f"\n{'='*60}")
    print(f"  OPTIMIZATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Target: {target} THz")
    print(f"  Best score: {best_score:.6f}")
    print(f"  Best candidate: {best_candidate_id}")
    print(f"  Iterations: {iteration}")
    print(f"  Final design (nm):")
    for k in cfg["param_order"]:
        baseline = cfg["baseline"][k]
        cur = best_design[k]
        delta = cur - baseline
        sign = "+" if delta >= 0 else ""
        print(f"    {k:>10s}: {cur:>10.3f}  (baseline={baseline}, {sign}{delta:.2f})")
    print()

    # Write final result.json
    result_json = run_dir / "result.json"
    final_payload: Dict[str, Any] = {
        "hypothesis": cfg["name"],
        "target_thz": target,
        "target_nm": 1e3 * 299.792458 / target,
        "best_design": best_design,
        "baseline_design": cfg["baseline"],
        "best_score": best_score,
        "best_candidate_id": best_candidate_id,
        "n_iterations": iteration,
        "n_kept": sum(1 for h in history if h["action"] == "keep"),
        "converged": best_score < args.threshold,
        "history": history,
    }
    # Try to attach the final spectrum path
    try:
        all_rows = read_results_tsv(results_tsv)
        for row in reversed(all_rows):
            if row.get("candidate_id") == best_candidate_id:
                # Find the iter_dir for this candidate by scanning subdirs
                for sub in sorted(run_dir.glob("iteration_*")):
                    rec = sub / "iteration_record.json"
                    if rec.exists():
                        with open(rec) as f:
                            r = json.load(f)
                        if r.get("candidate_id") == best_candidate_id:
                            final_payload["final_iter_dir"] = str(sub)
                            final_payload["final_absorptance_csv"] = str(sub / "Absorptance.csv")
                            break
                break
    except Exception:
        pass

    with open(result_json, "w") as f:
        json.dump(final_payload, f, indent=2, default=str)
    print(f"  Result summary -> {result_json}")
    print(f"  Iteration log  -> {iteration_log_path}")

    # Optional: trim CST projects to save disk
    if args.keep_best > 0 or args.keep_recent > 0:
        trimmed = _cleanup_iter_dirs(
            run_dir, results_tsv,
            keep_best=args.keep_best, keep_recent=args.keep_recent,
        )
        print(f"  Trimmed {trimmed} iteration dirs (kept best={args.keep_best}, recent={args.keep_recent}).")
    print()


if __name__ == "__main__":
    main()
