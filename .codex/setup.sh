#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip

if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
fi
