# Broadband CWC 5×5 Absorber: Optimization Insights for 14-18 μm Band

**Project**: `D:\Dary\agent\broad\Agent_fine`
**Date**: 2026-03-24 to 2026-03-29
**Total CST simulations**: 123 candidates evaluated
**Target**: Maximize mean absorptance over 14-18 μm (16.67-21.43 THz)

---

## 1. Structure & Parameter Space

- **Stack**: Au ground (0.1 μm) / Ge spacer (0.6 μm) / Au CWC (0.1 μm) / Vacuum
- **Array**: 5×5 unit cells, pitch = 4.0 μm, periodic boundary conditions
- **75 tunable parameters**: 3 per cell (x, g, w) × 25 cells
  - `x` (margin): controls outer radius r1 = 2.0 - x → main resonance tuning lever
  - `g` (gap): cross-arm length = r2 - g/2 → coupling strength and Q-factor
  - `w` (width): inner radius r2 = r1 - w → impedance matching
- **Constraints**: x ∈ [0.1, 1.8], g ∈ [0.1, 3.5], w ∈ [0.05, 1.5], r1 ≥ 0.15, r2 ≥ 0.02

## 2. Best Results Achieved

| Approach | Candidate | Mean Abs | Min Abs | Min Location | Score |
|----------|-----------|----------|---------|--------------|-------|
| GPT-5.4 (v1) | 0006 | **68.1%** | 51.5% | 17.8 μm | 0.319 |
| 1x1 Agent v2 | 0053 | 68.1% | 33.2% | 18.0 μm | 0.319 |
| 1x1 Agent v3 (coupling-aware) | 0086 | 66.5% | **45.1%** | 18.0 μm | 0.335 |

**No design achieved >90% absorption at ANY wavelength in the 14-18 μm band.**

## 3. Optimization Approaches Tried

### Phase 1: GPT-5.4 Guided (candidates 0001-0035)
- LLM analyzes spectrum, proposes parameter perturbations each iteration
- Rapid initial improvement: 9.2% → 68.1% in 5 iterations
- Then complete stagnation: 29 consecutive iterations with no improvement
- **Lesson**: LLM-guided perturbation is good for coarse optimization but cannot escape local optima in a 75-dimensional space

### Phase 2: 1×1 Lookup Table + Greedy Tiling (candidates 0036-0062)
- Pre-computed 1500 single-cell simulations (1×1 periodic) across parameter space
- Greedy algorithm tiles the 14-18 μm band by selecting cells whose 1×1 peaks cover uncovered bins
- Iterative swap: replace cells targeting weak sub-bands
- **Lesson**: 1×1 peaks do NOT predict 5×5 array behavior reliably. Near-field coupling between cells shifts resonances significantly

### Phase 3: Coupling-Aware Design (candidates 0063-0123)
- Edge-weighted bin scoring (17-18 μm bins get 2× weight)
- Balanced sub-band allocation: forced 4/4/4/8/3 cells across 14-15/15-16/16-17/17-18/18-20 μm
- 2D simulated annealing for spatial arrangement (frequency-gradient grid)
- Beyond-band (18-20 μm) candidates for tail absorption contribution
- **Lesson**: Improved min_abs (33% → 45%) and spectral uniformity, but slightly reduced mean_abs

---

## 4. Key Physics Insights

### 4.1 The 17-18 μm Weakness Is Structural

The 18 μm (16.67 THz) band edge is consistently the weakest point across ALL optimization approaches. Root causes:

1. **Sparse candidate space**: Only 27 out of 1500 single-cell geometries have 1×1 peaks at 17-18 μm, vs 76 at 14-15 μm. The CWC geometry naturally favors shorter wavelengths.

2. **Triple-peak structure**: Most 17-18 μm candidates are triple-peak cells (peaks at ~8, ~13, ~17 μm). Their absorption power is distributed across all peaks, diluting the 17-18 μm contribution.

3. **Cavity interference**: The 0.6 μm Ge spacer creates a Fabry-Perot condition. At 18 μm, the spacer is ~λ/30 (very thin), which reduces the magnetic resonance coupling efficiency of the MIM cavity.

