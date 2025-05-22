#!/usr/bin/env python3
"""Apply formatting and linting across the project.

This script runs ``black`` followed by ``flake8`` on the repository
root. Run it before committing changes to ensure consistent style and
linting.
"""
from __future__ import annotations

import subprocess
import sys
from typing import List


def run_command(cmd: List[str]) -> None:
    """Run a command and exit if it fails.

    Args:
        cmd: Command and arguments to execute.
    """
    print(f"Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    """Format the codebase and run lint checks."""
    run_command([sys.executable, "-m", "black", "."])
    run_command([sys.executable, "-m", "flake8", "."])


if __name__ == "__main__":
    main()
