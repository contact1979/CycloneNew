#!/usr/bin/env python3
<<<<<<< HEAD
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
=======
"""
Script to format and lint the codebase.
This handles running black, flake8, and isort on the codebase.
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """Run a command and print its output."""
    print(f"\n{description}...")
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        print(result.stdout)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(e.stdout)
        print(e.stderr)
        return e.returncode


def main():
    """Run formatting and linting tools."""
    # Get the project root directory
    project_dir = Path(__file__).parent

    # Directories to format
    directories = ["hydrobot", "tests", "scripts", "dashboard"]

    # Add individual Python files at the root
    root_py_files = [f for f in os.listdir(project_dir) if f.endswith(".py")]

    # Run Black
    black_args = ["black"] + directories + root_py_files
    black_result = run_command(black_args, "Running Black code formatter")

    # Run isort
    isort_args = ["isort"] + directories + root_py_files
    isort_result = run_command(isort_args, "Running isort import sorter")

    # Run flake8
    flake8_args = ["flake8"] + directories + root_py_files
    flake8_result = run_command(flake8_args, "Running flake8 linter")

    # Exit with error code if any of the tools failed
    if black_result != 0 or isort_result != 0 or flake8_result != 0:
        print("\nWarning: Some formatting/linting checks failed.")
        sys.exit(1)

    print("\nAll formatting and linting checks completed successfully!")
>>>>>>> 2ee8954 (WIP: Stage all local changes before rebase to resolve branch divergence and enable push. Includes linting, code quality, and other local modifications.)


if __name__ == "__main__":
    main()
