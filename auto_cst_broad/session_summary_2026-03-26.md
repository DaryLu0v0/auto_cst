# Broadband CWC Absorber Optimization — Session Summary (2026-03-26)

## Project

- **Path**: `D:/Dary/agent/broad/Agent_fine/auto_cst_broad`
- **CST file**: `Ge_Abs_CWC_5x5_run10 (1).cst`
- **Structure**: 5x5 CWC (cross-wire-coupled) array on Ge dielectric, MIM stack (Au ground / Ge spacer 0.6 um / Au CWC 0.1 um / vacuum)
- **75 parameters**: 3 per cell (x, g, w) x 25 cells

## Goal Change

- **Previous target band**: 14-22 um (13.636-21.429 THz)
- **New target band**: 14-18 um (16.667-21.429 THz)
- Narrowed to focus on a more achievable bandwidth for the 5x5 array

## What Was Done This Session

### 1. Band narrowing (14-22 um -> 14-18 um)

Updated the following files to target the new 16.667-21.429 THz band:

- **`evaluator.py`**: Changed `BAND_FREQ_MIN_THZ = 300.0 / 18.0` (16.667 THz) and `BAND_FREQ_MAX_THZ = 300.0 / 14.0` (21.429 THz)
- **`agent.py`**: Updated docstring and system prompt to reflect the 14-18 um band

### 2. Optimization Run 1 (candidates 0001-0015)

- Started from **baseline** (0001): 9.2% mean absorption
- GPT-5.4 quickly diagnosed broken cross arms and re-seeded parameters
- Rapid improvement: 9.2% -> 43.1% -> 46.0% -> 59.3% -> **68.1%** (candidate 0006)
- Candidate 0006 became the new best and was never surpassed
- Subsequent iterations (0007-0015) all reverted to 0006 as parent — none improved

| Candidate | Mean Abs | Min Abs | Weakest Freq (THz) | Score  |
|-----------|----------|---------|---------------------|--------|
| 0001      | 9.2%     | 6.7%    | 18.31               | 0.908  |
| 0002      | 43.1%    | 19.6%   | 16.67               | 0.569  |
| 0003      | 46.0%    | 21.4%   | 16.67               | 0.540  |
| 0004      | 59.3%    | 37.4%   | 16.67               | 0.408  |
| **0006**  | **68.1%**| **51.5%**| **16.86**           | **0.319** |

### 3. Optimization Run 2 (candidates 0016-0025)

- Continued from best candidate 0006
- 1 solver crash (0016), 9 successful evaluations
- None beat 0006 — best attempt was 0017 at 61.8% mean absorption
- Optimizer stuck in local optimum

### 4. Optimization Run 3 (candidates 0026-0035)

- Another 10 iterations continuing from 0006
- All reverted — best attempt was 0030 at 63.9% mean absorption
- Confirmed plateau: 30 consecutive iterations without improvement over 0006

## Current Best Design

**Candidate 0006** (saved in `design.py`):

| Metric | Value |
|--------|-------|
| Score | 0.319 |
| Mean absorption | 68.1% |
| Min absorption | 51.5% |
| Freq at min | 16.858 THz (17.8 um) |
| Band coverage >90% | 0.0% |

## Total Candidates Evaluated

| Metric | Value |
|--------|-------|
| Total candidates | 35 |
| Successful simulations | 34 |
| Solver crashes | 1 (candidate 0016) |
| Improvements found | 5 (0001 -> 0002 -> 0003 -> 0004 -> 0006) |
| Stagnation streak | 29 iterations since last improvement |

## Known Issues & Observations

1. **Local optimum plateau**: Candidate 0006 has been the best for 29 consecutive iterations. GPT-5.4's perturbation-based approach cannot escape this basin.

2. **Band-edge tradeoff**: Improving absorption at the high-frequency edge (~21.4 THz / 14 um) consistently degrades the low-frequency side (~16.7 THz / 18 um), and vice versa.

3. **Empty GPT-5.4 responses**: Fixed with the None/empty content check in `call_chatgpt()`, but the reasoning model occasionally exhausts tokens on thinking. `max_completion_tokens` set to 16384.

4. **Solver crash** (candidate 0016): One CST solver error occurred, likely due to CST Studio Suite being open during the run. Always close CST before launching.

## Suggested Next Steps

1. **Reset with new baseline**: Use `--reset` to escape the local optimum with a completely different initial seed
2. **Multi-start strategy**: Run several resets and pick the best across all starts
3. **Increase exploration**: Modify the system prompt to encourage GPT-5.4 to make larger, more diverse parameter changes (reseed 50%+ of cells simultaneously)
4. **Tune Ge spacer thickness**: If CST allows varying `t`, that extra degree of freedom could help bridge the absorption gap
5. **Consider score function**: Add a penalty for min absorption to encourage flatter spectra, e.g. `score = 1 - 0.7*mean_abs - 0.3*min_abs`

## Key Files

| File | Purpose |
|------|---------|
| `runner.py` | CST pipeline — unit fix applied here |
| `evaluator.py` | Score = 1 - mean(absorptance in 16.667-21.429 THz band) |
| `agent.py` | GPT-5.4 optimization loop |
| `constraints.py` | Geometry validation (x, w, g bounds + arm length) |
| `design.py` | Current best parameter values (candidate 0006) |
| `results.tsv` | Experiment log (35 rows) |
| `exports/` | Per-candidate CSV exports (Absorptance, S-params, RTA) |

## Run Commands

```bash
# Continue optimization (picks up from best candidate 0006)
cd D:/Dary/agent/broad/Agent_fine/auto_cst_broad
PYTHONPATH="E:/cst/AMD64/python_cst_libraries:$PYTHONPATH" /d/cst/Python/python.exe agent.py --max-iter 20 --api-key <KEY>

# Reset with new baseline
PYTHONPATH="E:/cst/AMD64/python_cst_libraries:$PYTHONPATH" /d/cst/Python/python.exe agent.py --max-iter 20 --reset --api-key <KEY>

# Single test run
PYTHONPATH="E:/cst/AMD64/python_cst_libraries:$PYTHONPATH" /d/cst/Python/python.exe runner.py --note "test" --candidate-id test_001
```
