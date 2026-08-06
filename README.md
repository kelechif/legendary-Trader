# Quant Platform

Live multi-asset paper-trading dashboard with Coinbase WebSocket feeds, strategy plugins, backtesting, and performance analytics.

## Features

- **Portfolio panel** — positions, equity, allocation per asset
- **Performance metrics** — Sharpe ratio, max drawdown, win rate
- **Alerts** — color flash, sound, browser popups on trades/drawdowns
- **Backtesting engine** — run strategies on collected price history
- **Order book panel** — live bids/asks via Coinbase REST API (polled every 5s)
- **Multi-timeframe candles** — 1m, 5m, 15m, 1h
- **Strategy parameters UI** — tune lookback, thresholds, MACD periods
- **Logging + metrics** — rotating log file + in-dashboard metrics
- **Config system** — YAML config with local overrides
- **Plugin architecture** — drop new strategies into `services/strategy_engine/plugins/`

## Architecture

```
config/
  default.yaml          # Main configuration
  local.yaml            # Optional local overrides (gitignored)
services/
  market_data/          # WebSocket feed, candles, order book
  strategy_engine/      # Plugin-based strategies
    plugins/            # Add new strategy files here
  execution_engine/     # Paper trading, portfolio, performance
  risk_governance/      # Alert system
  training_engine/      # Backtesting
  dashboard/            # Flask UI + API
  shared/               # Config, logging, metrics
infra/                  # Docker
```

## Quick start

```bash
pip install -r requirements.txt
python run.py
```

Open **http://localhost:8080** — the UI binds immediately; in Moomoo equity mode, klines continue loading in the background (`feed_status` in `/data`).

On Windows, use `start.bat` to free port 8080 and launch the platform.

### Docker

```bash
cd infra
docker compose up --build
```

## Configuration

Edit `config/default.yaml` or create `config/local.yaml` for overrides.

Environment variables:
| Variable | Description |
|----------|-------------|
| `PORT` | HTTP port (default 8080) |
| `QUANT_CONFIG` | Path to JSON config override file |

## Adding a Strategy Plugin

Create `services/strategy_engine/plugins/my_strategy.py`:

```python
from services.strategy_engine.base import StrategyPlugin
from services.strategy_engine.registry import register

@register
class MyStrategy(StrategyPlugin):
    name = "MyStrategy"
    description = "My custom strategy"
    default_params = {"period": 14}

    def signal(self, prices, params=None, candles=None):
        # return "BUY", "SELL", or "HOLD"
        return "HOLD"
```

Add default params under `strategies:` in `config/default.yaml`, then restart.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/data` | GET | Full dashboard snapshot |
| `/api/strategies` | GET | List strategies + param schemas |
| `/api/strategy/<name>` | POST | Switch active strategy |
| `/api/strategy/<name>/params` | GET/POST | Read/update parameters |
| `/api/backtest` | POST | Run backtest `{strategy, asset, params?}` |
| `/api/config` | GET | Current configuration |
| `/api/metrics` | GET | System metrics |
| `/api/alerts` | GET | Recent alerts |

## Moomoo equity mode (large-cap daily trend)

For daily large-cap trend trading via Moomoo OpenD:

1. Install and start **OpenD** (`127.0.0.1:11111`)
2. Copy equity config: `cp config/equity.yaml.example config/local.yaml`
3. Install deps: `pip install -r requirements.txt`
4. Run daily pipeline: `python run_daily.py` (or `run_daily.bat` on Windows)

**Universe (~100 US large caps):**
```bash
# From Moomoo screener (OpenD required)
python refresh_universe.py --force

# From static YAML fallback (no OpenD)
python refresh_universe.py --source file

# Inspect
curl http://localhost:8080/api/universe
```

Configure in `config/local.yaml`:
```yaml
universe:
  source: moomoo_screener   # or file
  limit: 100
  min_market_cap_usd: 20000000000
  cache_file: data/universe.json
  fallback_file: config/universe_us_large_cap.yaml

trading:
  broker: internal          # set moomoo + safe_mode: false for OpenD SIMULATE orders
