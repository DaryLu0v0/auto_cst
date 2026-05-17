"""nir/cst_helpers.py -- thin wrappers around cst.interface and cst.results
that protect against the silent footguns we hit during the auto_cst NIR + ELC runs.

Two layers:

A. RESULT-READ HELPERS (open_results, get_result_with_data, find_reflection_sparams)
   These wrap cst.results and fix two silent footguns:
     1. cst.results.ProjectFile requires an ABSOLUTE path. Relative paths give
        you a project handle whose run_id index is silently broken --
        get_result_item raises "ResultItem does not exist for run id=N" even
        though the data is in the file.
     2. Parameter injection invalidates the empty-template's run_id=0 results.
        The actual data lives at run_id >= 1. cst.results.get_result_item(path)
        defaults to run_id=0 and silently returns nothing.

B. BUILD-SIDE HELPERS (save_project_at, HistoryBuilder, verify_solid_exists,
   verify_material_exists, get_messages_safe, assert_spectrum_nontrivial)
   These wrap cst.interface and fix the "layered silent-failure" pattern in
   add_to_history (see feedback_cst_2026_vba memory). The HistoryBuilder
   verifies side effects after each VBA step, so failures localize cleanly
   to the offending step.

Use the helpers everywhere instead of raw cst.results / cst.interface, and
these issues disappear.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# CST library setup (callers are expected to have already added it; we add
# defensively to support standalone helper-module usage in scripts).
_CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if _CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, _CST_PYTHON_LIB)

import cst.results as cstres   # noqa: E402


# ===========================================================================
# A. Result-read helpers (post-solve)
# ===========================================================================

def open_results(working_cst: str | Path,
                 *, allow_interactive: bool = True
                 ) -> Tuple[Any, List[int]]:
    """Open a CST project's result database safely.

    Returns (proj3d, run_ids) where:
      - proj3d is the result-tree handle (use with get_result_with_data)
      - run_ids is the list of run_ids that exist for this project,
        sorted ascending (newest is run_ids[-1])

    Always pass an ABSOLUTE path -- this is the silent-footgun fix.
    """
    abs_path = str(Path(working_cst).resolve())
    proj = cstres.ProjectFile(abs_path, allow_interactive=allow_interactive)
    proj3d = proj.get_3d()
    try:
        run_ids = sorted(proj3d.get_all_run_ids())
    except Exception:
        run_ids = [0]
    if not run_ids:
        run_ids = [0]
    return proj3d, run_ids


def get_result_with_data(proj3d: Any,
                         item_path: str,
                         run_ids: Iterable[int]
                         ) -> Tuple[Any, int]:
    """Return (result_item, run_id_used) for the first run_id that has data.

    Tries highest run_id first (latest solve), falls back to no-arg call
    if all explicit run_ids fail. Raises RuntimeError if no run_id has data.
    """
    last_exc: Exception | None = None
    for rid in sorted(run_ids, reverse=True):
        try:
            ri = proj3d.get_result_item(item_path, rid)
            xdata = ri.get_xdata()
            if xdata is not None and len(xdata) > 0:
                return ri, rid
        except Exception as exc:
            last_exc = exc
            continue
    # Final fallback: no explicit run_id (uses CST default = 0)
    try:
        ri = proj3d.get_result_item(item_path)
        xdata = ri.get_xdata()
        if xdata is not None and len(xdata) > 0:
            return ri, -1   # -1 means "no run_id specified"
    except Exception as exc:
        last_exc = exc
    raise RuntimeError(
        f"no run_id has data for {item_path}; last error: {last_exc}"
    )


def find_reflection_sparams(tree_items: Iterable[str], sep: str = "\\") -> List[str]:
    """Return the diagonal Zmax(i)->Zmax(i) reflection S-params from a CST tree.

    The TD solver typically exposes all 16 (Zmax/Zmin x port1/port2 cross-pairs);
    the FD solver may only expose 4 (only the excited port). This matcher
    accepts whichever Zmax(i),Zmax(i) appears -- the reflection coefficient
    we need for Absorptance = 1 - |S11|^2.
    """
    out = []
    for item in tree_items:
        parts = item.split(sep)
        if len(parts) < 3:
            continue
        if parts[0] != "1D Results" or parts[1] != "S-Parameters":
            continue
        label = parts[-1]
        if re.search(r"Zmax\((\d+)\),Zmax\(\1\)", label) or label == "S1,1":
            out.append(item)
    return out


# ===========================================================================
# B. Build-side helpers (live CST project, pre-solve)
# ===========================================================================

def save_project_at(prj: Any, target_path: str | Path) -> None:
    """Save the current CST project to target_path using Mode 3 VBA (no history).

    CRITICAL: do not use m3d.add_to_history with a SaveAs VBA step. CST replays
    every history step on project open, and on open the .cst is already locked
    by CST itself -- the SaveAs would try to overwrite the open file and fail
    with "History Error: Saving of <path> failed (&H8000ffff)". Mode 3 runs the
    VBA exactly once and leaves no history trace.

    See feedback_cst_2026_vba memory for the discovery story.
    """
    save_path = str(Path(target_path).resolve()).replace("\\", "/")
    prj.schematic.execute_vba_code(
        f'Sub Main\n    SaveAs "{save_path}", "True"\nEnd Sub\n'
    )


def get_messages_safe(prj: Any) -> str:
    """Return CST's message-window contents with safe Unicode decoding.

    Plain prj.get_messages() raises UnicodeDecodeError on hosts where the
    default Python codec is GBK (Chinese Windows) or similar non-UTF-8 codecs,
    because CST's messages may contain extended characters. We catch the
    error and return an empty string rather than crashing the diagnostic.
    """
    try:
        return prj.get_messages()
    except UnicodeDecodeError:
        return ""
    except Exception:
        return ""


def _run_mode3_with_echo(prj: Any, vba_body: str) -> List[str]:
    """Run a Mode 3 VBA Sub that writes to a tempfile; return the file lines.

    vba_body is inserted between `Open <path> For Output As #1` and `Close #1`,
    so it should contain `Print #1, ...` statements. The tempfile is read with
    encoding='utf-8' errors='replace' and unlinked before return.
    """
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt",
                                     encoding="utf-8") as f:
        out_path = f.name
    out_path_vba = out_path.replace("\\", "/")
    full_vba = (
        f'Sub Main\n'
        f'Open "{out_path_vba}" For Output As #1\n'
        f'{vba_body}\n'
        f'Close #1\n'
        f'End Sub\n'
    )
    try:
        prj.schematic.execute_vba_code(full_vba)
        content = Path(out_path).read_text(encoding="utf-8", errors="replace")
        return content.splitlines()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def verify_solids_exist(m3d: Any,
                        names: Sequence[str],
                        *,
                        default_component: str = "component1") -> Dict[str, bool]:
    """Check whether each named solid exists. Returns dict {name: bool}.

    Uses Mode 2 Python proxy `m3d.Solid.DoesExist(...)` -- a direct getter that
    doesn't go through history. Expects the full `component:name` form; if no
    ':' is present in the input name, we auto-prefix with `default_component`
    (which is "component1" for our new_mws() builds).

    Discovered via probing: `m3d.Solid` has a `DoesExist` method (yes, despite
    earlier diagnostic flags), but `Solid.DoesExist` as raw VBA via
    add_to_history raises (10091). The Python proxy works because cst.interface
    handles the binding differently than CST's VBA engine.
    """
    result: Dict[str, bool] = {}
    for name in names:
        full = name if ":" in name else f"{default_component}:{name}"
        try:
            result[name] = bool(m3d.Solid.DoesExist(full))
        except Exception:
            result[name] = False
    return result


def verify_materials_exist(m3d: Any, names: Sequence[str]) -> Dict[str, bool]:
    """Check whether each named material is defined. Returns dict {name: bool}.

    Uses Mode 2 Python proxy `m3d.Material.Exists(...)` -- direct getter.

    Note the proxy method name: it's `Material.Exists` (not `Material.DoesExist`
    like Solid uses). This is a CST API quirk -- the two objects' query
    methods have inconsistent names. Don't confuse them.
    """
    result: Dict[str, bool] = {}
    for name in names:
        try:
            result[name] = bool(m3d.Material.Exists(name))
        except Exception:
            result[name] = False
    return result


def assert_spectrum_nontrivial(s11, s21, *, threshold: float = 0.02) -> None:
    """Raise RuntimeError if |S11| and |S21| are both essentially constant.

    For a real metamaterial resonance we expect at least one of the S-params to
    have std > threshold across the sweep. If both are flat, the solver
    completed but the geometry didn't build (silent VBA failure that even the
    HistoryBuilder missed -- e.g., a port failed to attach so the solver ran
    on a domain with no excitation).

    Call this at the END of a build pipeline, after the export step, as a
    safety net.
    """
    import numpy as np
    s11_var = float(np.std(np.abs(s11)))
    s21_var = float(np.std(np.abs(s21)))
    if s11_var < threshold and s21_var < threshold:
        raise RuntimeError(
            f"Spectrum is flat: std|S11|={s11_var:.4f}, std|S21|={s21_var:.4f}, "
            f"both < threshold {threshold}. The solver completed but the "
            f"geometry didn't produce a meaningful resonance. Almost always "
            f"a silent VBA failure -- inspect the CST history list manually."
        )


class HistoryBuilder:
    """Wraps m3d.add_to_history with verified side effects.

    The auto_cst codebase originally used add_to_history naively:

        m3d.add_to_history(label, vba)

    But CST 2026's add_to_history only RAISES on property-existence errors
    (.SomeNonexistentMethod). Value-resolution errors -- undefined material
    name in a brick, missing component, etc. -- silently fail. The brick
    doesn't get created, no Python exception, no log line. The next solver
    run completes in 10 seconds on an empty domain and produces no S-params.

    HistoryBuilder.add() verifies the expected side effects after each VBA
    step. If the step says "this creates solid 'fr4'", we Mode 3-query the
    project to confirm 'fr4' exists. On mismatch, RuntimeError with the
    step label + missing artifact.

    Usage:
        builder = HistoryBuilder(prj)
        builder.add("Step 1: Units", VBA_UNITS)
        builder.add("Step 2: Parameters", vba_params,
                    expects_parameters=["a", "d", "l", "w", "g"])
        builder.add("Step 6: FR4 material", VBA_FR4,
                    expects_materials=["FR4"])
        builder.add("Step 7: ELC geometry", vba_geom,
                    expects_solids=["fr4", "frame_top", "frame_bottom",
                                    "frame_left", "frame_right",
                                    "top_spine", "top_plate",
                                    "bottom_spine", "bottom_plate"])
        builder.add("Step 8: Floquet ports", VBA_PORTS)

    Verification overhead: ~100 ms per step (one Mode 3 round-trip).
    Negligible vs the solver time, and saves hours of post-hoc debugging.
    """

    def __init__(self, prj: Any, *, verify: bool = True):
        """
        Args:
            prj: a Project object (env.new_mws() or env.open_project(...))
            verify: if False, the builder is a no-op pass-through (just calls
                    m3d.add_to_history without side-effect checks). Useful for
                    debugging the wrapper itself or for known-good builds.
        """
        self.prj = prj
        self.m3d = prj.model3d
        self.verify = verify
        self.steps: List[Tuple[int, str]] = []

    def add(self,
            label: str,
            vba: str,
            *,
            expects_parameters: Optional[Sequence[str]] = None,
            expects_materials: Optional[Sequence[str]] = None,
            expects_solids: Optional[Sequence[str]] = None,
            ) -> None:
        """Add a VBA history step and verify its side effects.

        Raises RuntimeError on failure with the step label + the specific
        missing artifact.
        """
        step_idx = len(self.steps) + 1

        # 1. Run add_to_history. Catches property-existence VBA errors.
        try:
            self.m3d.add_to_history(label, vba)
        except Exception as e:
            raise RuntimeError(
                f"[step {step_idx}: {label}] add_to_history raised:\n  {e}"
            ) from e
        self.steps.append((step_idx, label))

        if not self.verify:
            return

        # 2. Verify expected parameters via DoesParameterExist (works in CST 2026).
        if expects_parameters:
            missing = [
                p for p in expects_parameters
                if not self.m3d.DoesParameterExist(p)
            ]
            if missing:
                raise RuntimeError(
                    f"[step {step_idx}: {label}] expected parameters missing "
                    f"after VBA: {missing}. The VBA returned success but "
                    f"StoreParameter / StoreDoubleParameter failed silently. "
                    f"Check the VBA syntax (StoreParameter expects "
                    f"`StoreParameter \"name\", \"value\"`)."
                )

        # 3. Verify expected materials via m3d.Material.Exists proxy.
        if expects_materials:
            mat_status = verify_materials_exist(self.m3d, expects_materials)
            missing = [m for m, ok in mat_status.items() if not ok]
            if missing:
                raise RuntimeError(
                    f"[step {step_idx}: {label}] expected materials missing "
                    f"after VBA: {missing}. The Material .Create returned "
                    f"success but the material isn't defined. Common causes: "
                    f"deprecated property name (.Tandd vs .TanD), unsupported "
                    f".Type value, or .Create not actually reached."
                )

        # 4. Verify expected solids via m3d.Solid.DoesExist proxy.
        if expects_solids:
            solid_status = verify_solids_exist(self.m3d, expects_solids)
            missing = [s for s, ok in solid_status.items() if not ok]
            if missing:
                raise RuntimeError(
                    f"[step {step_idx}: {label}] expected solids missing "
                    f"after VBA: {missing}. The Brick .Create returned success "
                    f"but the bricks weren't actually created. Most common "
                    f"causes: undefined material name (e.g. .Material \"PEC\" "
                    f"on a system without PEC pre-defined), undefined "
                    f"component (use .Component \"component1\" as the default), "
                    f"or zero-volume brick (check Xrange/Yrange/Zrange "
                    f"expressions resolve to a non-degenerate box)."
                )

    def summary(self) -> str:
        """Return a one-line-per-step summary of what was added."""
        return "\n".join(
            f"  [{idx:2}] {lbl}" for idx, lbl in self.steps
        )
