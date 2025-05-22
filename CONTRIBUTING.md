# Contributing

Thank you for your interest in improving HydroBot.

## Development Workflow

1. Create a feature branch from `main`.
2. Ensure `pre-commit` hooks or `black`, `isort`, and `mypy` pass locally.
3. Add tests for any new functionality.
4. Submit a pull request describing your changes.

We follow the [PEP 8](https://peps.python.org/pep-0008/) style guide and use
`black` for formatting.

Run `format_code.py` before committing to ensure formatting and linting pass:

```bash
./format_code.py
```
