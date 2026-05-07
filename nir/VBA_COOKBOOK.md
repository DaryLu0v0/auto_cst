# auto_cst CST VBA Cookbook

Tested on **CST Studio Suite** with `cst.interface` / `cst.results`
Python libraries at `E:\cst\AMD64\python_cst_libraries`. All snippets below
are pasted from working `m3d.add_to_history(tag, vba)` calls — they are
verified, not guessed. Snippets that DIDN'T work are also documented (with
the actual CST error) so the next debugger doesn't repeat the same trial.

Pattern of use everywhere: build the VBA string in Python, then

```python
m3d.add_to_history("NIR_X: step name", vba_string)
```

If a step fails, CST raises `Exception("...add_to_history... ActiveX
Automation: ...")` with the offending VBA line in the message. Inject
each block as a SEPARATE history step so failures localize.

---

## ✅ Working: project skeleton

### Delete the default PEC box (always first)

```vba
Component.Delete "component1"
```

### Units, frequency, boundary, background

```vba
With Units
  .Geometry "nm"
  .Frequency "THz"
  .Time "fs"
End With

With Solver
  .FrequencyRange "100", "300"
End With

With Boundary
  .Xmin "unit cell"
  .Xmax "unit cell"
  .Ymin "unit cell"
  .Ymax "unit cell"
  .Zmin "expanded open"
  .Zmax "expanded open"
End With

With Background
  .Type "Normal"
  .Epsilon "1.0"
  .Mu "1.0"
End With
```

### Floquet ports (both Zmax and Zmin)

```vba
With FloquetPort
  .Reset
  .SetDialogTheta "0"
  .SetDialogPhi "0"
  .SetPolarizationIndependentOfScanAnglePhi "0", "False"
  .SetSortCode "+beta/pw"
  .SetCustomizedListFlag "False"
  .Port "Zmax"
  .SetNumberOfModesConsidered "2"
  .SetDistanceToReferencePlane "0"
  .SetUseCircularPolarization "False"
  .Port "Zmin"
  .SetNumberOfModesConsidered "2"
End With
```

### Solver type + mesh

```vba
ChangeSolverType "HF Time Domain"
' OR
ChangeSolverType "HF Frequency Domain"

With Mesh
  .MeshType "PBA"          ' for TD; FD usually wants "Tetrahedral"
  .SetCreator "High Frequency"
End With
```

**Solver-mesh decision rule** (learned the hard way during hypothesis C):

| Geometry | Solver | Mesh |
|---|---|---|
| Patterned (LSPR-driven; disks, patches, SRRs) | **HF Time Domain** | PBA hex |
| Uniform planar (cavity-driven; thin-film MIM) | **HF Frequency Domain** | Tetrahedral |

Time Domain with periodic boundaries on a fully-uniform planar structure
**does not excite an absorbing mode** — gives identically zero absorptance.
Frequency Domain handles it correctly.

---

## ✅ Working: materials (constant-σ)

### Lossy metal (Au, Ag, Cr, etc.)

```vba
With Material
  .Reset
  .Name "Au_lossy"
  .Folder ""
  .FrqType "all"
  .Type "Lossy metal"
  .Sigma "4.1e7"
  .Colour "1.0", "0.84", "0.0"
  .Create
End With
```

DC conductivities used in `nir/materials.py`:

| Material | σ (S/m) | Notes |
|---|---:|---|
| Au | 4.1 × 10⁷ | Standard DC value |
| Ag | 6.3 × 10⁷ | Standard DC value |
| Cr | 7.7 × 10⁶ | DC; **bad approximation at NIR**, see hypothesis C |
| Ti | 2.38 × 10⁶ | Used in mid-IR scripts |

**Caveat.** "Lossy metal" with constant σ uses CST's high-frequency
surface-impedance approximation. At NIR (~200 THz), Au/Ag skin depth is
~13–25 nm — the approximation is borderline. It works fine for
**plasmonic-resonance-dominated** designs (disks, patches) where the LC
mode is the main physics, but **fails for impedance-matching-dominated**
designs (uniform planar absorbers) — the whole point of those is the
correct ε(ω) of a thin lossy film, which constant σ doesn't capture.

### Normal dielectric (SiO₂, etc.)

```vba
With Material
  .Reset
  .Name "SiO2"
  .Folder ""
  .FrqType "all"
  .Type "Normal"
  .Epsilon "2.10"
  .Mu "1"
  .Kappa "0"
  .TanD "0.0"
  .TanDGiven "True"
  .TanDModel "ConstTanD"
  .Colour "0.8", "0.8", "0.95"
  .Create
End With
```

