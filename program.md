# CST AutoResearch -- Agent Operating Policy

## Goal

Shift the dominant SRR resonance from approximately **0.8 THz** toward **0.7 THz**
while maintaining strong absorption (>90%).

## Setup Protocol

1. Read this file (`program.md`), `design.py`, `constraints.py`, `evaluator.py`, and `runner.py`.
2. Verify `templates/base_project.cst` exists.
3. Verify `results.tsv` exists (create via `python runner.py --dry-run` if needed).
4. Run the baseline design unmodified: `python runner.py --note "baseline"`.
5. Record the baseline score. This is your starting point.

## Editable File

- **`design.py`** -- ONLY this file. Change values in the `DESIGN` dict.

## Do NOT Modify

- `runner.py`
- `evaluator.py`
- `constraints.py`
- `templates/base_project.cst`
- `program.md`

## Tunable Parameters

| Parameter     | Baseline | Unit | Physics Effect                          |
|---------------|----------|------|-----------------------------------------|
| `p`           | 50.0     | um   | Unit cell period; affects coupling       |
| `outer_srr`   | 45.0     | um   | SRR outer dimension; main resonance      |
| `w`           | 2.0      | um   | Trace width; inductance/capacitance      |
| `gap`         | 0.6      | um   | Split gap; capacitance (lower gap -> lower freq) |
| `t_m`         | 0.1      | um   | Metal thickness; loss/inductance         |
| `st`          | 30.0     | um   | Substrate thickness; effective index     |
| `length_arm`  | 25.0     | um   | Arm coupling; effective path length      |

## Hard Constraints

- `gap` >= 0.4 um
- `w` >= 1.0 um
- `outer_srr` < `p`
- `outer_srr` > 2 * `w`
- `t_m` in [0.05, 1.0] um
- `st` in [5.0, 100.0] um
- `p` in [10.0, 300.0] um
- `length_arm` >= 2.0 um and < `outer_srr`
- Preserve SRR topology (no shape changes, only parameter tuning)

## Objective

**Minimize the score** reported by `python runner.py`.

Score = |f_resonance - 0.7| + 0.2 * max(0, 0.90 - absorption)

## Experiment Loop

1. Read the current `design.py` and the latest `results.tsv` row.
2. Decide on ONE parameter change (or a small coordinated set).
3. Edit `design.py` with the new values.
4. Run: `python runner.py --note "<brief description of what you changed>"`.
5. Read the score from stdout.
6. **If score improved**: keep the change, note it as "keep" in your log.
7. **If score worsened or crashed**: revert `design.py` to the previous values,
   note it as "discard".
8. Repeat from step 1.

## Physics Hints

To **lower** resonance frequency:
- **Increase `outer_srr`** -- longer effective path = lower frequency (strongest lever)
- **Increase `length_arm`** -- longer coupling arms add inductance
- **Decrease `gap`** -- smaller gap = more capacitance = lower frequency
- **Increase `st`** -- thicker substrate raises effective permittivity

To **raise** absorption:
- **Increase `w`** -- wider traces reduce ohmic loss
- **Decrease `gap`** slightly -- stronger LC coupling
- **Tune `st`** -- impedance matching to free space

## Strategy Guidelines

- **Start with the strongest lever**: `outer_srr` scaling.
  A 12.5% increase (45 -> 50.6 um) should shift resonance ~12.5% down.
- **Prefer single-parameter changes** to isolate effects.
- **Small steps**: change by 5-15% at a time to stay in the linear regime.
- **If stuck**, try coordinating two parameters (e.g., increase `outer_srr` + decrease `gap`).
- **Never skip validation**: always run `python runner.py`, don't guess scores.

## NEVER STOP

Keep iterating until the score reaches 0.0 or you have exhausted all reasonable
parameter combinations. The human may not be watching.
Log every attempt in `results.tsv` via the runner.
