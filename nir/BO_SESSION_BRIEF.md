# auto_cst NIR — Bayesian Optimization session brief

**Goal of this session.** Implement a Bayesian Optimization (BO) variant of
the LLM-in-loop optimizer in [`nir/agent.py`](agent.py) and compare it
head-to-head on the same NIR perfect-absorber problem. Hypothesis A's
LLM run is the existing baseline to beat.

**Why BO is worth trying** (one sentence): CST simulations are expensive
(~80 s/run), the parameter space is continuous and 4–5 dimensional, the
score surface is mostly smooth within a single resonance mode — textbook
BO conditions, and the LLM's biggest failure mode (mode-hop confusion
across 4 wasted REVERTs in hypothesis A iters 2–5) is exactly what GP
posterior uncertainty handles for free.

---

## 1. The problem (cold-start summary)

Target: peak absorption at **1550 nm (193.41 THz, telecom C-band)** for an
NIR metamaterial absorber. Three independent geometries from a prior
literature-review stage, all sharing an Au / SiO₂ / Ag MIM stack:

| Hypothesis | Geometry | Tunable params | Status with LLM-in-loop |
|---|---|---|---|
| **A** | circular Ag disk on SiO₂ on Au, square lattice | `p, r, h, d` (+ fixed `t_ground`) | ✅ converged, score=0.61 in 8 iters (4 KEEPs) |
| **B** | rectangular Ag patch (`lx≠ly`) — polarization-sensitive | `p, lx, ly, h, d, t_ground` | ⚠ partial, score=13.0 in 10 iters (capped) |
| **C** | uniform planar Au/SiO₂/Ag stack, no patterning | `p, t_top, d, t_ground` | ❌ did not converge — see report |

**Score formula** (the BO objective; note: *minimize* this — or maximize `-score`):
```
score = |f_peak − 193.41 THz| + 0.2 × max(0, 0.90 − peak_abs)        # legacy
      = |f_peak − 193.41 THz| + 0.5 × (1 − peak_abs)²                # 'improved' formula, opt-in
```

Convergence threshold: `score < 0.5 THz` (= ~4 nm wavelength accuracy).

---

## 2. What's already built — REUSE THIS

The existing CST harness has a clean CLI interface that emits a parseable
JSON result line. **Do not modify the runner / evaluator / constraints —
just call `python -m nir.runner` as a subprocess from `bo_agent.py` and
parse the `RESULT_JSON:` line.**

```bash
python -m nir.runner \
    --hypothesis A \
    --target 193.41 \
    --iter-dir <run_dir>/iter_NN \
    --results-tsv <run_dir>/results_A.tsv \
    --candidate-id 0042 \
    --note "BO iter 5"

# Last line of stdout is:
#   RESULT_JSON: {"status": "ok", "valid": true, "candidate_id": "0042",
#                 "f_peak_thz": 192.80, "abs_at_peak": 0.9994, "fwhm_thz": 13.05,
#                 "score": 0.61, "score_formula": "legacy",
#                 "freq_error": 0.61, "abs_penalty": 0.0,
#                 "solve_duration_s": 74.5,
#                 "absorptance_csv": "...", "s11_csv": "..."}
```

Subprocess timeout: ~35 min (CST internal cap is 30 min). Wall time per
successful run: 70–150 s for hypothesis A/B at full mesh; ~50 s in
`--quick` mode (5 cells/λ vs 10).

### Files to reuse unmodified

