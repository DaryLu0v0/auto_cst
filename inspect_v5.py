"""Forensic inspection of elc_11ghz_v5.cst after the failed v5 build.

Read-only, retries on lock contention from any lingering CST instance.
"""
import sys, tempfile, time
from pathlib import Path
sys.path.insert(0, r"E:\cst\AMD64\python_cst_libraries")
import cst.interface as cstint

TARGET = Path(r"D:\Claude\MetaClaw\runs\elc_11ghz\Experiment\cst_design\elc_11ghz_v5.cst")


def open_with_retry(path: Path, attempts: int = 5):
    env = cstint.DesignEnvironment()
    last_err = None
    for i in range(attempts):
        try:
            proj = env.open_project(str(path.resolve()))
            return env, proj
        except Exception as e:
            last_err = e
            print(f"  attempt {i+1}: {e}")
            time.sleep(3)
    raise RuntimeError(f"could not open after {attempts} retries: {last_err}")


env, proj = open_with_retry(TARGET)
m3d = proj.model3d

# --------------------------------------------------------------------------
# A: ELC parameters (the things my v5 should have stored)
# --------------------------------------------------------------------------
print("=== ELC parameters ===")
elc_params = ("a", "d", "l", "w", "g", "h_FR4", "t_Cu", "air_extent")
for name in elc_params:
    exists = m3d.DoesParameterExist(name)
    print(f"  {name}: {'EXISTS' if exists else 'missing'}")

# --------------------------------------------------------------------------
# B: Stale template params (should all be MISSING since we used new_mws)
# --------------------------------------------------------------------------
print()
print("=== Stale template params (should all be missing) ===")
for name in ("p", "st", "t_m", "outer_srr", "gap", "length_arm"):
    exists = m3d.DoesParameterExist(name)
    print(f"  {name}: {'EXISTS (bad)' if exists else 'missing (good)'}")

# --------------------------------------------------------------------------
# C: Read each ELC parameter's value via VBA echo + verify units
# --------------------------------------------------------------------------
print()
print("=== Parameter values + units (via VBA echo) ===")
with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "v.txt"
    out_str = out.as_posix()
    vba = f'''
Open "{out_str}" For Output As #1
Print #1, "geometry_unit=" & Units.GetGeometryUnit
Print #1, "frequency_unit=" & Units.GetFrequencyUnit
Print #1, "time_unit=" & Units.GetTimeUnit
Print #1, ""
'''
    # CST evaluates parameter names as expressions directly -- "a" in a VBA
    # context is the numeric value of the stored parameter `a`.
    for name in elc_params:
        vba += f'Print #1, "{name}=" & {name}\n'
    vba += 'Close #1\n'
    try:
        m3d.add_to_history("probe_values", vba)
    except Exception as e:
        print(f"  VBA probe raised: {e}")
    if out.exists():
        print(out.read_text())
    else:
        print("  (probe output file missing -- VBA may have failed)")

# --------------------------------------------------------------------------
# D: Read messages from CST -- this is where silent VBA errors are logged
# --------------------------------------------------------------------------
print()
print("=== CST messages (errors / warnings from history execution) ===")
try:
    msgs = proj.get_messages()
    if isinstance(msgs, list):
        for m in msgs[:50]:
            print(f"  {m}")
    else:
        print(repr(msgs)[:4000])
except Exception as e:
    print(f"  get_messages failed: {e}")

# --------------------------------------------------------------------------
# E: Discard (no save -- we don't want to pollute v5 further)
# --------------------------------------------------------------------------
proj.close()
env.close()
print()
print("Inspection complete.")