```

**Ranked entries:** the engine scans all universe names, ranks BUY signals by trend score, and fills up to `max_positions` (default 10). View ranked signals at `/api/signals` or the dashboard **Universe Signals** panel.

**Regime gating:** new entries only in `BULL` regime (configurable under `trading.regime`).

**Universe backtest:**
```bash
python run_backtest_universe.py
# or POST /api/backtest/universe from the dashboard
```

**Walk-forward optimization** (requires cached klines from `run_daily.py`):
```bash
# Expanded grid (EMA/ATR/RSI), sample 64 combos for ~13 min runtime
python run_wfo.py --grid expanded --limit 100 --folds 2 --max-combos 64 --apply
# Core grid (RSI only, 27 combos)
python run_wfo.py --grid core --folds 3 --apply
python refresh_missing_klines.py   # retry tickers missing from cache
# or POST /api/wfo with {"grid": "expanded", "limit": 50, "folds": 2, "max_combos": 64}
# GET /api/universe/health — cached kline coverage
```

**Moomoo SIMULATE orders** (`trading.broker: moomoo`, `safe_mode: false`):
```bash
python run_simulate_orders.py   # daily refresh + ranked signals + OpenD orders
# GET /api/trading/account — buying power, total_assets, drawdown_halt_active, can_buy
```

### Margin safety (paper / SIMULATE)

Moomoo **SIMULATE MARGIN** accounts can face forced liquidation when NAV falls below maintenance margin. To reduce that risk:

| Config key | Default (example) | Purpose |
|------------|-------------------|---------|
| `trading.simulate_acc_type` | `CASH` | Prefer SIMULATE cash account over margin |
| `trading.simulate_acc_id` | — | Explicit SIMULATE account id override |
| `trading.min_buying_power` | `1000` | Block BUY if OpenD `power` is below this |
| `trading.min_power_pct` | — | Alternative: reserve as fraction of `total_assets` |
| `trading.drawdown_halt_pct` | `12.0` | Stop **new entries** when portfolio NAV drawdown from peak exceeds this; **SELL exits still run** |
| `trading.safe_mode` | `true` | Log orders without executing (safest default) |
| `trading.max_exposure_pct` | `0.50` | Cap invested fraction of NAV |
| `trading.max_positions` | `5` | Limit concurrent holdings |

Blocked buys log `order_skipped` to `logs/execution.log` with reason (`min_buying_power`, `drawdown_halt`, etc.).

**Reset paper account:** In the moomoo app go to **Me → Paper Trading → Reset Card** if buying power is depleted or after a forced liquidation. You can also switch to a SIMULATE CASH account via `simulate_acc_type: CASH`.

**Safer local overrides** (add to `config/local.yaml` when live SIMULATE trading):
```yaml
trading:
  safe_mode: false
  simulate_acc_type: CASH
  min_buying_power: 1000
  drawdown_halt_pct: 12.0
  max_exposure_pct: 0.50
  max_positions: 5
```

**OpenD live smoke test** (quote connection + sample klines + signal scan):
```bash
copy config\equity.yaml.example config\local.yaml
python run_opend_smoke_test.py
python run_daily.py          # full universe refresh + ranked signals
```

5. Run dashboard: `python run.py` → http://localhost:8080

**Strategy:** `InstitutionalTrend` — 200 SMA regime, MA stack, EMA pullback entries, RSI/MACD confirmation.

**Safety defaults:** `trading.safe_mode: true` logs orders without executing. Set `safe_mode: false` to paper-trade via internal portfolio sim.

Daily klines are cached under `data/klines/`. Structured logs: `logs/data.log`, `logs/signal.log`, `logs/execution.log`, etc.

## 0DTE options (TradeStation + Moomoo)

| Broker | Use case | Entry point |
|--------|----------|-------------|
| **TradeStation** | SPX 0DTE + TWMN CTV | `tradewithmenow/easylanguage/*.els`, `SETUP_Michaels_SIM.md` |
| **Moomoo** | US.SPY/QQQ 0DTE via OpenD | `run_0dte_moomoo.py` |

**Moomoo 0DTE (OpenD):**
```bash
copy config\options.yaml.example config\local.yaml
# set options.execution.broker: moomoo, options.moomoo.safe_mode: true
python run_0dte_moomoo.py --status
python run_0dte_moomoo_loop.py --once --dry-run   # single tick
python run_0dte_moomoo_loop.py                    # auto-loop every 60s
```

**TradeStation:** see `tradewithmenow/SETUP_Michaels_SIM.md`

See `tradewithmenow/README.md` for phased rollout (signal-only → SIM → live).

## Logs

Logs written to `logs/platform.log` (configurable in `config/default.yaml`).
