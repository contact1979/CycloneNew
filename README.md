# HydroBot v2

[![Build Status](https://github.com/user/repo/actions/workflows/test.yml/badge.svg)](https://github.com/user/repo/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/user/repo/branch/main/graph/badge.svg?token=TOKEN)](https://codecov.io/gh/user/repo)

[![PyPI](https://img.shields.io/pypi/v/hft-scalping-bot.svg)](https://pypi.org/project/hft-scalping-bot/)
HydroBot is a research project for exploring automated trading strategies. It is
distributed under the MIT license and provided for educational purposes only.
Use it at your own risk.

The bot focuses on a simple scalping strategy with tight risk controls. It aims
to capture small price movements while capping drawdowns through strict stop
loss and position sizing rules.
## Strategy Overview and Risk Management
HydroBot uses a scalping strategy focused on high-frequency entries and exits.
Signals are generated from order book imbalance and short-term momentum.
Risk management enforces stop-loss and take-profit targets along with a
maximum account drawdown percentage. Position sizing is capped by the
`max_risk_per_trade_pct` setting.


## Features

- Modular architecture with strategies, trading utilities and data ingestion modules.
- Configuration via `config/config.yaml` with secrets in `secrets.yaml` or environment variables.
- Docker deployment with Redis and an optional PostgreSQL service.
- Test suite using `pytest`.

## Quickstart

### Prerequisites

- Python 3.11+
- `pip` for dependency management

### Local Run

```bash
./setup.sh
python main.py
```

### Docker Compose

Build and run all services with:

```bash
docker-compose up --build
```

This starts HydroBot, Redis and PostgreSQL containers.
The compose file mounts `./logs` and `./data` as volumes so logs and market
data persist across runs.

For database persistence you can mount a volume for PostgreSQL as shown in `docker-compose.yml`.

For running tests in Docker:

```bash
docker-compose -f docker-compose.tests.yml up --build
```

### Example Configuration
Sample configuration files are provided as `sample_config.yaml` and
`sample_secrets.yaml`. Copy them to `config.yaml` and `secrets.yaml` and fill in
your values. Secrets such as API keys can also be supplied via environment
variables (`EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`).

> **Security Note**: `secrets.yaml` is listed in `.gitignore` to avoid accidental commits.
> For production deployments provide sensitive values through environment variables.

```yaml
exchange:
  name: binanceus
  is_sandbox: true
trading:
  symbols: ["BTC/USDT"]
  default_trade_amount_usd: 15.0
```

### Usage Example
```bash
python main.py --config config.yaml
```

### Windows Setup

Use the provided PowerShell script to create a virtual environment and install packages:

```powershell
./setup.ps1
```

### Code Formatting
Run the helper script to format and lint the codebase:

```bash
./format_code.py
```

`black` and `flake8` must be installed. They are listed in
`dev-requirements.txt`.

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
