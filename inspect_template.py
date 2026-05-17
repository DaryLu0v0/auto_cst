"""Inspect what's actually inside D:/Claude/auto_cst/templates/base_project.cst:
  - Pre-existing parameters (the param list seen in the GUI Parameter List tab)
  - Pre-existing components / materials
  - Pre-existing history steps
  - Pre-existing units

This is the read-only sister of build_elc_11ghz.py -- never modifies the file.
"""
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, r"E:\cst\AMD64\python_cst_libraries")
import cst.interface as cstint

TEMPLATE = Path("D:/Claude/auto_cst/templates/base_project.cst")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# Copy to a temp dir so the original is never touched.
with tempfile.TemporaryDirectory() as td:
    tmp_cst = Path(td) / "probe.cst"
    shutil.copy2(TEMPLATE, tmp_cst)

    env = cstint.DesignEnvironment()
    proj = env.open_project(str(tmp_cst.resolve()))
    m3d = proj.model3d

    # ----- 1. Parameters -----
    section("Parameters defined in the template")
    # Use the documented API: get_all_parameters_as_string? get_parameter_names?
    try:
        for name in dir(m3d):
            if "Parameter" in name and not name.startswith("_"):
                print(f"  candidate API: m3d.{name}")
    except Exception:
        pass

    # Try a few specific methods.
    for method_name in ("get_all_parameter_names", "get_parameter_names",
                        "get_parameters", "list_parameters"):
        try:
            fn = getattr(m3d, method_name)
            result = fn()
            print(f"  {method_name}() -> {result}")
        except Exception as e:
            pass

    # The Schematic / 3D parameter list is exposed as m3d.GetParameterNNNN VBA --
    # let's probe via DoesParameterExist for common names.
    section("DoesParameterExist probe for common template names")
    candidates = ["p", "st", "t_m", "t_metal", "theta", "phi",
                  "p1s", "sp1", "p2s", "sp2", "p3s", "sp3",
                  "outer_srr", "w", "gap", "length_arm",
                  "a", "d", "l", "g", "h_FR4", "t_Cu"]
    for n in candidates:
        try:
            exists = m3d.DoesParameterExist(n)
            if exists:
                print(f"  {n}: EXISTS")
            else:
                pass  # only show those that exist
        except Exception:
            pass

    # ----- 2. Try to read the history list as a string -----
    section("History list (raw)")
    for accessor in ("get_history_list_as_string",
                     "get_history_list",
                     "GetHistoryListAsString",
                     "list_history_items"):
        try:
            fn = getattr(m3d, accessor)
            result = fn()
            print(f"  {accessor}() = ")
            if isinstance(result, str):
                print(result[:4000])
            else:
                print(repr(result)[:4000])
            break
        except (AttributeError, TypeError):
            continue
        except Exception as e:
            print(f"  {accessor}() raised: {e}")

    # ----- 3. Probe units via a Python expression after asking CST -----
    # CST's VBA `Units.GetGeometryUnit` returns the current unit string.
    section("Current units (via macro echo to a temp file)")
    probe_out = Path(td) / "units_probe.txt"
    units_probe_vba = f'''
Dim sUnit As String
sUnit = Units.GetGeometryUnit
Open "{probe_out.as_posix()}" For Output As #1
Print #1, "geometry=" & sUnit
sUnit = Units.GetFrequencyUnit
Print #1, "frequency=" & sUnit
sUnit = Units.GetTimeUnit
Print #1, "time=" & sUnit
Close #1
'''
    try:
        m3d.add_to_history("units_probe", units_probe_vba)
        if probe_out.exists():
            print(probe_out.read_text())
        else:
            print("  probe file not written -- VBA may have failed silently")
    except Exception as e:
        print(f"  units probe VBA raised: {e}")

    # ----- 4. Try to dump component / material lists via VBA echo too -----
    section("Components + materials (via VBA echo)")
    list_out = Path(td) / "list_probe.txt"
    list_probe_vba = f'''
Open "{list_out.as_posix()}" For Output As #1
Print #1, "--- components ---"
Dim i As Integer
For i = 0 To Component.GetNumberOfComponents - 1
    Print #1, "  " & Component.GetNameByIndex(i)
Next
Print #1, "--- materials ---"
For i = 0 To Material.GetNumberOfMaterials - 1
    Print #1, "  " & Material.GetNameByIndex(i)
Next
Close #1
'''
    try:
        m3d.add_to_history("list_probe", list_probe_vba)
        if list_out.exists():
            print(list_out.read_text())
        else:
            print("  probe file not written -- VBA may have failed silently")
    except Exception as e:
        print(f"  list probe VBA raised: {e}")

    proj.close()
    env.close()

print()
print("Inspection complete.")
