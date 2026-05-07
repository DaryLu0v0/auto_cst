"""nir/run_hypothesis_A.py -- entrypoint for the hypothesis-A LLM-in-loop run.

Creates a timestamped run directory under runs/, then invokes nir.agent.main
with the right --run-dir.

Usage:
    python -m nir.run_hypothesis_A
    python -m nir.run_hypothesis_A --max-iter 5  --reset
"""
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
    parser = argparse.ArgumentParser(description="Run hypothesis A end-to-end")
    parser.add_argument("--max-iter", type=int, default=15)
    parser.add_argument("--target", type=float, default=193.41)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--model", type=str, default="gpt-4o")
    parser.add_argument("--reset", action="store_true",
                        help="Reset nir/design_A.py to baseline before starting")
    parser.add_argument("--run-name", type=str, default=None,
                        help="Override the auto-generated run dir name")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_name = args.run_name or timestamp
    run_dir = RUNS_ROOT / run_name / "hypothesis_A_disk"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"Run directory: {run_dir}")

    cmd = [
        sys.executable, "-m", "nir.agent",
        "--hypothesis", "A",
        "--target", str(args.target),
        "--max-iter", str(args.max_iter),
        "--threshold", str(args.threshold),
        "--model", args.model,
        "--run-dir", str(run_dir),
    ]
    if args.reset:
        cmd.append("--reset")

    # Inherit env (OPENAI_API_KEY etc.)
    env = os.environ.copy()
    # If the user set the OpenAI key in CLAUDE.md but it's not in env,
    # the agent will fall back to the key it picks up from elsewhere.

    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    sys.exit(completed.returncode)


if __name__ == "__main__":
    main()
