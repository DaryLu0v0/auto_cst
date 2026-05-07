# CST AutoResearch

> Autonomous metamaterial design optimization — inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch)

Treat a CST Studio Suite simulation like `train.py`: an LLM agent iteratively modifies geometric parameters, runs full-wave EM simulations, evaluates results, and keeps or reverts changes to hit a target resonance frequency.

**Two pipelines in this repo:**

| Pipeline | Band | Typical target | Geometry | Status |
|---|---|---|---|---|
| Project root (`agent.py`, `runner.py`, …) | THz / microwave | 0.3–1.0 THz | gold split-ring resonator on silicon | reference design |
| [`nir/`](nir/) subpackage | NIR / optical | 1550 nm (193.41 THz, telecom C-band) | metallic-disk MIM (Au / SiO₂ / Ag); two more variants | **see [NIR section below](#nir-1550-nm-perfect-absorbers)** |

![Optimization Progress](optimization_report.png)

## How It Works

```
┌─────────────┐     ┌───────────┐     ┌──────────┐     ┌───────────┐
│  agent.py   │────▶│ design.py │────▶│ runner.py│────▶│ CST Suite │
│  (ChatGPT)  │◀────│ (params)  │     │ (harness) │     │ (solver)  │
└──────┬──────┘     └───────────┘     └─────┬────┘     └───────────┘
       │                                     │
       │  keep / revert                      ▼
       │                              ┌────────────┐
       └──────────────────────────────│evaluator.py│
                                      └────────────┘
```

1. **Agent reads** the current design, constraint rules, physics hints, and experiment history
2. **ChatGPT proposes** a parameter change with reasoning (JSON response)
3. **Constraints are validated** before any simulation runs
4. **Runner injects** parameters into CST via COM/VBA, runs the FD solver, exports S-parameters
5. **Evaluator scores** the result: `score = |f_res - target| + 0.2 * max(0, 0.90 - reflectance)`
6. **Agent decides** keep (score improved) or revert (score worsened)
7. **Repeat** until the score threshold is met or stagnation is detected

All experiments are logged to `results.tsv` — a permanent, append-only ledger.

## Quick Start

### Prerequisites

- **CST Studio Suite** (tested with 2024) installed with COM interface
- **Python 3.10+** with conda
- **OpenAI API key**

### Setup

```bash
conda activate cst_inference
pip install openai matplotlib numpy

# CST Python libraries (adjust path to your CST install)
set PYTHONPATH=E:\cst\AMD64\python_cst_libraries
```

### Run

```bash
# Target 0.7 THz (default), reset to baseline first
python agent.py --target 0.7 --reset

# Target 0.4 THz, allow up to 20 iterations
python agent.py --target 0.4 --reset --max-iter 20

# Resume from where you left off (no reset)
python agent.py --target 0.5

# Custom API key
python agent.py --target 0.6 --api-key sk-...
```

The agent will print reasoning for each iteration, keep/revert decisions, and generate `optimization_report.png` when done.

## NIR (1550 nm) perfect absorbers

The [`nir/`](nir/) subpackage extends the same agent / runner / evaluator pattern to the **near-infrared / telecom C-band** (target 1550 nm, 193.41 THz). It bypasses the THz-specific `runner.py` and `constraints.py` (which would reject 1 µm-scale periods) and provides an LLM-driven loop that consumes the canonical handoff from a separate stage-1 literature-review agent (`hypothesis.json`).

**Designed end-to-end by the agent:** three independent absorbers from the top-3 hypotheses returned by lit-review. Final results, all on the same Au / SiO₂ / Ag MIM stack:

| Hypothesis | Geometry | Peak | Wavelength error | Peak absorption |
|---|---|---|---|---|
| **A — disk MIM** | circular Ag disk on SiO₂ on Au, square lattice | **1554.94 nm** | **5 nm (0.32 %)** | **99.94 %** |
| B — rectangular-patch MIM | Ag rectangle (lx ≠ ly) on the same MIM stack — polarization-sensitive | 1662 nm | 112 nm | 79.0 % |
| C — planar Au/SiO₂/Ag stack | thin-film Fabry-Perot, no lateral patterning | did not converge — see report | n/a | <5 % |

Hypothesis A is the deliverable design. Full report, methodology, per-iteration trace, and the comparison plot are in [`runs/FINAL_REPORT.md`](runs/FINAL_REPORT.md) and [`runs/FINAL_REPORT_spectra.png`](runs/FINAL_REPORT_spectra.png).

### Quick start (NIR)

```bash
conda activate cst_inference
cd D:/Claude/auto_cst
export OPENAI_API_KEY=sk-...

# 1. Validate (no CST -- catches import + constraint bugs in <1 s)
python -m nir.runner --hypothesis A --dry-run

# 2. Smoke-test geometry + VBA + solver pipeline (~50 s, coarser mesh)
python -m nir.runner --hypothesis A --quick

# 3. Full LLM-in-loop optimization (15 iters, ~15 min)
python -m nir.run_hypothesis_A --reset --max-iter 15

# Same flow for hypothesis B and C
python -m nir.run_hypothesis_B --reset --max-iter 10
python -m nir.run_hypothesis_C --reset --max-iter 8
```

Outputs go to `runs/<timestamp>/hypothesis_X_<shape>/`:
- `result.json` — final design + score + match metrics
- `results_X.tsv` — append-only per-candidate ledger
- `iteration_log.json` — full ChatGPT reasoning per iter
- `iteration_NN/Absorptance.csv` — final spectrum per iteration

### NIR-specific tools

- [`nir/runner.py`](nir/runner.py) — hypothesis-dispatched CST harness (`--hypothesis A|B|C`). Each hypothesis selects design module, constraints, geometry-VBA-builder, materials function, and solver/mesh combo. `--quick` flag runs a coarser-mesh smoke test in ~50 s.
- [`nir/agent.py`](nir/agent.py) — LLM-in-loop optimizer with hypothesis-aware system prompts, mode-hop detection (auto-warns the LLM when peak jumps >30 THz on <10 % param change), and optional `--keep-best`/`--keep-recent` iteration retention.
- [`nir/cst_helpers.py`](nir/cst_helpers.py) — wraps two `cst.results` silent footguns (relative-path index corruption + run_id=0 default after parameter injection) and the solver-dependent S-parameter naming gotcha.
- [`nir/VBA_COOKBOOK.md`](nir/VBA_COOKBOOK.md) — every tested working CST VBA snippet from this project plus the failed ones (with their actual `(10091)` errors), the **solver-mesh decision rule** (TD+PBA for patterned, FD+Tet for planar), and a pre-flight checklist.
- [`nir/probe_drude_vba.py`](nir/probe_drude_vba.py) — auto-tries 9 candidate Drude / library-load VBA syntaxes to discover the right inline-dispersive-material syntax for any given CST install.

### Score formula (NIR)

Default ('legacy', matches the THz pipeline):
```
score = |f_peak − target| + 0.2 × max(0, 0.90 − peak_abs)
```

Opt-in ('improved' — gives gradient even at low peak amplitude, includes FWHM weight):
```
score = |f_peak − target| + α × (1 − peak_abs)²
        + β × |fwhm − target_fwhm|       # if a target FWHM is set
```

Switch via `score_design(..., formula='improved')` or by setting the per-hypothesis config in [`nir/runner.py`](nir/runner.py).

## Project Structure

```
auto_cst/
├── agent.py                  # THz: autonomous optimization loop (ChatGPT-driven)
├── design.py                 # THz: ONLY mutable file — SRR geometric parameters
├── runner.py                 # THz: fixed experiment harness (CST COM interface)
├── evaluator.py              # THz: fixed scoring function
├── constraints.py            # THz: hard fabrication constraints
├── program.md                # THz: agent policy document (physics hints, rules)
├── results.tsv               # THz: experiment ledger (append-only)
├── optimization_report.png   # THz: auto-generated progress plot
│
├── nir/                      # NIR (1550 nm) absorber pipeline
│   ├── design_A.py, constraints_A.py     # disk MIM
│   ├── design_B.py, constraints_B.py     # rectangular-patch MIM
│   ├── design_C.py, constraints_C.py     # planar Fabry-Perot stack
│   ├── geometry_disk.py                  # disk VBA builder
│   ├── geometry_ellipse.py               # rect-patch VBA builder
│   ├── geometry_planar.py                # planar stack VBA builder
│   ├── materials.py                      # NIR-band Au, Ag, SiO₂ (constant-σ)
│   ├── runner.py                         # hypothesis-dispatched CST harness
│   ├── agent.py                          # LLM-in-loop optimizer (gpt-4o)
│   ├── evaluator.py                      # peak detection + score (legacy + improved)
│   ├── cst_helpers.py                    # cst.results wrapper (footgun-safe)
│   ├── run_hypothesis_A.py               # entrypoints (per-hypothesis)
│   ├── run_hypothesis_B.py
│   ├── run_hypothesis_C.py
│   ├── plot_final_report.py              # comparison spectra plot
│   ├── probe_drude_vba.py                # auto-discover Drude VBA syntax
│   └── VBA_COOKBOOK.md                   # tested CST VBA snippets + known failures
│
├── runs/                     # NIR per-run artifacts (CST binaries gitignored)
│   ├── FINAL_REPORT.md                   # comparative report across A / B / C
│   ├── FINAL_REPORT_spectra.png          # comparison plot
│   └── <timestamp>/hypothesis_X_<shape>/
│       ├── result.json                   # final design + score + metrics
│       ├── results_X.tsv                 # per-candidate ledger
│       ├── iteration_log.json            # ChatGPT reasoning per iter
│       └── iteration_NN/                 # per-iter spectra (CSVs) + JSON record
│                                         # working_X.cst regeneratable, gitignored
│
└── templates/
    └── base_project.cst      # Frozen CST template (used by both pipelines)
```

### Architecture Mapping (autoresearch → CST)

| autoresearch      | CST AutoResearch      | Role                          |
|-------------------|-----------------------|-------------------------------|
| `train.py`        | `runner.py`           | Fixed experiment harness      |
| `design.py`       | `design.py`           | Mutable parameters            |
| `program.md`      | `program.md`          | Agent policy + physics hints  |
| validation loss   | score (freq + refl)   | Scalar optimization metric    |
| `aider` edits     | ChatGPT JSON response | LLM proposes parameter edits  |
| git log           | `results.tsv`         | Experiment history            |

## Tunable Parameters

| Parameter    | Baseline | Unit | Physics Effect                              |
|-------------|----------|------|---------------------------------------------|
| `p`         | 50.0     | μm   | Unit cell period; affects coupling           |
| `outer_srr` | 45.0     | μm   | SRR outer dimension; main frequency lever    |
| `w`         | 2.0      | μm   | Trace width; inductance/capacitance          |
| `gap`       | 0.6      | μm   | Split gap; capacitance (↓ gap → ↓ freq)     |
| `t_m`       | 0.1      | μm   | Metal thickness; loss/inductance             |
| `st`        | 30.0     | μm   | Substrate thickness; effective index         |
| `length_arm`| 25.0     | μm   | Arm coupling; effective path length          |

## Constraints

Hard fabrication rules enforced before every simulation:

- `gap >= 0.4 μm`
- `w >= 1.0 μm`
- `outer_srr < p` (SRR must fit in unit cell)
- `outer_srr > 2 * w`
- `t_m ∈ [0.05, 1.0] μm`
- `st ∈ [5.0, 100.0] μm`
- `p ∈ [10.0, 300.0] μm`
- `length_arm >= 2.0 μm` and `< outer_srr`

## Results

### 0.4 THz Target (from 0.81 THz baseline) — THz pipeline

- **14 experiments, 14 kept** (zero reverts)
- **Final frequency**: 0.4016 THz (error: 0.0016 THz)
- **Total time**: ~12 minutes
- Strategy: agent scaled `outer_srr` and `p` together in ~3 μm steps, fine-tuned with `gap` and `length_arm`

### 1550 nm target — NIR pipeline (hypothesis A)

- **8 iterations, 4 kept**, 4 reverts (the LLM was briefly fooled by a mode-hop in iters 2–5; recovered after expanding the unit cell)
- **Final wavelength**: 1554.94 nm (error: 5 nm = 0.32 %)
- **Final peak absorption**: 99.94 %
- **FWHM**: 105 nm (target was 200 nm — broadening to 200 nm needs a topology change, see [report §5](runs/FINAL_REPORT.md))
- **Total time**: ~14 minutes (8 CST runs + LLM API calls)
- Strategy: agent identified `r` (disk radius) as the strongest peak-position lever, then `d` (spacer) for fine-tuning. The retry-on-constraint-violation handled `r > (p − 50)/2` correctly by proposing both `p` and `r` increases together.

Hypothesis B (rectangular patch) reached 1662 nm at 79 % absorption — partial. Hypothesis C (uniform planar Au/SiO₂/Ag stack) failed to converge under the constant-σ material model used here; the lithography-free planar absorber class needs dispersive Au/Ag, which awaits a fix to the Drude VBA syntax (see [`nir/probe_drude_vba.py`](nir/probe_drude_vba.py)).

## Design Details

### Split-Ring Resonator (SRR)

The test design is a gold SRR on a lossless silicon substrate (ε = 11.9) with:
- Floquet port excitation (periodic unit cell)
- Frequency-domain solver
- Unit cell boundary conditions

### Scoring

```
score = |f_resonance - target| + 0.2 * max(0, 0.90 - reflectance)
```

The frequency error dominates; the reflectance penalty only activates if the resonance peak drops below 90%.

## Acknowledgments

- Architecture inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
- CST Studio Suite COM/Python interface by Dassault Systèmes
- OpenAI GPT-4o for agent reasoning
