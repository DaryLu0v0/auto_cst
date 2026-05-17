# auto_cst CST VBA Cookbook

Tested on **CST Studio Suite** with `cst.interface` / `cst.results`
Python libraries at `E:\cst\AMD64\python_cst_libraries`. All snippets below
are pasted from working `m3d.add_to_history(tag, vba)` calls — they are
verified, not guessed. Snippets that DIDN'T work are also documented (with
the actual CST error) so the next debugger doesn't repeat the same trial.

> **See also**:
> - [`feedback_cst_2026_vba`](../../../../.claude/projects/D--Claude-MetaClaw/memory/feedback_cst_2026_vba.md) memory — VBA gotchas specific to CST 2026
> - [`reference_cst_python`](../../../../.claude/projects/D--Claude-MetaClaw/memory/reference_cst_python.md) memory — pointer to the ok-nc/cst_python authoritative API reference
> - `nir/cst_helpers.py` — drop-in helpers (`HistoryBuilder`, `save_project_at`, `verify_solids_exist`, `verify_materials_exist`, `assert_spectrum_nontrivial`) — use these instead of raw add_to_history

Pattern of use everywhere: build the VBA string in Python, then

```python
m3d.add_to_history("NIR_X: step name", vba_string)
```

If a step fails, CST **may** raise `Exception("...add_to_history... ActiveX
Automation: ...")` with the offending VBA line in the message. **But only for
some failure modes** — see the "Layered silent-failure pattern" section
below. Inject each block as a SEPARATE history step so failures localize.

---

## What is and isn't general in this codebase (read first)

The auto_cst pipeline is split deliberately into "general primitives" and
"hypothesis-specific build scripts". Understand the split before writing
code:

| Layer | Where | Reusable as-is? |
|---|---|---|
| **General primitives** | `nir/cst_helpers.py` (HistoryBuilder, save_project_at, verify_*_exists, assert_spectrum_nontrivial, open_results, find_reflection_sparams, get_messages_safe) | ✅ Yes — use for any new build |
| **Per-hypothesis geometry/design pattern** | `nir/design_<id>.py` + `nir/constraints_<id>.py` + `nir/geometry_<id>.py` | ✅ Pattern is general — write 3 new small files per new hypothesis |
| **Docs** | This file + `feedback_cst_2026_vba` memory | ✅ |
| **Build scripts** (`build_<id>.py` / `run_<id>_v*.py`) | `auto_cst/build_*.py` | ❌ **Hypothesis-specific examples**. Copy + adapt the materials / boundary / ports / solver / freq band when you write one for a new hypothesis. |

**Why the build scripts are intentionally not factored into one universal
class**: the wiring choices in a build script — which materials, which
boundary conditions, which port type, which solver, which frequency band
— are domain-physics decisions, not boilerplate. Forcing them into a
config-dict abstraction obscures the physics. The right abstraction is
the *helpers*, and we already have those.

`build_elc_11ghz.py` is the cleanest example to copy from (uses Mode 3
SaveAs + HistoryBuilder + pre-flight render + flat-spectrum guard; CST
2026 verified). The older `build_midIR_*.py` / `run_midIR_v*.py` files
predate the helpers and are NOT canonical references — they still work
but don't use the silent-failure protections.

---

## ⚠️ CST 2026 ERRATA (updated 2026-05-11)

