# HydroBot – Product Requirements Document (Autonomous Crypto Trading System)

**Version:** 2.2 (Merged Detailed Requirements)  
**Date:** 2025-04-22  
**Status:** Final

---

## 1. Introduction

### 1.1 Purpose

HydroBot is an autonomous, cloud-native cryptocurrency trading bot designed for real-time execution of high-frequency trading (HFT) strategies, including arbitrage and scalping. Built with extensibility in mind, HydroBot integrates technical indicators, optional machine learning models for market regime detection and price prediction, and robust safety/risk controls. The system is deployed on **Microsoft Azure** using containerized services and aims to generate consistent returns through automated decision-making and rapid execution.

### 1.2 Scope

This document defines the full set of features for HydroBot's initial release (Phase 1) and planned extensions. It incorporates existing codebase capabilities with architectural goals for full-scale deployment.

**In-Scope (Phase 1 + Planned Enhancements):**

- Arbitrage and scalping engines
- Strategy pipeline supporting configurable execution logic (Arbitrage → Indicators → ML)
- Modular ML framework for future integration of regime/prediction models
- Real-time and historical market data ingestion (WebSockets/REST)
- Risk management and safety checks
- Simulated and live trading modes
- Centralized configuration (config.yaml, .env, Azure Key Vault)
- Persistent data storage (PostgreSQL)
- Dash dashboard with live monitoring and controls
- Azure cloud-native deployment (Docker + AKS + Azure Monitor)

**Out of Scope (Future Considerations):**

- On-chain/DeFi trading integrations
- Margin trading, leverage, or short-selling
- Fully integrated sentiment analysis in trading signals (model and UI planned)
- Advanced dashboard analytics (multi-timeframe views, replay, ML overlays)
- Full CI/CD automation (to be integrated with Azure DevOps or GitHub Actions)

---

## 2. Goals

- **Autonomous Trading**: Execute trades based on real-time and historical data, predefined strategies, and dynamic market conditions.
- **Profitability**: Optimize for consistent net positive returns, especially during microstructure inefficiencies.
- **Scalability**: Handle increasing trading pairs, exchanges, and ML model complexity.
- **Extensibility**: Allow easy plug-in of new strategies, features, and ML modules.
- **Reliability**: Maintain high uptime and graceful recovery with Azure-native tooling.
- **Safety**: Enforce hard risk constraints to protect capital and avoid catastrophic failures.
- **Observability**: Expose logs and performance metrics through Prometheus and Azure Monitor.

---

## 3. Use Cases / User Stories

### As the Bot Operator, I want to:

- Configure bot settings (API keys via Key Vault/.env, strategy parameters, risk limits, feature toggles) centrally via config.yaml.
- Run the bot in live trading mode reliably on Azure Kubernetes Service (AKS).
- Run the bot in simulated (paper) trading mode using live or historical data.
- Backtest strategies on historical data with real conditions.
- View bot status, opportunities, balances, PnL, logs, and charts via the Dash dashboard.
- Analyze slippage and win/loss streaks.
- Switch between strategy modes and enable/disable ML layer via config.
- Trigger a panic shutdown via dashboard or CLI.
- Collect historical market data with scripts.
- Deploy updates manually (future CI/CD planned).

### As the Bot (System), I need to:

- Connect securely to Binance US and Kraken via API.
- Ingest real-time order books/trades via WebSocket and historical data via REST.
- Calculate indicators if enabled.
- Identify profitable opportunities based on strategy.
- Validate signals using profitability and risk rules.
- Execute paired/scalping orders via asyncio.gather with IOC/FOK.
- Manage order lifecycles and cancel second leg if needed.
- Track positions, balances, and PnL.
- Enforce safety rules: drawdown, exposure, latency, timeout, cooldowns.
- Log all actions, store in PostgreSQL, expose Prometheus metrics.
- Use ML models (if enabled) to refine decisions.

---

## 4. Features & Requirements

### 4.1 Functional Requirements