NIR refractive indices used:

| Material | ε | n | Notes |
|---|---:|---:|---|
| SiO₂ | 2.10 | 1.45 | tan δ ≈ 0 |
| Si₃N₄ | 7.0 | 2.65 | tan δ ≈ 0.01 |
| Ge | 16.0 | 4.0 | tan δ ≈ 0.001 |

---

## ✅ Working: geometry primitives

### Brick (rectangular block)

```vba
With Brick
  .Reset
  .Name "ground"
  .Component "absorber"
  .Material "Au_lossy"
  .Xrange "-p/2", "p/2"
  .Yrange "-p/2", "p/2"
  .Zrange "0", "t_ground"
  .Create
End With
```

`p`, `t_ground` are CST parameters defined via `StoreDoubleParameter` first.

### Cylinder (circular)

```vba
With Cylinder
  .Reset
  .Name "disk"
  .Component "absorber"
  .Material "Ag_lossy"
  .Axis "z"
  .Outerradius "r"
  .Innerradius "0"
  .Xcenter "0"
  .Ycenter "0"
  .Zrange "t_ground + d", "t_ground + d + h"
  .Segments "0"
  .Create
End With
```

`Segments "0"` = smooth (geometry-correct), nonzero = N facets.

### Ellipse curve + ExtrudeCurve (NEEDS FIX)

```vba
' Defines a 2D ellipse curve. Compiles successfully.
With Curve
  .NewCurve "ellipse_curve"
End With

With Ellipse
  .Reset
  .Name "ellipse_profile"
  .Curve "ellipse_curve"
  .XRadius "rx"
  .YRadius "ry"
  .Xcenter "0"
  .Ycenter "0"
  .Segments "0"
  .Create
End With

With ExtrudeCurve
  .Reset
  .Name "disk"
  .Component "absorber"
  .Material "Ag_lossy"
  .Thickness "h"
  .Twistangle "0.0"
  .Taperangle "0.0"
  .DeleteProfile "True"
  .Curve "ellipse_curve:ellipse_profile"
  .Create
End With
```

This compiles in CST without errors — but in our hypothesis-B run it
produced an absorber with abs=0.73 instead of the expected ~0.99,
**suggesting the disk was placed at z=0..h instead of on top of the
spacer**. The Transform.Translate that should move it (see below) needs
the right syntax we don't yet have for this CST version.

**Workaround** (used in current `geometry_ellipse.py`): use a rectangular
patch (Brick) instead. Polarization sensitivity comes from `lx ≠ ly`.

---

## ❌ Failed: dispersive Au/Ag (Drude model)

I tried four flavors of inline Drude VBA. All failed with
`(10091) ActiveX Automation: no such property or method`:

```vba
' (1) NOT WORKING -- best-guess from CST docs
With Material
  .DispModelEpsilon "Drude"   ' <-- error: no such property
End With

' (2) NOT WORKING
With Material
  .DispModelEps "Drude"        ' <-- error
End With

' (3) NOT WORKING
With Material
  .Sigma "0"
  .EpsInfinity "1"
  .DispCoeff1Eps "1.367e16"    ' <-- error
End With

' (4) NOT WORKING
Material.LoadFromMaterialLibrary "Gold (Drude)"
```

The likely correct path is one of:

```vba
' Library load via With block:
With Material
  .Reset
  .Name "Gold (Lossy)"
  .Folder ""
  .LoadLibraryMaterial
End With

' OR the Lorentz-pole approach:
With Material
  .DispCoeffsAddLorentz ...
End With
```

These are unverified. **To resolve:** open CST GUI, manually create
"Gold (Lossy)" or "Gold (Johnson, Christy)" via the material library
import dialog, then save the project and read `History List → New material:
Gold (Lossy)` — that gives the literal VBA the GUI generated, which is
guaranteed to work in this CST version. See `nir/probe_drude_vba.py`
for a script that auto-tries variants and reports which (if any) succeed.

**Impact of not having dispersive materials:**
- A & B (LSPR-dominated): minimal — peak position correct, FWHM and
  amplitude slightly inaccurate.
- C (impedance-matching): catastrophic — no absorption at all.

---

## ❌ Failed: anisotropic stretch via Transform.Scale

Tried to stretch a circular cylinder into an ellipse by scaling the y-axis:

```vba
' NOT WORKING -- (10091) ActiveX Automation: no such property or method (.ScaleX)
With Transform
  .Reset
  .Name "absorber:disk"
  .Origin "Free"
  .Center "0", "0", "0"
  .ScaleX "1.0"        ' <-- error here
  .ScaleY "ry/rx"
  .ScaleZ "1.0"
  .Transform "Shape", "Scale"
End With
```

