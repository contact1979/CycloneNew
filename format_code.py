"""Apply formatting and linting across the project."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List


def run_command(command: List[str], description: str) -> int:
    """Run a command and print its output."""
    print(f"\n{description}...", flush=True)
    result = subprocess.run(command)
    return result.returncode


def main() -> None:
    """Run formatting and linting tools."""
    project_dir = Path(__file__).parent
    directories = ["hydrobot", "tests", "scripts", "dashboard"]
    root_py_files = [f for f in os.listdir(project_dir) if f.endswith(".py")]

    black_result = run_command(["black", *directories, *root_py_files], "Running Black")
    isort_result = run_command(["isort", *directories, *root_py_files], "Running isort")
    flake8_result = run_command(
        ["flake8", *directories, *root_py_files], "Running flake8"
    )

    if black_result != 0 or isort_result != 0 or flake8_result != 0:
        print("\nWarning: Some formatting/linting checks failed.")
        sys.exit(1)

    print("\nAll formatting and linting checks completed successfully!")


if __name__ == "__main__":
    main()
