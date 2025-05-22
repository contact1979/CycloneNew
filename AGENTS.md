# CycloneNew Contributor Guide

Welcome! This guide explains how to develop, test, and contribute to CycloneNew.

## Setup
- Ensure Python 3.8+ is installed.
- Create and activate a virtual environment:
  ```
  python3 -m venv .venv
  source .venv/bin/activate
  ```
- Install dependencies:
  ```
  pip install -r requirements.txt
  pip install -r dev-requirements.txt
  ```

## Development Workflow
- All code resides in `cyclone/`.
- Tests are in `tests/`.
- Configuration files are in `config/` or the project root.

## Lint and Format
- Format code:  
  `black .`
- Lint code:  
  `flake8 .`
- Static analysis:  
  `pylint cyclone/`

## Testing
- Run all tests:  
  `pytest`
- Add or update tests when changing code.
- All tests must pass before merging.

## Pull Requests & CI
- All PRs must:
  - Pass linting (`flake8`)
  - Pass formatting check (`black --check .`)
  - Pass all tests (`pytest`)
- Use descriptive PR titles:  
  `[CycloneNew] <Short Description>`
- Reference any related issues in the PR description.

## Documentation
- Add or update docstrings for all public functions and classes.
- Update README.md if you change setup, usage, or config instructions.

## Additional Tips
- Use pre-commit hooks if available:
  ```
  pre-commit install
  ```
- If you add external dependencies, update requirements files.
- Ask questions or propose improvements via GitHub Issues or PRs.

Thank you for contributing to CycloneNew!
