# Demo interface plan

Goal for evaluation day: show that the system **works end to end** on real data.
How we got here (phases, failures, findings) is told in the PPT, not in the app.

Run: `streamlit run app/main.py` (from the repo root, inside the venv).

## Status

| # | Page | What it shows | Status |
|---|------|---------------|--------|
| 1 | **Live Session Replay** | Pick a historical day → before-the-open training/calibration/threshold decision → minute-by-minute session: index candles, ATM call/put candles with BUY/SELL markers and stop/target lines, live P(UP) vs threshold, option chain with OI bars and model probability per strike, positions, risk-check lights, activity feed, order book, intraday net P&L, closing summary with charge breakdown | **Built** (v1) |
| 2 | Model comparison | Same day / same year, several algorithms side by side (LightGBM, XGBoost, Random Forest, Logistic Regression …): AUC, Brier, reliability, net P&L. Reads `reports/benchmark.csv` produced by a benchmark script | Planned — needs the multi-algorithm runs |
| 3 | Market explorer | Any date: option-chain heat-map over time (OI, IV), IV smile, PCR and futures basis through the day | Planned |
| 4 | Year at a glance | Walk-forward run picker: equity curve, calendar heat-map of daily P&L (traded vs skipped days), trade list that links into page 1 | Planned |
| 5 | Cost calculator | Premium / lot / brokerage sliders → itemised charges and break-even move | Planned (small) |

Pages 2–5 reuse the engine in `src/live/replay.py`, the reports on disk and
`CostModel`; none needs new trading logic.

## Page 1 — design notes

- **Honesty guarantee:** `tests/test_replay.py` checks that the replay produces
  exactly the trades of the backtester (`BacktestSimulator`) for the same day.
  Every value at minute *t* uses only data up to *t*; the app just reveals the
  pre-computed tape one minute at a time.
- **Default strategy:** horizon 15 min, 13-day window (8 fit + 5 calibration),
  threshold grid 0.65–0.80, risk manager on — the best configuration so far.
  All of it is adjustable under *Strategy settings*.
- **Sit-out days:** when the no-edge rule says "don't trade", the app says so,
  still runs the model live, and offers a clearly-labelled *what-if* toggle.
- **Speed:** first load of a day ≈ 15 s (training), then cached to disk
  (`persist="disk"`), so pre-loading the demo days once makes them instant even
  after a restart.

## Evaluation-day checklist

1. Open the app the evening before and click through every demo day once
   (warms the disk cache).
2. Pick 3 days to show: a day with a winning trade, a day with a stop/loss, and a
   sit-out day (the no-edge rule is part of the system).
3. Laptop on charger, browser zoom ~80 %, sidebar collapsed after choosing the day.
4. Keep a screen recording of one full replay as a fallback.

## Ideas to make page 1 even more realistic (backlog)

- Smoother animation (client-side Plotly frames instead of re-sending charts).
- Futures price panel (needs futures close stored in the feature store).
- Sound / toast on order fills; "market depth" style ladder for the ATM strike.
- Second underlying (NIFTY) once its features are built.