| Feature | Description | Priority |
|--------|-------------|----------|
| Strategy Pipeline | Arbitrage and scalping with optional indicator/ML filtering | Must |
| Exchange Integration | Binance US & Kraken API support (REST/WebSocket) | Must |
| Order Execution | Asynchronous, concurrent FOK/IOC trading logic with fallback | Must |
| Technical Indicators | RSI, SMA, MACD, Volume Z-score spikes | Should |
| Machine Learning Layer | Optional predictive models (LightGBM, regime classifier) | Should |
| Risk Control | Exposure limits, latency filters, drawdown thresholds, stop-loss, panic shutdown | Must |
| Simulated Trading | Paper trading support for full test loop | Must |
| Live Trading | Toggle switch with real fund execution | Must |
| Configuration | Centralized YAML/.env config with Azure Key Vault integration | Must |
| Logging & Monitoring | JSON logging, Prometheus metrics, Azure Application Insights | Must |
| Dashboard | Dash dashboard with real-time monitoring, metrics, and control toggles | Must |
| Database | PostgreSQL for trades, logs, configs, and model outputs | Must |
| Backtesting | Run strategies over OHLCV data with slippage/fill simulation | Must |
| Scripts | CLI support for backfill, config updates, and one-off tasks | Must |

### 4.2 Non-Functional Requirements

| Requirement | Description |
|------------|-------------|
| Performance | <500ms from detection to execution (arbitrage/scalp) |
| Security | API keys in Azure Key Vault, `.env` only for local/dev |
| Deployability | Docker + Kubernetes manifests for Azure (AKS-ready) |
| Observability | Full log, error, and performance telemetry to Azure Monitor |
| Maintainability | PEP8 code style, modular structure, test coverage, typed functions |
| Testability | Unit tests + E2E via simulation and backtest environment |
| Scalability | Add new pairs, exchanges, and strategies without core rewrites |

---

## 5. Design & Architecture

### Language & Tooling

- **Python 3.10+**
- **Dash** for UI
- **ccxt**, **pandas-ta**, **websockets**, **aiohttp** for trading + data
- **Azure SDK** (`azure-keyvault-secrets`, `azure-monitor-opencensus`)
- **Prometheus** for metrics
- **MLflow**, **LightGBM**, **scikit-learn** for model orchestration
- **PostgreSQL** + **SQLAlchemy** for persistence

### Directory Layout (Simplified)

```bash
hydrobot/
├── config/              # YAML + .env reader, schema validation
├── data/                # Exchange clients, WebSocket ingestion, backfillers
├── database/            # PostgreSQL utils, schema
├── features/            # Feature engineering (indicators, volatility)
├── models/              # ML prediction & regime classifiers
├── strategies/          # BaseStrategy, Arbitrage, Scalping, Manager
├── trading/             # Order Executor, Risk Controller, Portfolio Manager
├── dashboard/           # Dash app
├── scripts/             # Run backtest, collect data, update configs
├── utils/               # Logging, Prometheus setup, helpers
├── main.py              # Entry point: launch bot
```

---

## 6. Deliverables

- Core bot package (`hydrobot/`)
- Scalping and arbitrage strategy implementations
- Working live/simulated trade toggles
- Dash UI with metrics and kill switch
- ML interfaces (trained model not required in v1)
- Azure-ready Dockerfile + Kubernetes YAML manifests
- Logging, Prometheus, and Azure Monitor integration
- `requirements.txt`, `.env.example`, `README.md`
- Backtest and data collection scripts

---

## 7. Future Enhancements

- Sentiment-based filtering (Twitter, Reddit, WhaleAlerts)
- Reinforcement learning or auto-parameter tuning agents
- Telegram bot integration (alerts, control)
- CI/CD pipeline (Azure DevOps, GitHub Actions)
- Exchange expansion (Coinbase Pro, KuCoin)
- Multi-user support if productized

---

## 8. Open Issues / Pending Decisions

1. Finalize latency threshold by exchange and bot stage (data → signal → order)
2. Choose messaging layer for live bot → dashboard sync (Redis, WebSocket, DB polling)
3. Decide final evaluation metrics for ML (Sharpe ratio vs. F1-score vs. ROI delta)
4. Clarify persistent vs. in-memory strategy state (recovery after crash)
5. Determine fallback logic for exchange downtime

---

> Document compiled by integrating PRDs from April 20 and April 22 drafts.