- [`runner.py`](runner.py) — the subprocess. Already supports `--hypothesis A|B|C`, `--quick`, `--dry-run`.
- [`evaluator.py`](evaluator.py) — peak detection + score (`legacy` and `improved` formulas).
- [`constraints_A.py`](constraints_A.py) / `_B.py` / `_C.py` — `validate_design(d)` returns `(ok, reason)`. Also exposes `PARAM_BOUNDS: {param: (lo, hi)}` for BO bound spec.
- [`design_A.py`](design_A.py) / `_B.py` / `_C.py` — current design. `agent.py:read_design(cfg)` and `write_design(params, cfg)` parse / write these. (BO doesn't need to write `design_X.py`; it can pass params straight to the runner.)
- [`cst_helpers.py`](cst_helpers.py) — `cst.results` wrapper. Footgun-safe.

### Hypothesis-specific bounds (from the `_constraints_X.py` files)

```python
# Hypothesis A
PARAM_BOUNDS_A = {
    "p":        (700.0, 1500.0),     # nm
    "r":        (200.0, 725.0),      # max = (MAX_PERIOD - 50)/2
    "h":        (30.0,  200.0),
    "d":        (50.0,  400.0),
    "t_ground": (50.0,  200.0),      # FIXED at 100, do not optimize
}
# Constraint: 2*r + 50 <= p   (disk diameter must clear neighbors)

# Hypothesis B
PARAM_BOUNDS_B = {
    "p":  (700.0, 1700.0),
    "lx": (200.0, 1650.0),
    "ly": (200.0, 1650.0),
    "h":  (30.0,  200.0),
    "d":  (50.0,  400.0),
    "t_ground": (50.0, 200.0),       # FIXED at 100
}
# Constraints: lx <= p - 50  AND  ly <= p - 50

# Hypothesis C
PARAM_BOUNDS_C = {
    "p":     (200.0, 1000.0),        # FIXED at 500 (planar = uniform)
    "t_top": (3.0,   50.0),
    "d":     (80.0,  600.0),
    "t_ground": (50.0, 200.0),       # FIXED at 100
}
```

The `t_ground` (and `p` for C) parameters are **fixed**; optimize over the
others only.

---

## 3. Recommended BO scaffold

### Minimal sketch (BoTorch + EI)

Save as `nir/bo_agent.py`. ~150 lines:

```python
import json, subprocess, sys
from datetime import datetime
from pathlib import Path

import torch
from botorch.models import SingleTaskGP
from botorch.fit import fit_gpytorch_mll
from botorch.acquisition import qExpectedImprovement
from botorch.optim import optimize_acqf
from botorch.utils.sampling import draw_sobol_samples
from gpytorch.mlls import ExactMarginalLogLikelihood

from nir.constraints_A import validate_design, PARAM_BOUNDS

PARAM_ORDER = ["p", "r", "h", "d"]                    # fixed t_ground out of search
BOUNDS = torch.tensor([[PARAM_BOUNDS[k][0] for k in PARAM_ORDER],
                       [PARAM_BOUNDS[k][1] for k in PARAM_ORDER]],
                      dtype=torch.double)

def run_cst(params: dict, iter_dir: Path, results_tsv: Path,
            candidate_id: str) -> dict:
    """Subprocess into nir.runner; parse RESULT_JSON. Returns the result dict."""
    # Write params to a temp design file? OR pass via --design-json (requires runner change).
    # Simplest: write to nir/design_A.py before each call (matches LLM-agent pattern).
    write_design(params)
    cmd = [sys.executable, "-m", "nir.runner",
           "--hypothesis", "A", "--target", "193.41",
           "--iter-dir", str(iter_dir),
           "--results-tsv", str(results_tsv),
           "--candidate-id", candidate_id,
           "--note", f"BO {candidate_id}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2100)
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON: "):
            return json.loads(line[len("RESULT_JSON: "):])
    raise RuntimeError("runner produced no RESULT_JSON")


def make_objective(result: dict) -> float:
    """BoTorch maximizes; we want to minimize score, so return -score."""
    if not result.get("valid"):
        return -999.0
    return -float(result["score"])


def constraint_fn(x: torch.Tensor) -> torch.Tensor:
    """Returns True (1) if x satisfies disk-clearance constraint 2*r + 50 <= p."""
    p, r = x[..., 0], x[..., 1]
    return p - 2*r - 50.0     # >= 0 means feasible (BoTorch convention)


def sobol_init(n: int) -> torch.Tensor:
    """Draw n Sobol points within bounds, reject infeasible. Returns feasible n."""
    accepted = []
    while len(accepted) < n:
        batch = draw_sobol_samples(BOUNDS, n=2*n, q=1).squeeze(1)
        feasible = constraint_fn(batch) >= 0
        accepted.extend(batch[feasible].tolist())
    return torch.tensor(accepted[:n], dtype=torch.double)


def main():
    run_dir = Path(f"runs/{datetime.now():%Y-%m-%d_%H-%M-%S}/hypothesis_A_BO")
    run_dir.mkdir(parents=True, exist_ok=True)
    results_tsv = run_dir / "results_A.tsv"

    # --- Initial design: 5-8 Sobol points (slightly more than LLM's 1 baseline) ---
    X = sobol_init(n=8)
    Y = []
    for i, x in enumerate(X):
        params = dict(zip(PARAM_ORDER, x.tolist()))
        params["t_ground"] = 100.0          # fix
        result = run_cst(params, run_dir / f"iter_{i:02d}", results_tsv, f"{i+1:04d}")
        Y.append(make_objective(result))
    Y = torch.tensor(Y, dtype=torch.double).unsqueeze(-1)

    # --- BO loop ---
    for iteration in range(8, 25):           # cap at 25 total evals
        if Y.max().item() > -0.5:           # converged
            break

        gp = SingleTaskGP(X, Y)
        fit_gpytorch_mll(ExactMarginalLogLikelihood(gp.likelihood, gp))

        EI = qExpectedImprovement(gp, best_f=Y.max())
        candidates, _ = optimize_acqf(
            EI, bounds=BOUNDS, q=1, num_restarts=10, raw_samples=512,
            inequality_constraints=[(torch.tensor([0, 1]),  # indices: p, r
                                     torch.tensor([1.0, -2.0]),
                                     50.0)],                # p - 2*r >= 50
        )
        x_new = candidates.squeeze(0)
        params = dict(zip(PARAM_ORDER, x_new.tolist()))
        params["t_ground"] = 100.0
        result = run_cst(params, run_dir / f"iter_{iteration:02d}",
                         results_tsv, f"{iteration+1:04d}")
        y_new = torch.tensor([[make_objective(result)]], dtype=torch.double)
        X = torch.cat([X, x_new.unsqueeze(0)])
        Y = torch.cat([Y, y_new])

    print(f"Best score: {(-Y.max()).item():.4f} after {len(Y)} evals")
```

### Open design choices for the new session

1. **Initial design size.** 8 Sobol points = 8 × 80 s ≈ 11 min upfront. Could go down to 4 (fewer initial pts, but GP fit may be unstable early) or warm-start from LLM-proposed points.

2. **Acquisition function.**
   - `qExpectedImprovement` (EI) — safe default
   - `qUpperConfidenceBound` (UCB) — more exploration; better near mode boundaries
   - `qLogExpectedImprovement` — better numerical behavior at near-converged regimes

3. **Kernel.** BoTorch defaults to Matern-5/2 — fine for smooth resonances. For hypothesis B's multimodal patch landscape (m=1 vs m=2 modes), consider:
   - **Composite kernel**: separate length scales per parameter (BoTorch does this by default with ARD).
   - **Deep Kernel Learning (DKL)** — overkill but handles multimodality.
   - **Multi-task GP** — if you do hypotheses A/B/C jointly.

4. **Constraint handling.**
   - **Outcome constraint** (BoTorch's `inequality_constraints`): linear constraints on input variables — fine for `p − 2r ≥ 50`.
   - **Composite acquisition** (penalty on infeasibility): more robust if constraints are nonlinear.
   - **Trust-region BO (TURBO)**: very robust, handles constraints implicitly.

5. **Multi-fidelity.** The runner's `--quick` flag (5 cells/λ, ~50 s solve) is a natural low-fidelity oracle. BoTorch `SingleTaskMultiFidelityGP` could squeeze ~2-3× efficiency.

6. **Multi-objective BO** — instead of scalar score, optimize the 3-objective Pareto front of (`f_error`, `1 - peak_abs`, `|fwhm - target_fwhm|`) using `qNEHVI`. The LLM can't do this naturally; BoTorch does it in ~10 lines.

---

## 4. Comparison plan (hypothesis A is the apples-to-apples baseline)

The existing LLM run on hypothesis A is at:
[`runs/2026-05-07_02-10-06/hypothesis_A_disk/`](../runs/2026-05-07_02-10-06/hypothesis_A_disk/)

Key metrics to compare against:

| Metric | LLM-in-loop on A | BO target |
|---|---|---|
| Iterations to converge (score < 0.5) | 8 (didn't hit threshold; final 0.61) | aim for **≤ 6** |
| Iterations wasted on REVERTs | **4** | aim for 0 |
| Wall time | ~14 min | aim for ~10 min (8 evals × 80s) |
| Final score | 0.61 | aim for **≤ 0.3** |
| Final wavelength error | 5 nm | aim for ≤ 3 nm |
| Final peak absorption | 99.94 % | aim for ≥ 99 % |
| API cost | ~$0.05 in OpenAI tokens | $0 |

If BO converges in ≤ 5 iters or hits score ≤ 0.3, that's a clear win. If
it takes 10+ iters, examine why (probably needs more initial points or a
different kernel).

For hypotheses B and C the comparison is more about *robustness* than
speed — does BO handle the multimodal patch surface (B) and the
degenerate planar surface (C) better than the LLM did?

---

## 5. Variants worth implementing if time permits

### A. Hybrid: LLM warm-start + BO drive

Use the LLM (1 cheap API call) to propose 3 initial points based on
physics priors, then BO drives convergence. Predicted: best of both
worlds — physics-prior initial points + data-driven optimization.

```python
# In bo_agent.main(), replace the Sobol init:
llm_proposals = call_llm_for_initial_points(target=193.41, n=3)
X = torch.tensor([[d[k] for k in PARAM_ORDER] for d in llm_proposals],
                 dtype=torch.double)
# Then run all 3, then start BO loop
```

### B. Multi-fidelity BO

```python
from botorch.models.multi_fidelity import SingleTaskMultiFidelityGP
# Add a "fidelity" dimension to inputs: 0 = quick mode, 1 = full mode
# Acquisition: qMultiFidelityKnowledgeGradient
```

Cheapest fidelity is `--quick` (50 s, 5 cells/λ). Full is 80 s. Even if
the speedup is only 1.5×, it lets BO explore more cheaply early before
investing full-fidelity evaluations near the optimum.

### C. Multi-objective BO

```python
from botorch.acquisition.multi_objective import qNoisyExpectedHypervolumeImprovement
# Objectives: [-freq_error, peak_abs, -|fwhm - 25 THz|]
# Reference point: [-100, 0, -100]
```

Returns a Pareto front. Useful if the user wants to inspect tradeoffs
between peak position vs amplitude vs FWHM.

---

## 6. Things the new session should NOT change

- **The CST harness** ([`runner.py`](runner.py), [`cst_helpers.py`](cst_helpers.py),
  geometry/materials/evaluator) — interface is stable. Just subprocess into it.
- **The constraint definitions** in `constraints_X.py` — reuse them as-is.
- **The result artifact layout** under `runs/<timestamp>/hypothesis_X_*/` — keep
  one run dir per BO experiment so the artifacts mirror the LLM runs and the
  comparison is straightforward.

---

## 7. Reference: physics priors for warm-start (if doing the hybrid)

These are the same priors encoded in the LLM system prompts. Use them
to spec good initial points.

**Hypothesis A (disk MIM, target 1550 nm):**
- `r ≈ 580 nm`, `p ≈ 1300 nm`, `d ≈ 100 nm`, `h ≈ 100 nm` is the converged design.
- Sensitivity: `r` is the strongest lever (peak λ scales linearly with r).
- Constraint: `2r + 50 ≤ p`.

**Hypothesis B (rect-patch MIM):**
- Larger axis controls the dominant peak. Final design: `p=1400, lx=500, ly=1100, d=200`.
- Patch resonance: `λ ≈ 2 × n_eff × L` with n_eff ≈ 0.5–0.7 for thin MIM.
- Multimodal: m=1 mode at low f, m=2 mode at higher f. BO with Matern kernel
  may need more initial points than for hypothesis A.

**Hypothesis C (planar Au/SiO₂/Ag):**
- Quarter-wave resonance: `d ≈ λ/(4 n_SiO₂) = 1550/(4 × 1.45) ≈ 267 nm`.
- Top metal: 8–15 nm of Ag is typical for impedance matching.
- **Likely won't converge regardless of optimizer** under the constant-σ material
  model — reference [report §5](../runs/FINAL_REPORT.md). This is a
  material-model limitation, not an optimizer limitation. Proves the BO doesn't
  hide the underlying issue. Try [`probe_drude_vba.py`](probe_drude_vba.py)
  to discover dispersive Au/Ag VBA before re-attempting hypothesis C.

---

## 8. Recommended starting prompt for the new session

Copy this into the new session as the first message:

> Read [`nir/BO_SESSION_BRIEF.md`](nir/BO_SESSION_BRIEF.md) in this repo.
> Implement `nir/bo_agent.py` and `nir/run_hypothesis_A_bo.py` per the brief.
> Use BoTorch with EI acquisition. Run hypothesis A end-to-end. Compare
> iteration count, convergence wall-time, and final score against the existing
> LLM run at `runs/2026-05-07_02-10-06/hypothesis_A_disk/result.json`. Save
> the BO result under `runs/<timestamp>/hypothesis_A_BO/result.json` with the
> same schema (`hypothesis`, `best_design`, `best_score`, `n_iterations`,
> `n_kept`, `converged`, `history`).

The new session will need:
- Conda env `cst_inference` with BoTorch installed (`pip install botorch`)
- The CST install at `E:\cst\AMD64\python_cst_libraries`
- An OpenAI API key (only if implementing the hybrid warm-start variant)
