# HydroBot - Autonomous Crypto Trading Bot

## Introduction

HydroBot is a modular, cloud-ready cryptocurrency trading bot designed for autonomous, real-time trading. The initial focus (Phase 1) is on executing arbitrage strategies between Binance US and Kraken, with capabilities for technical analysis and a foundation for future machine learning integration.

This project aims to provide a robust, maintainable, and extensible platform for developing and deploying automated trading strategies. It is built with Python using asyncio for performance and designed for deployment on cloud platforms like Azure.

For detailed requirements and design decisions, please refer to the Product Requirements Document ([prd.md](prd.md)).

## Features (Phase 1)

- **Arbitrage Engine**: Detects and evaluates cross-exchange arbitrage opportunities (Binance US / Kraken)
- **Modular Strategy Framework**: Supports different strategy pipelines (Arbitrage only, Tech+Arb, ML+Arb)
- **Technical Analysis**: Calculates standard indicators (SMA, EMA, RSI, MACD, Volume Spikes) via pandas-ta
- **Exchange Integration**: Connects to Binance US and Kraken for market data and trade execution
- **Risk Management**: Implements configurable safety controls (max exposure, trade limits, latency thresholds)
- **Real-time Monitoring**: Streamlit dashboard for status monitoring and control
- **Backtesting**: Comprehensive backtesting engine with historical data support
- **Cloud-Ready**: Designed for deployment on Azure with containerization support

## Project Structure

```
├── .venv/                 <-- Python Virtual Environment
├── deploy/                <-- Deployment files (Kubernetes, Azure configs)
├── hydrobot/              <-- Main Python Package
│   ├── __init__.py
│   ├── config/           <-- Configuration loading
│   ├── data/             <-- Data clients, loading, technical indicators
│   ├── database/         <-- Database interaction (PostgreSQL)
│   ├── strategies/       <-- Strategy logic implementations
│   ├── trading/          <-- Trading execution, portfolio, risk management
│   ├── models/           <-- Machine learning models and features
│   ├── features/         <-- Feature engineering for ML models
│   ├── dashboard/        <-- Streamlit dashboard code
│   ├── scripts/          <-- Utility scripts (backtest, data collection)
│   └── utils/            <-- Shared utilities (logging, metrics)
├── data/                 <-- Historical and collected data
├── logs/                 <-- Application logs
├── tests/                <-- Test suite
├── .env                  <-- Local secrets (DO NOT COMMIT)
├── .gitignore           <-- Git ignore rules
├── CITATIONS.md         <-- Code attributions and references
├── prd.md              <-- Product Requirements Document
└── README.md           <-- This file
```

## Setup Instructions

1. **Clone the Repository**:

   ```bash
   git clone <your-repository-url>
   cd hydrobot
   ```

2. **Create Virtual Environment**:

   ```bash
   python -m venv .venv
   ```

3. **Activate Virtual Environment**:

   - On macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```
   - On Windows (Command Prompt):
     ```bash
     .\.venv\Scripts\activate.bat
     ```
   - On Windows (PowerShell):
     ```bash
     .\.venv\Scripts\Activate.ps1
     ```

4. **Install Dependencies**:

   ```bash
   pip install -r hydrobot/requirements.txt
   ```
   
   Note: Ensure you have necessary system dependencies for packages like psycopg2-binary if not using pre-compiled wheels.

## Configuration

The bot uses a combination of a YAML file for general settings and a .env file for secrets.

### Secrets (.env file)

1. Create a file named `.env` in the project root directory
2. Copy the contents of `hydrobot/config/.env.example` into your new `.env` file
3. Fill in your actual secret values:

   - API keys for Binance US/Kraken
   - PostgreSQL DATABASE_URL
   - Other sensitive configuration

IMPORTANT: Never commit your .env file to version control.

### General Settings (config.yaml)

- Location: `hydrobot/config/config.yaml`
- Contains non-secret settings like:
  - Strategy parameters
  - Risk thresholds
  - Indicator periods
  - File paths
- Modify according to the structure in `hydrobot/config/settings.py`

## Usage Examples

Make sure your virtual environment is activated before running these commands.

```bash
# Run Data Collection (Backfill)
python -m hydrobot.scripts.run_data_collection --mode backfill --days 7 --interval 5m

# Run Data Collection (Continuous)
python -m hydrobot.scripts.run_data_collection --mode continuous --interval 1m

# Run Backtest
python -m hydrobot.scripts.run_backtest --symbols BTC/USDT --start-date 2024-01-01

# Run the Streamlit Dashboard
streamlit run hydrobot/dashboard/app.py
```

## Contributing

Please see our [Contributing Guide](CONTRIBUTING.md) for details on how to:

- Set up your development environment
- Run tests
- Submit pull requests
- Follow coding standards

## Citations & Attributions

This project builds upon various open-source components and libraries. For detailed attribution and licensing information, please see [CITATIONS.md](CITATIONS.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This Crypto Arbitrage Bot is for educational and research purposes only. Cryptocurrency trading carries a high level of risk, and may not be suitable for all investors. Before deciding to trade cryptocurrency, you should carefully consider your investment objectives, level of experience, and risk appetite. The possibility exists that you could sustain a loss of some or all of your initial investment and therefore you should not invest money that you cannot afford to lose. You should be aware of all the risks associated with cryptocurrency trading, and seek advice from an independent financial advisor if you have any doubts.