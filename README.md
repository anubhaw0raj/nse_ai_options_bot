# NSE AI Options Bot

Machine-learning trading bot for NSE index options (BANKNIFTY / NIFTY).
Predicts short-horizon option premium direction from 1-minute option-chain
data and backtests a long-options strategy with realistic Indian market costs.

**Full plan:** see [ROADMAP.md](ROADMAP.md) — currently at Phase 2/3
(walk-forward backtesting + modern feature set).

## What the model sees

Beyond classical inputs (moneyness, TTE, IV, greeks, momentum), every row
carries **modern option-market context**:

| Group | Features |
|---|---|
| Contract flow | OI change 1m/5m, volume z-score, IV z-score |
| Chain-wide | Put/Call ratio (OI & volume), IV skew (PE−CE) |
| Futures / institutions | basis %, futures 1m/5m returns, futures OI change, VWAP distance |
| Regime & calendar | realized vol 15m/60m, time-of-day (sin/cos), day-of-week |

Labels are built **per contract** with a time-gap guard and a deadband
(the move must beat a threshold %, not 1 tick). All simulated fills pass
through a cost model: brokerage, STT, exchange fees, GST, stamp duty, SEBI
fees and slippage — reported PnL is **net**.

## Layout

```
config/settings.yaml     all tunables: lot sizes by date, costs, thresholds
src/
  config.py              config loader, lot-size-by-date
  data/                  raw CSV discovery + inspector
  features/              feature engineering (greeks + modern inputs)
  models/                LightGBM direction classifier
  backtest/              cost model, simulator, (walk-forward, metrics)
scripts/
  run_backtest.py        N-day train / 1-day test, any window offset
tests/                   pytest suite
data/raw_option_chain/   1-min CSVs 2020–2024 (not in git)
reports/                 generated charts & run reports
```

## Quickstart

```bash
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
pytest                                   # sanity checks
python scripts/run_backtest.py           # 7-day train, test day 8
python scripts/run_backtest.py --offset 30 --train-days 10
```

Raw data layout expected under `data/raw_option_chain/`:
`{instrument}_data/{instrument}_{options|spot|fut}/YYYY/M/*.csv` with
columns `date,time,symbol,open,high,low,close[,oi,volume]`.

> ⚠️ Research software. Not investment advice. Verify lot sizes, costs and
> exchange rules against NSE circulars before any live use.
