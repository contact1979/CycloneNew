# HydroBot v2

HydroBot is a research project for exploring automated trading strategies. It is distributed under the MIT license and provided for educational purposes only. Use it at your own risk.

## Features
* Modular architecture with strategies, trading utilities and data ingestion modules.
* Configuration via `config/config.yaml` with secrets in `secrets.yaml` or environment variables.
* Docker deployment with Redis and an optional PostgreSQL service.
* Test suite using `pytest`.

## Quickstart

### Prerequisites
* Python 3.11+
* `pip` for dependency management

### Local Run
```bash
pip install -r requirements.txt
python main.py
```

### Docker Compose
Build and run all services with:
```bash
docker-compose up --build
```
This starts HydroBot, Redis and PostgreSQL containers.

For running tests in Docker:
```bash
docker-compose -f docker-compose.tests.yml up --build
```

### Windows Setup
Use the provided PowerShell script to create a virtual environment and install packages:
```powershell
./setup.ps1
```

## Directory Structure
```
hydrobot/       # core package
config/         # configuration files
models/         # ML models and utilities
strategies/     # trading strategies
trading/        # order execution and portfolio management
utils/          # shared utilities
```

## License
MIT
