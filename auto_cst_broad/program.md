# Broadband Absorber -- Agent Operating Policy

## Goal

Maximize mean absorptance over the **14-18 um** band (16.67-21.43 THz)
for a 5x5 CWC (Complementary Wire Circle) Ge-based metamaterial absorber.

## Score

```
score = 1 - mean(absorptance over 14-18 um band)
```

Lower is better. Target: score < 0.02 (mean absorptance > 98%).

## Editable File

- **`design.py`** -- ONLY this file. Change values in the `DESIGN` dict.

## Do NOT Modify

- `runner.py`
- `evaluator.py`
- `constraints.py`
- `program.md`
- The CST project file

## Tunable Parameters (75 total)

For each cell (i,j) where i,j ∈ {0,1,2,3,4}:

| Parameter | Unit | Physics Effect                                    |
|-----------|------|---------------------------------------------------|
| `x_i_j`   | um   | Margin; outer radius r1 = 2.0 - x (main lever)  |
| `g_i_j`   | um   | Gap; coupling strength and Q-factor              |
| `w_i_j`   | um   | Width; inner radius r2 = r1 - w, impedance match |

Fixed: `a_i_j = 4.0 um` (pitch), all layer thicknesses.

## Hard Constraints

- `x_i_j` in [0.1, 1.8] um
- `w_i_j` in [0.05, 1.5] um
- `g_i_j` in [0.1, 3.5] um
- `r1 = 2.0 - x > 0.15` (outer radius must be positive)
- `r2 = r1 - w > 0.02` (inner radius must be positive)

## Experiment Loop

1. Read the current `design.py` and the latest `results.tsv` row.
2. Identify the weakest absorption point from `min_abs` and `freq_at_min_thz`.
3. Decide which cells to adjust (match cell r1 to resonance near freq_at_min).
4. Edit `design.py` with the new values.
5. Run: `python runner.py --note "<brief description>"`.
6. Read the score from stdout.
7. **If score improved**: keep the change.
8. **If score worsened**: revert `design.py` to previous values.
9. Repeat from step 1.

## Physics Hints

### Frequency vs Geometry

Each CWC cell resonates at a frequency roughly proportional to 1/r1.
- Larger r1 (smaller x) → lower resonance frequency
- Smaller r1 (larger x) → higher resonance frequency

### Broadband Coverage

The 25 cells have a distribution of r1 values. To fill an absorption gap
at a specific frequency:
1. Find which cells have r1 near the resonance frequency of the gap.
2. Slightly adjust those cells' x (and/or w, g) to shift or broaden
   their resonance.

### Gap and Width Effects

- **Gap g**: Controls coupling. Smaller g → broader resonance but
  potentially weaker peak. Larger g → sharper resonance.
- **Width w**: Controls impedance matching. Wider w → better matching
  to free space (stronger absorption). Also shifts r2.

## Strategy Guidelines

- **This is a finetune**: the design is already decent. Small changes only (1-5%).
- **Focus on the weakest point**: look at `freq_at_min_thz` and target cells near it.
- **Change multiple cells per iteration** for efficiency (75 params is a lot).
- **Do NOT make global changes** (e.g., "increase all x by 5%") -- this disrupts
  the carefully distributed resonance frequencies.
- **Never skip validation**: always run `python runner.py`.

## NEVER STOP

Keep iterating until the score reaches the threshold or stagnation is detected.
Log every attempt via the runner.
