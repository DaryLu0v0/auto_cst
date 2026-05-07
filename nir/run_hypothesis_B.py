"""nir/run_hypothesis_B.py -- entrypoint for the hypothesis-B run (elliptical disk MIM)."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
RUNS_ROOT = PROJECT_ROOT / "runs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run hypothesis B end-to-end")
    parser.add_argument("--max-iter", type=int, default=10)
    parser.add_argument("--target", type=float, default=193.41)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--model", type=str, default="gpt-4o")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--run-name", type=str, default=None)
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_name = args.run_name or timestamp
    run_dir = RUNS_ROOT / run_name / "hypothesis_B_ellipse"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Run directory: {run_dir}")

    cmd = [
        sys.executable, "-m", "nir.agent",
        "--hypothesis", "B",
        "--target", str(args.target),
        "--max-iter", str(args.max_iter),
        "--threshold", str(args.threshold),
        "--model", args.model,
        "--run-dir", str(run_dir),
    ]
    if args.reset:
        cmd.append("--reset")

    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=os.environ.copy())
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
