# legendary-Trader

A simple, structured trading bot that combines technical data analysis, a
machine-learning direction model, and risk-managed automated strategies for
**stocks and futures**. It's built to help you research and run ideas
consistently — not to guarantee profits.

> **Disclaimer:** This is an educational project, not financial advice. Markets
> are risky and models can be wrong. The bot defaults to **paper trading**
> (simulated orders only) and never touches a real broker unless you
> explicitly configure live credentials.

## How it fits together

```
Data (Yahoo Finance)  →  Indicators/Features  →  ML direction model
        │                                              │
        └──────────────► Strategy signal (BUY/SELL/HOLD) ◄──── trend/RSI filters
                                   │
                          Risk-managed position sizing (ATR-based stop/target)
                                   │
                    Backtester  ◄─┴─►  Broker (Paper by default, Alpaca optional)
```

- **Data**: `trading_bot/data/fetcher.py` pulls OHLCV bars via `yfinance` for
  any ticker — plain symbols for stocks/ETFs (`AAPL`, `SPY`) and Yahoo's
  continuous-contract suffix for futures (`ES=F`, `CL=F`, `GC=F`).
- **Features**: `trading_bot/features/indicators.py` computes SMA/EMA, RSI,
  MACD, Bollinger Bands, ATR, OBV, volatility, and returns, then builds a
  model-ready feature matrix.
- **ML model**: `trading_bot/ml/model.py` trains a Random Forest (or Gradient
  Boosting) classifier to predict the probability that price will be higher
  N bars ahead, using a chronological train/test split (no shuffling, no
  look-ahead).
- **Strategy**: `trading_bot/strategy/signals.py` turns the model's
  probability into BUY/SELL/HOLD, filtered by a long-term trend check
  (SMA-200) and an RSI overbought/oversold guard.
- **Risk**: `trading_bot/strategy/risk.py` sizes each position from an
  ATR-based stop distance and a fixed percent-of-equity risk budget, with
  hard caps on position size and daily loss.
- **Backtest**: `trading_bot/backtest/engine.py` walks bar-by-bar over
  held-out (out-of-sample) data, applying the same signal + risk logic,
  and reports return, CAGR, Sharpe, max drawdown, and win rate.
- **Execution**: `trading_bot/execution/` provides a `PaperBroker` (simulated
  fills, persisted to a local JSON file) and an optional `AlpacaBroker` for
  live/paper trading through Alpaca, plus a `TradingBot` loop that ties
  everything together.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

### 1. Backtest a strategy on historical data

```bash
python main.py backtest --symbol AAPL --period 2y --plot
python main.py backtest --symbol ES=F --period 1y   # futures work the same way
```

Prints total return, CAGR, Sharpe ratio, max drawdown, win rate, and (with
`--plot`) saves an equity curve PNG.

### 2. Train and persist a model for live/paper use

```bash
python main.py train --symbol MSFT
```

### 3. Run the automated trading loop (paper mode by default)

```bash
# One evaluation cycle for specific symbols, then exit
python main.py trade --symbol AAPL MSFT ES=F --once

# Continuous loop over the configured watchlist (config.yaml -> watchlist)
python main.py trade --watchlist
```

Each cycle: fetch latest data → indicators → ML prediction → signal →
risk-managed size → paper order. State (cash, open positions, trade log) is
persisted to `paper_account.json`.

### Going live (optional, off by default)

To route real orders through [Alpaca](https://alpaca.markets/), set
`broker.mode: alpaca` in `config.yaml` and provide credentials via
environment variables (e.g. an `.env` file):

```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # or the live endpoint
```

This requires `pip install alpaca-trade-api`. Start with Alpaca's own paper
endpoint before ever pointing this at a live account.

## Configuration

All defaults — the watchlist, data window, model hyperparameters, risk
limits, and broker mode — live in `config.yaml`. Edit it directly, or pass
`--config path/to/other.yaml` to any CLI command.

## Tests

```bash
pytest tests/ -v
```

Tests run against deterministic synthetic OHLCV data, so they require no
network access.

## Project layout

```
trading_bot/
  data/fetcher.py         # Yahoo Finance OHLCV fetch (stocks + futures)
  features/indicators.py  # technical indicators + feature engineering
  ml/model.py              # direction-prediction model (train/predict/persist)
  strategy/signals.py      # ML + technical-filter signal generator
  strategy/risk.py         # ATR-based position sizing and risk limits
  backtest/engine.py       # walk-forward backtester + performance metrics
  execution/broker.py      # PaperBroker (default) + optional AlpacaBroker
  execution/trader.py      # ties data -> model -> signal -> risk -> broker
main.py                    # CLI: backtest / train / trade
config.yaml                 # watchlist, model, risk, and broker settings
```