### 4.2 Band-Edge Tradeoff

There is a fundamental tradeoff between the two band edges:
- Improving 14 μm absorption (high-freq edge) → requires smaller r1 (larger x) → degrades 18 μm
- Improving 18 μm absorption (low-freq edge) → requires larger r1 (smaller x) → degrades 14 μm
- With only 25 cells and 4 μm span, there aren't enough degrees of freedom to cover both edges AND the mid-band simultaneously

### 4.3 1×1 Peaks ≠ 5×5 Array Behavior

**Critical finding**: A cell with a 1×1 peak at 17.8 μm does NOT produce a peak at 17.8 μm when placed in the 5×5 array. The reasons:

- **Near-field coupling** between adjacent cells shifts resonances (typically by 0.3-1.0 μm)
- **Mutual impedance** changes the effective impedance matching
- **Periodicity effects**: The 5×5 array with periodic boundaries creates a super-cell with complex mode structure
- **Consequence**: The 1×1 lookup table is useful for SEEDING but not for precise targeting

### 4.4 Neighbor Coupling Is 2D, Not 1D

Each cell in the 5×5 array couples with 4 neighbors (up/down/left/right), not just its row neighbors:
- Adjacent cells with **similar** resonant frequencies → strong coupling → mode splitting → **broadened** absorption
- Adjacent cells with **very different** frequencies → weak coupling → act independently
- A 1D serpentine arrangement leaves vertical neighbors with huge frequency gaps (up to 3.65 μm)
- Proper 2D optimization (simulated annealing) reduces the max neighbor gap to ~2 μm

### 4.5 CWC Geometry Patterns for Different Wavelength Ranges

From analysis of 1500 single-cell simulations:

| Target λ | x range | g range | w range | Notes |
|----------|---------|---------|---------|-------|
| 14-15 μm | 0.3-0.6 | 1.0-1.6 | 0.2-0.3 | Moderate r1, large gap |
| 15-16 μm | 0.1-0.3 | 1.1-1.6 | 0.2-0.3 | Large r1, large gap |
| 16-17 μm | 0.1-0.4 | 0.8-1.4 | 0.2-0.3 | Large r1, moderate gap |
| 17-18 μm | 0.1-0.3 | 0.6-1.3 | 0.2-0.3 | Large r1, **small gap** is key |
| 18-20 μm | 0.9-1.2 | 0.6-1.0 | 0.2-0.3 | Small r1 (single-peak mode) |

**Key pattern**: Reaching 17-18 μm requires g < 1.3 (small gap = long cross-arms = lower frequency). The width w is not a strong discriminator (~0.2-0.3 across all bands).

---

## 5. What Works and What Doesn't

### What Works
- **Greedy band-tiling with forced sub-band allocation**: Ensures every 1 μm sub-band gets adequate cell count (4/4/4/8/3 split)
- **2D coupling-aware placement (simulated annealing)**: Creates smooth frequency gradient across the array, maximizing beneficial near-field coupling for all neighbors
- **Beyond-band candidates (18-20 μm)**: Their absorption tails contribute to the 17-18 μm edge
- **Swap memory**: Prevents oscillating between failed configurations during iterative refinement
- **Edge-cluster shuffle strategy**: When stagnating on edge weakness, replacing multiple cells simultaneously toward 17-18 μm

### What Doesn't Work
- **Random/sequential grid placement**: Ignoring spatial coupling wastes potential broadening effects
- **Single-cell swaps for edge improvement**: Swapping ONE cell to fix 17-18 μm always removes more mid-band coverage than it adds edge coverage
- **Over-weighting edge bins (3×)**: Causes nearly all cells to target 17-18 μm, starving the mid-band
- **Pure LLM-guided perturbation**: Stagnates after ~5-10 improvements in 75D space
- **Trusting 1×1 peaks for 5×5 targeting**: Coupling shifts are too large (0.3-1.0 μm) for precise control

---

## 6. Stagnation Analysis

