"""nir/cst_helpers.py -- thin wrappers around cst.interface and cst.results
that protect against the two silent footguns I hit during the auto_cst NIR runs:

  1. `cst.results.ProjectFile(...)` requires an ABSOLUTE path. With a relative
     path it returns a project handle whose run_id index is silently broken
     -- get_result_item raises "ResultItem does not exist for run id=N" even
     though the data is in the file.

  2. Parameter injection invalidates the empty-template default run_id=0
     results. The actual data lives at the highest run_id (1 after a single
     solve). cst.results.get_result_item(path) defaults to run_id=0 and
     silently returns nothing.

Use `open_results()` and `get_result_with_data()` everywhere instead of the
raw cst.results API, and these two issues disappear.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, List, Tuple

# CST library setup (callers are expected to have already added it; we add
# defensively to support standalone helper-module usage in scripts).
_CST_PYTHON_LIB = r"E:\cst\AMD64\python_cst_libraries"
if _CST_PYTHON_LIB not in sys.path:
    sys.path.insert(0, _CST_PYTHON_LIB)

import cst.results as cstres   # noqa: E402


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
    import re
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