Field name `.ScaleX` doesn't exist on the Transform object. The likely
correct form is positional (single `.ScaleFactor "x", "y", "z"` call) or
named differently — see the same workflow as the Drude case (export from
GUI to discover the right syntax).

---

## ✅ Working: parameter injection

```vba
StoreDoubleParameter "p", 993.59
StoreDoubleParameter "r", 457.05
StoreDoubleParameter "h", 105.98
' ... etc
```

Or with parametric expressions:
```vba
StoreParameter "inner_radius", "r - 50"
```

Use `StoreDoubleParameter` for numeric values, `StoreParameter` for
parametric expression strings. Both are top-level VBA functions, NO
`With` block.

---

## ✅ Working: result export (post-solve)

```python
# After project.save() + project.close() + env.close():
from nir.cst_helpers import open_results, get_result_with_data, find_reflection_sparams

# IMPORTANT: pass an absolute path. Relative paths silently break run_id index.
proj3d, run_ids = open_results(working_cst_path)
tree_items = proj3d.get_tree_items()

# Find S(Zmax(i),Zmax(i)) reflection coefficient
reflections = find_reflection_sparams(tree_items)

for sp in reflections:
    # Auto-tries highest run_id first; falls back to lower run_ids if needed
    result, used_rid = get_result_with_data(proj3d, sp, run_ids)
    freq = result.get_xdata()
    s_complex = result.get_ydata()
    mag_sq = [abs(y)**2 for y in s_complex]
    absorptance = [1.0 - m for m in mag_sq]   # Au ground blocks transmission
```

**Two silent footguns** (now wrapped in `cst_helpers.py`):

1. **Absolute path required.** `cst.results.ProjectFile("relative/path.cst")`
   returns a project handle whose `get_result_item(path, run_id=N)` raises
   "ResultItem does not exist for run id=N" even though the data is in
   the file. Always pass `Path(...).resolve()`.

2. **run_id=0 default is wrong after parameter injection.**
   `proj3d.get_result_item(path)` with no run_id defaults to 0, but
   parameter injection invalidates the empty-template's run_id=0
   results — the actual data lives at run_id=1+. Always call
   `proj3d.get_all_run_ids()` and request the highest.

**Solver-dependent S-parameter naming** (learned from hypothesis C):

| Solver | S-params exposed |
|---|---|
| HF Time Domain | All 16: Zmax(i)→Zmax(j) and Zmax(i)→Zmin(j) for i,j ∈ {1,2} |
| HF Frequency Domain | Sometimes only port 2 excited: just 4 S-params with Zmax(2) as 2nd index |

Don't hardcode "Zmax(1),Zmax(1)". Use `find_reflection_sparams()` which
matches any diagonal `Zmax(i),Zmax(i)`.

---

## Time-domain solver settings

Standard:
```python
m3d.start_solver()
while m3d.is_solver_running():
    time.sleep(POLL_INTERVAL_S)   # we use 10 s
```

Add a hard wall-time cap (we use 30 min):
```python
if elapsed > SOLVER_TIMEOUT_S:
    m3d.abort_solver()
    return error_dict
```

**Smoke-test (`--quick`) mode** (added in this revision): coarser mesh
(5 cells/wavelength instead of 10) ~halves solve time. NOT accurate
enough for converged peak position — meant for catching VBA / geometry
errors before launching a full agent loop.

---

## Pre-flight checklist before launching `nir/agent.py`

1. **Dry-run** the runner: `python -m nir.runner --hypothesis X --dry-run`
   — verifies imports, design dict, constraints. <1 s.
2. **Smoke-test** with full CST: `python -m nir.runner --hypothesis X --quick`
   — verifies all VBA history steps execute, solver completes, S-params
   exported, peak detected. ~30–60 s.
3. **Inspect** the smoke spectrum: open `nir/working_default_X/Absorptance.csv`
   in any plotter. Check that:
   - Peak amplitude is reasonable (>0.5 for an MIM absorber on resonance;
     <0.1 with no peak is a smell — see hypothesis C).
   - Peak frequency is within an order of magnitude of target.
   - Mode hops between adjacent frequency points indicate noise; smooth
     spectrum is healthy.
4. **Only then** launch the agent: `python -m nir.run_hypothesis_X --reset`.

This 30–60 s smoke-test would have saved ~30 min on hypothesis B's first
agent run (broken ExtrudeCurve geometry, abs=0.73, mode-hopping LLM).