The cookbook below was authored against an earlier CST version. Several
property names + idioms have drifted in CST 2026 (the version installed
on the user's `cst_inference` conda env). If you're working in CST 2026,
use the forms here **instead of** the original cookbook sections — those
sections remain valid for older CST versions for historical reference.

### Layered silent-failure pattern (THE most important update)

`m3d.add_to_history(label, vba)` returns *success* on:
- **Property-existence errors** raise `(10091) ActiveX Automation: no such
  property or method` with the offending VBA line. These are noisy and
  easy to debug.

But it silently swallows:
- **Undefined material name** in a brick → brick fails to create, NO Python
  exception, no log line. Caused our v1 build to "solve" in 10s with 0
  S-parameters and 0 mesh cells.
- **Missing component** → same silent-failure mode.
- **Geometric pathology** (zero-volume brick, e.g. negative ranges from
  a bad parameter expression) → same silent-failure.
- **`.TanD` vs `.Tandd`** — `.Tandd` raises loudly in CST 2026; but other
  Material property typos may not.

**Never trust `add_to_history` exit alone.** Use `HistoryBuilder` (in
`cst_helpers.py`) which verifies side effects after every step:

```python
from nir.cst_helpers import HistoryBuilder
from nir.geometry_elc import expected_solid_names

builder = HistoryBuilder(project)
builder.add("Step 1: Units", VBA_UNITS)
builder.add("Step 2: Parameters", vba_params,
            expects_parameters=["a", "d", "l", "w", "g"])
builder.add("Step 6: FR4 material", VBA_FR4,
            expects_materials=["FR4"])
builder.add("Step 7: ELC geometry", vba_geom,
            expects_solids=expected_solid_names())
builder.add("Step 8: Floquet ports", VBA_PORTS)
```

The builder raises `RuntimeError` with the specific step + missing
artifact on any silent failure. Verification overhead is ~50 ms per check.

### Don't put `SaveAs` in history (CRITICAL)

`SaveAs` is a CST VBA function that writes the project to disk. Putting it
in `add_to_history` causes a **circular file-lock error** on every reopen:
CST regenerates history when opening, the SaveAs tries to overwrite the
currently-open .cst, and you get "History Error: Saving of <path> failed
(&H8000ffff)". Use Mode 3 instead:

```python
# Wrong (cookbook used to recommend this):
m3d.add_to_history("save_as", f'SaveAs "{path}", "True"')

# Right (one-shot, leaves no history trace):
from nir.cst_helpers import save_project_at
save_project_at(project, path)
```

`save_project_at` uses `prj.schematic.execute_vba_code` with a `Sub Main`
wrapper — Mode 3 in the cst_python repo's terminology. The VBA runs
exactly once, doesn't replay.

### Don't copy the polluted template; use `env.new_mws()`

`templates/base_project.cst` ships with leftover parameters from the
broadband-absorber pipeline (`p, st, w, gap, outer_srr, length_arm, t_m`)
and units `um/THz/ns`. These corrupt new builds:
- Your `w` parameter collides with the template's `w` (different
  semantics).
- Your geometry stored in nm gets interpreted as µm — a 1000× scale
  error that makes the unit cell kilometers wide.

```python
# Wrong (cookbook used to recommend this):
TEMPLATE = "D:/Claude/auto_cst/templates/base_project.cst"
shutil.copy2(TEMPLATE, target_cst)
proj = env.open_project(str(target_cst))

# Right (clean empty MWS project):
env = cstint.DesignEnvironment()
proj = env.new_mws()
save_project_at(proj, target_cst)
```

### Default units of `new_mws()`: mm / GHz / ns

Use these for microwave designs — no need to switch. For NIR/THz, switch
explicitly via the **canonical** `SetUnit` form (NOT the Python-only
`.Geometry` / `.Frequency` shorthands, which work via the Python proxy
but are inconsistent through `add_to_history`):

```vba
With Units
    .SetUnit "Length", "mm"
    .SetUnit "Frequency", "GHz"
    .SetUnit "Time", "ns"
    .SetUnit "Temperature", "K"
End With
```

`SetUnit "Length", ...` accepts `"nm"`, `"um"`, `"mm"`, `"cm"`, `"m"`,
`"mil"`, `"in"`, `"ft"`. Frequency unit accepts `"Hz" / "kHz" / "MHz" /
"GHz" / "THz" / "PHz"`.

### Order matters: Units BEFORE Parameters

`StoreParameter "a", "4.0905"` stores a numeric value evaluated in the
**current** units context. If you set units AFTER storing parameters, the
existing parameters DO NOT get reinterpreted. Set Units as Step 1 of
every build, BEFORE Step 2 (Parameters).

### Material idioms

`.TanD` / `.TanDGiven` / `.TanDModel` (the verbose cookbook form below)
**works** in CST 2026. `.Tandd` (lowercase second 'd', from the
patch_antenna_workflow example in ok-nc/cst_python) **does NOT** — raises
(10091).

`Material "PEC"` is a CST 2026 built-in. No explicit definition needed:

```vba
With Brick
    .Reset
    .Name "metal_trace"
    .Component "component1"
    .Material "PEC"
    .Xrange ..., ...
    .Create
End With
```

For lossy metals (Cu, Au, etc.), the `Type "Lossy metal" + Sigma` form
below works fine.

### Components: use the default `component1`

`new_mws()` ships with `component1` already defined. Use it directly in
`.Component "component1"` for all bricks. Don't `Component.New` custom
components unless you have a specific reason (multi-material clustering
for visualization), because every additional component is one more thing
the builder has to verify and one more potential silent-failure point.

### FDSolver property renames