All three optimization approaches plateau at score ≈ 0.32-0.34 (mean_abs 66-68%). The stagnation pattern:

1. **Iterations 1-5**: Rapid improvement (score drops from 0.9 to 0.32)
2. **Iterations 6-15**: Occasional small improvements (score fluctuates ±0.02)
3. **Iterations 15+**: Complete stagnation. No combination of 1-5 cell swaps improves the score

**Root cause**: The optimization is trapped in a basin where:
- Improving any sub-band requires redistributing cells from another sub-band
- The 1×1 lookup table doesn't have candidates that produce the needed resonances in the 5×5 context
- The swap search space (25 cells × 453 candidates) is large but the useful moves are exhausted

---

## 7. Recommendations for Future Optimization

### 7.1 Spacer Thickness as a Lever
The 0.6 μm Ge spacer is currently FIXED. Making it tunable (even as a global parameter) could:
- Shift the Fabry-Perot condition to better support 17-18 μm
- A thicker spacer (0.8-1.0 μm) might improve long-wavelength absorption
- This is the highest-impact single change available

### 7.2 Direct 5×5 Parameter Optimization
Instead of relying on 1×1 lookup → 5×5 mapping:
- Use Bayesian optimization (e.g., BO with Gaussian processes) directly on the 75D parameter space
- Each CST evaluation takes ~10 min, so budget ~200-500 evaluations
- Use the current best design as the starting point, not random initialization

### 7.3 Gradient-Based Approaches
CST supports adjoint sensitivity analysis:
- Compute ∂(absorptance)/∂(parameter) for all 75 parameters simultaneously
- Use gradient descent to directly optimize the broadband score
- Much more efficient than evolutionary/swap approaches in high-D spaces

### 7.4 Symmetry Exploitation
The current 5×5 design uses 75 independent parameters. Consider:
- **Mirror symmetry** (x/y): reduces to ~21 independent cells → 63 parameters
- **Rotational symmetry** (C4): reduces to ~7 independent cells → 21 parameters
- Fewer parameters = easier optimization, but less design freedom

### 7.5 Multi-Layer or Graded Spacer
- A graded Ge spacer (thicker under long-wavelength cells, thinner under short-wavelength cells) could decouple the Fabry-Perot condition from the CWC resonance
- This requires modifying the CST model but could fundamentally solve the edge tradeoff

### 7.6 Expand the 1×1 Database
Current: 1500 simulations. Only 27 candidates at 17-18 μm.
- Run 500+ additional 1×1 simulations specifically targeting g ∈ [0.5, 1.3], x ∈ [0.1, 0.3], w ∈ [0.15, 0.35]
- This is the geometry regime that produces 17-18 μm peaks
- More candidates = better tiling = potentially better 5×5 designs

---

## 8. File Reference

| File | Purpose |
|------|---------|
| `auto_cst_broad/agent_1x1.py` | v3 optimization agent (coupling-aware, balanced sub-band allocation) |
| `auto_cst_broad/runner.py` | CST automation harness |
| `auto_cst_broad/evaluator.py` | Broadband scoring (score = 1 - mean_abs over 14-18 μm) |
| `auto_cst_broad/design.py` | Current best design parameters (75 values) |
| `auto_cst_broad/results.tsv` | Full experiment log (123 candidates) |
| `auto_cst_broad/exports/0086/` | Best v3 absorptance spectrum |
| `RAG/CST 1by1/absorptance_analysis_1by1.csv` | 1×1 lookup table (1500 candidates) |

---

## 9. Quick-Start for Next Session

To resume optimization from the current best:
```bash
cd D:\Dary\agent\broad\Agent_fine\auto_cst_broad
D:\cst\Python\python.exe agent_1x1.py --resume --resume-score 0.335223 --resume-candidate 0086 --max-iter 20
```

To generate a fresh seed with new sub-band targets:
```bash
D:\cst\Python\python.exe agent_1x1.py --seed-only
```

Python location: `D:\cst\Python\python.exe` (Python 3.12.9 with numpy 2.2.4)
