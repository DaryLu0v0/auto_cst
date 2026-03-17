# CST AutoResearch

> Autonomous metamaterial design optimization — inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch)

Treat a CST Studio Suite simulation like `train.py`: an LLM agent iteratively modifies geometric parameters, runs full-wave EM simulations, evaluates results, and keeps or reverts changes to hit a target resonance frequency.

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

## Project Structure

```
auto_cst/
├── agent.py           # Autonomous optimization loop (ChatGPT-driven)
├── design.py          # ONLY mutable file — geometric parameters
├── runner.py          # Fixed experiment harness (CST COM interface)
├── evaluator.py       # Fixed scoring function
├── constraints.py     # Hard fabrication constraints
├── program.md         # Agent policy document (physics hints, rules)
├── results.tsv        # Experiment ledger (append-only)
├── optimization_report.png  # Auto-generated progress plot
└── templates/
    └── base_project.cst     # Frozen CST template
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

### 0.4 THz Target (from 0.81 THz baseline)

- **14 experiments, 14 kept** (zero reverts)
- **Final frequency**: 0.4016 THz (error: 0.0016 THz)
- **Total time**: ~12 minutes
- Strategy: agent scaled `outer_srr` and `p` together in ~3 μm steps, fine-tuned with `gap` and `length_arm`

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
