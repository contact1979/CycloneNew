#!/usr/bin/env bash
set -euo pipefail

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel

# Install runtime and dev dependencies
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
fi
if [[ -f dev-requirements.txt ]]; then
  pip install -r dev-requirements.txt
fi

# Install required dev tools for linting and testing
pip install --upgrade flake8 pylint pytest black