These were the cookbook-era properties:
```vba
With FDSolver
    .SetMethod "Tetrahedral Mesh"      ' ❌ (10091) in CST 2026
    .SweepType "Auto"                  ' ❌ (10091) in CST 2026
    ...
End With
```

In CST 2026, use the simpler form:
```vba
ChangeSolverType "HF Frequency Domain"

With Mesh
    .MeshType "Tetrahedral"
End With
```

And trust the FDSolver defaults for sweep config — they're sensible.
For Mode 2 blocking solve from Python: `m3d.FDSolver.Start()`.

### Result-tree probes

These Python proxy calls **work** in CST 2026 (Mode 2 getters, no
`allow_history_commands()` needed):

```python
m3d.DoesParameterExist("a")            # → bool
m3d.Material.Exists("FR4")             # → bool   (note: Exists, NOT DoesExist)
m3d.Solid.DoesExist("component1:fr4")  # → bool   (note: DoesExist, NOT Exists)
                                       #         expects "component:name" form
```

The Material/Solid naming inconsistency is a CST API quirk — Material
uses `Exists`, Solid uses `DoesExist`. The `cst_helpers.verify_*_exists`
wrappers normalize this.

These do NOT work in CST 2026 (raise (10091)):
- `Solid.DoesExist` *as raw VBA via add_to_history* (the Mode 1 dispatch
  doesn't have this method, even though Mode 2 does)
- `Material.DoesExist` *as raw VBA*
- `Component.GetNumberOfComponents` (raw VBA)

### `get_messages()` encoding (Chinese / non-UTF-8 Windows)

`prj.get_messages()` can raise `UnicodeDecodeError: 'gbk' codec can't decode...`
on Chinese-Windows hosts because CST's localized message strings have
non-ASCII characters that Python's default codec can't read. Use the
safe wrapper:

```python
from nir.cst_helpers import get_messages_safe
msgs = get_messages_safe(prj)   # returns "" on decode failure rather than raising
```

### Don't use mid-script `m3d.Mesh.GetNumberOfMeshCells()` as a probe

The mesh is built **lazily** at solver-start, not at `add_to_history`
time. Calling `GetNumberOfMeshCells()` immediately after the geometry
step returns 0 on a perfectly-built model. False signal. Use the
HistoryBuilder's `expects_solids=...` check instead — that queries
existence, not mesh.

### Image-export VBA macros are all renamed in CST 2026

These all raise (10091) or "Not an object reference":
- `Plot.ExportPlot "<path>", "PNG"`
- `Plot.StoreImage "<path>"`
- `View.ExportImage "<path>", "PNG"`
- `ExportImage "<path>"`

The correct names in CST 2026 are unknown — programmatic 3D-view
screenshot is not feasible right now. Workarounds:
- Use `nir.geometry_<id>.render_top_view(design, out_png)` for a
  Python-side matplotlib render (no CST needed).
- Or open in CST GUI and manually export via File → Save Picture As.

---

## ✅ NEW patterns for CST 2026 builds

### Pre-flight render (catches wrong-topology bugs in 1 second)

Render the geometry from Python BEFORE running CST. If the render doesn't
match the seed paper's figure, the CST build will reproduce that wrong
topology silently after 30 minutes of solver time.

```python
from nir.geometry_elc import render_top_view
from nir.design_ELC import DESIGN

render_top_view(DESIGN, "preflight.png", unit_scale=1e-6, unit_label="mm")
# Open preflight.png and visually compare against the seed paper's figure.
# If they don't match, fix nir/geometry_<id>.py BEFORE opening CST.
```

The renderer uses a single source-of-truth brick spec (e.g. `ELC_BRICK_SPEC`
in `geometry_elc.py`) that the VBA emitter ALSO consumes. So change one
rectangle and both the PNG and the CST build update together — no risk
of the render and the build drifting out of sync.

### Single source-of-truth brick spec pattern

When writing a new `nir/geometry_<id>.py`:

```python
# Symbolic brick specification (strings, evaluated by CST at mesh time)
HYPOTHESIS_X_BRICK_SPEC = [
    ("name", "Material", "x_lo", "x_hi", "y_lo", "y_hi", "z_lo", "z_hi"),
    # ... one tuple per brick ...
]

def build_<x>_geometry_vba(params):
    """Emits VBA from the spec."""
    blocks = []
    for name, mat, x_lo, x_hi, y_lo, y_hi, z_lo, z_hi in HYPOTHESIS_X_BRICK_SPEC:
        blocks.append(f'''
With Brick
    .Reset
    .Name "{name}"
    .Component "component1"
    .Material "{mat}"
    .Xrange "{x_lo}", "{x_hi}"
    .Yrange "{y_lo}", "{y_hi}"
    .Zrange "{z_lo}", "{z_hi}"
    .Create
End With
'''.strip())
    return "\n\n".join(blocks)

def expected_solid_names():
    return [name for name, _, *_ in HYPOTHESIS_X_BRICK_SPEC]

def render_top_view(design, out_png, ...):
    """Numerically evaluates the spec against design + matplotlib renders."""
    # See geometry_elc.py for the full implementation pattern
```

### Flat-spectrum guard (last-line-of-defense after solve)

Even with HistoryBuilder, some silent failures can slip through (e.g., a
Floquet port failing to attach). Add this at the END of the export step:

```python
from nir.cst_helpers import assert_spectrum_nontrivial

# s11, s21 are complex numpy arrays from the cst.results exporter
assert_spectrum_nontrivial(s11, s21, threshold=0.02)
# Raises RuntimeError if both have std < threshold (flat = silent failure)
```

---

## ✅ Working: project skeleton

### Delete the default PEC box (template-copy pattern only)

> ⚠️ **CST 2026**: this step is OBSOLETE if you use `env.new_mws()`. The
> default `component1` is empty and harmless — don't delete it, USE it
> as `.Component "component1"` for all your bricks. Only delete if you
> previously copied a polluted template like `base_project.cst`.

```vba
Component.Delete "component1"
```

### Units, frequency, boundary, background

> ⚠️ **CST 2026**: the `.Geometry / .Frequency / .Time` shorthands below
> are Python-only convenience methods (per ok-nc/cst_python `04_setup/units.md`).
> They sometimes work via Mode 1 add_to_history, sometimes silently fail.
> Use the canonical `SetUnit` form instead:
>
> ```vba
> With Units
>     .SetUnit "Length", "nm"
>     .SetUnit "Frequency", "THz"
>     .SetUnit "Time", "fs"
> End With
> ```
>
> The historical snippet remains below for reference.

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

> ⚠️ **CST 2026**: `.SetCreator "High Frequency"` below is brittle — works
> sometimes, raises (10091) other times depending on context. Drop it and
> trust the defaults set by `ChangeSolverType`. Also: `FDSolver.SetMethod`
> and `FDSolver.SweepType` are GONE — see the errata section above.

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

> ⚠️ **CST 2026** alternative: `m3d.FDSolver.Start()` is a Mode 2 blocking
> call that returns when the solver finishes — no `is_solver_running()`
> polling loop needed. Cleaner for short solves (< 1 hour). Falls back to
> the start_solver / poll pattern if you need a hard timeout.

**Smoke-test (`--quick`) mode** (added in this revision): coarser mesh
(5 cells/wavelength instead of 10) ~halves solve time. NOT accurate
enough for converged peak position — meant for catching VBA / geometry
errors before launching a full agent loop.

---

## Pre-flight checklist before launching `nir/agent.py`

1. **Dry-run** the runner: `python -m nir.runner --hypothesis X --dry-run`
   — verifies imports, design dict, constraints. <1 s.
2. **NEW (CST 2026)**: **render** the geometry from Python with
   `nir.geometry_<X>.render_top_view(DESIGN, "preflight.png")`. Visually
   compare against the seed paper's figure. Catches wrong-topology bugs
   in 1 second, before any CST round-trip. Would have saved 4 build
   iterations (v6-v9) on the ELC 11 GHz project.
3. **Smoke-test** with full CST: `python -m nir.runner --hypothesis X --quick`
   — verifies all VBA history steps execute, solver completes, S-params
   exported, peak detected. ~30–60 s.
4. **Inspect** the smoke spectrum: open `nir/working_default_X/Absorptance.csv`
   in any plotter. Check that:
   - Peak amplitude is reasonable (>0.5 for an MIM absorber on resonance;
     <0.1 with no peak is a smell — see hypothesis C).
   - Peak frequency is within an order of magnitude of target.
   - Mode hops between adjacent frequency points indicate noise; smooth
     spectrum is healthy.
5. **Only then** launch the agent: `python -m nir.run_hypothesis_X --reset`.

This 30–60 s smoke-test would have saved ~30 min on hypothesis B's first
agent run (broken ExtrudeCurve geometry, abs=0.73, mode-hopping LLM).
Adding the Python pre-flight render (step 2) catches an even bigger
class of bugs even earlier — topology mismatches like the ELC v1-v9
"two C-loops" mistake that took 9 build iterations to discover visually.
