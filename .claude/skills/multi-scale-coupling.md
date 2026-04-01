---
name: multi-scale-coupling
description: Build multi-scale CWC metamaterial array CST projects from scratch via Python. Creates NxN arrays (1x1, 2x2, 4x4, 8x8) with full solver setup, no template needed.
---

# Building Multi-Scale CWC Array CST Projects

## Core Procedure

Creates a fresh CST Microwave Studio project for any NxN CWC array entirely from Python — no manual CST setup or template file required.

### Step-by-step CST project creation

1. **Create blank project**: `env.new_mws()` → save with `project.model3d.SaveAs(path, False)`
2. **Add history items** (all via `mws.add_to_history(name, vba)`):
   - Units: um / THz
   - Background: vacuum, no extra space
   - Frequency range: `Solver.WavelengthRange "10", "20"`
   - Boundaries: `unit cell` X/Y, `expanded open` Z
   - Materials: Gold and Ge_IR loaded from VBA text files (`gold_vba.txt`, `ge_ir_vba.txt` extracted from original 1x1 model history)
   - Store parameters: per-cell `x_i_j`, `g_i_j`, `w_i_j`, `r1_i_j`, `r2_i_j`, `a_i_j` plus base params `t`, `t_gp`, `t_mm`, `Z`, `GLOBAL_SIZE`
   - Geometry: stackup bricks (GP, Ge, Vacuum) + per-cell CWC (Cylinder ring + Brick cross arm + Transform rotate 3x + Solid.Add boolean union)
   - Floquet ports: Zmin/Zmax, 2 modes, sort code `+beta/pw`
   - Problem type: `ChangeProblemType "Optical"` then `ChangeSolverType("HF Frequency Domain")`
   - Solver: FDSolver with `AddToExcitationList "Zmax", "TE(0,0);TM(0,0)"`
3. **Rebuild**: `mws.full_history_rebuild()` — safe because project has no prior history
4. **Solve**: `mws.start_solver()` + poll `mws.is_solver_running()`
5. **Close**: `project.save()`, `project.close()`, `env.close()`
6. **Export**: reopen with `cst.results.ProjectFile()` to extract S-parameters and compute absorptance

### Key CST API details

- `env.new_mws()` creates project in temp dir; use `model3d.SaveAs(abs_path, bool)` to relocate (2nd arg = include results)
- `project.save_as()` does NOT exist — must use `model3d.SaveAs()`
- `full_history_rebuild()` breaks if project has existing history (causes "Unknown error" on solver start); only use on fresh projects
- For existing projects, use `StoreDoubleParameter()` + `Rebuild()` instead
- Gold material: `.Type "Lossy metal"` with `.Sigma "4.561e+007"` (NOT `.Conductivity` or `.Kappa` under lossy metal context)
- Ge_IR material: tabulated dispersive fitting with ~130 `AddDispersionFittingValueEps` lines — must load from file, not simplified epsilon
- Material VBA files extracted from `D:/Dary/agent/broad/RAG/CST 1by1/CST 1by1/Ge_Abs_CWC_finetune_2/Model/3D/ModelHistory.json`

### CWC cell geometry (per cell)

```
Ring:      Cylinder(OuterRadius=r1, InnerRadius=r2, center=(cx,cy), z=[0, t_mm])
Cross arm: Brick(x=[-r2, -g/2], y=[-w/2, w/2], z=[0, t_mm]) centered at (cx,cy)
Rotate:    Transform cross arm 3x by 90° around (cx,cy)
Union:     Solid.Add ring + 4 arms
```

Where `r1 = a/2 - x`, `r2 = r1 - w`, `a = 4.0 um` (pitch).

### Stackup (bottom to top)

| Layer | Material | Z range |
|-------|----------|---------|
| Ground plane | Gold | `-(t+t_gp)` to `-t` |
| Dielectric | Ge_IR | `-t` to `0` |
| CWC pattern | Gold | `0` to `t_mm` |
| Vacuum | Vacuum | `t_mm` to `Z` |

Base params: `t=0.6, t_gp=0.2, t_mm=0.1, Z=3*a=12.0`

### Multi-scale checkerboard patterns

Given cell types `a` and `b`, the hierarchical arrangement is:
- **2x2**: `[a,b; b,a]` — single-cell checkerboard
- **4x4**: `[a_2,b_2; b_2,a_2]` — 2x2-block checkerboard
- **8x8**: `[a_4,b_4; b_4,a_4]` — 4x4-block checkerboard

### Scripts

| File | What it does |
|------|-------------|
| `coupling_study/build_and_run.py` | Main script: `--config {1x1_a,1x1_b,2x2,4x4,8x8,all}` |
| `coupling_study/compare_spectra.py` | Plot absorptance comparison after all runs |
| `coupling_study/gold_vba.txt` | Gold material VBA (from 1x1 model) |
| `coupling_study/ge_ir_vba.txt` | Ge_IR material VBA (from 1x1 model) |

### Usage

```bash
cd coupling_study/
/d/cst/Python/python.exe build_and_run.py --config 2x2
/d/cst/Python/python.exe build_and_run.py --config all
/d/cst/Python/python.exe compare_spectra.py
```
