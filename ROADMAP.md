# NSE AI Options Bot — Master Implementation Roadmap (v2)

> Upgraded plan, July 2026. Supersedes the Phase-1 Antigravity plan
> ("Modeling and Simulation Plan / Phase 5" + Final Theory Report).
> Everything in the old plan up to and including **momentum features +
> classification state machine** is DONE (commit `c89f7c5`).
>
> Goal: evolve the current single-day research script into a production-grade
> trading system that runs the **same code path** on 5 years of historical
> ("dummy") data and, later, on live Fyers market data — with an
> event/news risk layer (the "war factor") that can be set manually by the
> operator or inferred automatically from market news.

---

## Where we are today (audit summary)

**Works:**
- 5 years (2020–2024) of 1-minute BANKNIFTY + NIFTY options/spot/futures CSVs.
- `FeatureEngineer`: symbol parsing, TTE, IV + Greeks (py_vollib_vectorized), 1m/5m momentum.
- `OptionsModel`: GBM classifier, P(option UP in 5 min), near-ATM filter.
- `BacktestSimulator`: single-ATM-contract position state machine, PnL chart.

**Known defects to fix first (Phase 0/2):**
1. **Target-label bug** — `OptionsModel._build_target` does
   `close_opt.shift(-horizon)` on a frame sorted by *datetime across all
   symbols*, so the "future price" often belongs to a *different contract*.
   Targets must be shifted **per symbol**.
2. **No transaction costs** — no brokerage, STT, exchange fees, or bid-ask
   slippage. Thresholds of 0.52/0.48 near coin-flip likely lose money after costs.
3. **Hardcoded lot size 25** — BankNifty lot size changed over the 2020–2024
   window (20 → 25 → 15 → 30/35); must be config-driven per instrument+date.
4. **7-day train / 1-day test only** — a single test day proves nothing;
   need walk-forward over all ~1,200 trading days.
5. `requirements.txt` is UTF-16 encoded (breaks `pip install -r` on Linux);
   `src/metrics.py` is empty; `data_fetcher.py` is actually a data *inspector*;
   `sys.path` hack instead of a proper package.
6. Features are recomputed from raw CSVs on every run (greeks are expensive) —
   need a cached feature store.

---

## Target architecture

```
                    ┌─────────────────────────────────────────────┐
                    │                ORCHESTRATOR                 │
                    │   (same loop for backtest / paper / live)   │
                    └─────────────────────────────────────────────┘
                       │            │             │           │
             ┌─────────▼──┐  ┌──────▼─────┐  ┌────▼─────┐  ┌──▼────────┐
             │ DataFeed   │  │ Signal     │  │ Risk     │  │ Execution │
             │ (abstract) │  │ Engine     │  │ Manager  │  │ (abstract)│
             ├────────────┤  │ features + │  │ sizing,  │  ├───────────┤
             │ ReplayFeed │  │ model      │  │ limits,  │  │ PaperBroker│
             │ (CSV 5yr)  │  │ inference  │  │ event    │  │ FyersBroker│
             │ FyersFeed  │  │            │  │ overlay  │  │           │
             └────────────┘  └────────────┘  └──────────┘  └───────────┘
                                                  ▲
                                   ┌──────────────┴──────────────┐
                                   │  EVENT / NEWS RISK LAYER    │
                                   │  manual operator dial  +    │
                                   │  auto news/LLM sentiment    │
                                   └─────────────────────────────┘
```

The key idea: **DataFeed and Broker are interfaces.** A `ReplayFeed` streams
the historical CSVs minute-by-minute so the whole system runs end-to-end on
dummy data exactly as it will live. Going live later means swapping in
`FyersFeed`/`FyersBroker` — no strategy code changes.

---

## Phase 0 — Foundation & Repo Hygiene  *(small, do first)*  ✅ DONE (Jul 2026)

- [x] Restructure into a proper package:
  ```
  nse_ai_options_bot/
  ├── config/settings.yaml        # instrument specs, lot sizes by date, costs, thresholds
  ├── src/
  │   ├── data/        (loaders, inspector, feature store)
  │   ├── features/    (feature_engineering.py)
  │   ├── models/      (model.py, registry/)
  │   ├── backtest/    (walkforward.py, simulator.py, costs.py)
  │   ├── risk/        (risk_manager.py, events.py)
  │   ├── execution/   (broker_base.py, paper_broker.py, fyers_broker.py)
  │   ├── feeds/       (feed_base.py, replay_feed.py, fyers_feed.py)
  │   ├── news/        (ingest.py, sentiment.py)
  │   └── utils/       (logging, calendar, symbols)
  ├── scripts/         (run_backtest.py, run_paper.py, run_live.py, build_features.py)
  ├── tests/
  ├── reports/         (generated run reports)
  └── docs/            (this roadmap, theory report, run reports)
  ```
- [x] Central YAML config + `python-dotenv` for secrets; **lot-size-by-date table** for BANKNIFTY/NIFTY.
- [x] Rewrite `requirements.txt` as UTF-8 with only the ~15 real deps (pandas, numpy, scikit-learn, py_vollib_vectorized, matplotlib, lightgbm, pyyaml, fyers-apiv3, feedparser, requests, pytest…).
- [x] Structured logging util (`src/utils/logging_setup.py`).
- [x] `pytest` skeleton + first tests (symbol parser, target builder, costs, config).
- [x] Proper `README.md`.

**Exit criteria:** `pip install -r requirements.txt` works cross-platform; `pytest` green; `python scripts/run_backtest.py` reproduces today's behavior.

## Phase 1 — Correctness Fixes  *(critical)*  ✅ DONE (Jul 2026)

- [x] Fix per-symbol target shifting (groupby `symbol` before `shift(-horizon)`).
- [x] Fix per-symbol time-gap handling (gap guard: no label across >2× horizon gap).
- [x] Cost model (`backtest/costs.py`): brokerage ₹20/order, STT sell-side on premium, exchange txn, GST, stamp duty, SEBI fees + **slippage** per side. Every simulated fill goes through it.
- [x] Deadband label option: UP means `future > now × (1 + deadband)` so the model learns *tradeable* moves, not 1-tick noise.
- [x] Re-run the 7-day baseline: post-cost result on 2020-01-10 is **negative**
      (CE net ≈ −₹2.1k, PE net ≈ −₹1.9k, charges ≈ ₹1.6–2.3k) — honest benchmark recorded.

**Exit criteria:** unit test proves the target for symbol X never uses prices of symbol Y; backtest report shows gross AND net PnL.

## Phase 2 — Feature Store + Full-History Walk-Forward Backtest  ✅ CORE DONE (Jul 2026)

- [x] `scripts/build_features.py`: one-time pass converting all 5 years of raw CSVs into **Parquet** feature files (`data/features/{instrument}/{date}.parquet`). All 1,139 days built (~0.8s/day), zero failures.
- [x] `backtest/walkforward.py`: rolling scheme — train on N days, test the next day, slide forward. Retrain cadence configurable.
- [x] Trade log persisted per run (`reports/walkforward_*/trades.csv`). *(SQLite upgrade deferred.)*
- [x] Real metrics module (`src/backtest/metrics.py`): Sharpe, Sortino, profit factor, expectancy, max drawdown, win rate, avg hold, best/worst day.
- [x] Markdown + PNG run report per backtest (equity curve, daily bars, monthly table). *(HTML/PDF polish deferred.)*
- [x] Both CE and PE tradeable. *(NIFTY runs pending — same code path, just `--instrument nifty` after building its features.)*

**Recorded baseline (full-year 2020, entry 0.70/exit 0.35, 10-day train):**
4,706 trades, gross −₹72k, charges −₹277k, **net −₹350k**, PF 0.70.
Diagnosis: gross ≈ −₹15/trade (≈ zero raw edge at 5-min horizon) while costs
≈ ₹59/trade → the strategy trades ~20×/day and pays the toll every time.
Phase 3's job: calibration + threshold/expectancy optimization + longer
horizons to cut trade count 10× and make the per-trade edge exceed costs.

**Exit criteria:** one command backtests all 5 years in minutes (from Parquet), produces a report; results segmented by year (2020 Covid, 2022 Ukraine, 2024 election — natural stress tests already in the data).

## Phase 3 — Model Upgrades  ✅ CORE DONE (Jul 2026)

- [x] New features: OI change, volume z-score, PCR (OI + volume), IV z-score, IV skew, futures basis / returns / OI flow / VWAP distance, time-of-day, day-of-week, realized vol 15m/60m. *(Multi-day IV rank deferred.)*
- [x] Swap GBM → **LightGBM** (native NaN handling, fast walk-forward retrains).
- [x] **Probability calibration** — isotonic on a 2-day held-out fold inside each sliding window.
- [x] Threshold optimization — daily grid search maximizing *post-cost net PnL simulated on the calibration days*; ties → higher threshold.
- [x] **No-edge skip rule** — if the best calibration-day net ≤ 0, don't trade the test day at all.
- [ ] Purged/embargoed CV for hyperparameter tuning *(deferred — thresholds were the binding constraint, not tree params)*.
- [ ] Model registry *(deferred to Phase 6 — per-run params live in experiments.csv)*.
- [x] Experiment log: `reports/experiments.csv`, one row per run.
- [x] Multi-horizon tested: 5 / 15 / 30 min full-year 2020 runs.

**Exit criteria met:** net expectancy improved from −₹74.3/trade (Phase-2
baseline) to −₹36.2/trade, and full-year net from **−₹350k → −₹10k (35×)**:

| Full-year 2020 | trades | gross | charges | net | PF | Sharpe |
|---|---|---|---|---|---|---|
| Phase-2 baseline (0.70 fixed) | 4,706 | −72k | 277k | −350k | 0.70 | −7.6 |
| Phase-3, h=5m  | 470 | **+5.2k** | 27k | −22k | 0.79 | −2.6 |
| Phase-3, h=15m ← best | 276 | **+5.7k** | 16k | **−10k** | 0.85 | −1.8 |
| Phase-3, h=30m | 236 | −18k | 14k | −32k | 0.66 | −4.1 |

Diagnosis for Phase 4: at h=15m gross is now positive; ~₹40 of the ~₹57/trade
charges is *flat brokerage*, so the remaining gap is (a) per-trade stop-loss —
avg loss ₹460 > avg win ₹426, cut the left tail; (b) position sizing to
amortize flat costs; (c) regime filter. h=30m shows unmanaged long holds
bleed (avg loss ₹805) → stops matter more than horizon beyond 15m.

## Phase 4 — Strategy & Risk Layer

- [ ] `RiskManager` between signal and execution:
  - position sizing (fixed-fraction of capital, volatility-scaled),
  - hard stop-loss & take-profit per trade (in premium %),
  - max trades/day, max concurrent positions, daily loss kill-switch,
  - no-entry windows (first 5 min, last 15 min, expiry-day afternoon rules),
  - margin/capital tracking for realistic account simulation.
- [ ] Trade both directions properly: buy CE on bullish signal, buy PE on bearish (two models or symmetric signal).
- [ ] Regime filter: realized-vol / trend state gating which setups are allowed.
- [ ] All rules config-driven and backtested through Phase-2 engine.

**Exit criteria:** 5-year walk-forward with full risk stack shows controlled drawdowns; kill-switch and stops verified by unit tests.

## Phase 5 — Event & News Intelligence (the "war factor")

Two inputs producing one number: **`event_risk ∈ [0, 1]`** with a category
(war/geopolitics, policy/RBI/Fed, election, budget, crash/panic, none).

- [ ] **Manual operator dial:** `config/event_state.yaml` (or CLI `scripts/set_event.py --level 0.8 --type war --note "..."`), hot-reloaded by the orchestrator each cycle. Operator can always override the auto value (manual wins).
- [ ] **Automatic news reader:**
  - `news/ingest.py`: poll RSS feeds (Reuters world/markets, Economic Times Markets, Moneycontrol, Business Standard) every N minutes; dedupe; store headlines in SQLite.
  - `news/sentiment.py`: score each headline for market-risk relevance & severity. Tier 1: keyword/rules (war, strike, sanctions, RBI, repo, crash…). Tier 2: LLM scoring via Claude API (batch headlines → JSON severity+category) or local FinBERT. Design as a pluggable scorer so both work.
  - Aggregate into `event_risk` with time decay (e.g., half-life 6h) so old news fades.
- [ ] **Consumption** (both, measured separately):
  - as a **risk overlay**: high event_risk → cut position size, widen entry threshold, or halt new entries entirely (config matrix);
  - as a **model feature**: event_risk + category one-hots enter the feature set.
- [ ] **Backtestable on dummy data:** build `data/events/historical_events.csv` for 2020–2024 (Covid crash Mar-2020, Russia-Ukraine Feb-2022, Fed hikes 2022, general election May/Jun-2024, budget days, RBI dates) + India VIX daily as a continuous proxy. Walk-forward A/B: strategy with vs. without event layer.

**Exit criteria:** replaying Feb–Mar 2020 and Feb 2022, the event layer measurably reduces drawdown vs. baseline; live news poller runs for a day and produces sensible scores on real headlines.

## Phase 6 — Simulated Live Loop (paper trading on dummy data)

This is what makes the project "fully functional with dummy data".

- [ ] `feeds/replay_feed.py`: streams a chosen historical day (or range) bar-by-bar with a speed multiplier (1× real-time to ∞), exposing `get_next_bar()` / subscription API identical to the future live feed.
- [ ] `execution/paper_broker.py`: accepts orders, fills at next bar with slippage+costs from Phase 1, tracks positions/margin/cash.
- [ ] `orchestrator.py`: the single event loop — on each bar: update features incrementally → model inference → risk manager (incl. event_risk) → orders → broker. Same loop object for replay, paper-on-live-data, and live.
- [ ] **Dashboard** (Streamlit): live price + P(UP), open position, PnL, trade log, event-risk gauge, model info, kill-switch button + manual event dial.
- [ ] Alerts: Telegram/desktop notification on entry/exit/kill-switch (optional).
- [ ] State persistence & crash recovery (restart mid-day, reload open position).

**Exit criteria:** pick any historical day, run `python scripts/run_paper.py --date 2022-02-24 --speed 60x`, watch the bot trade it live on the dashboard, and the result matches the Phase-2 batch backtest for the same day within slippage tolerance.

## Phase 7 — Live Market Integration (Fyers)

`fyers_apiv3` is already a dependency; `.env` holds credentials.

- [ ] Auth module: Fyers OAuth login flow, token refresh, stored in `.env`/keyring.
- [ ] `feeds/fyers_feed.py`: WebSocket subscription to spot + relevant option strikes (ATM ± 5); build 1-minute bars in memory; resubscribe as ATM drifts.
- [ ] Instrument master: daily symbol/lot-size/expiry download and mapping to our internal symbol format.
- [ ] `execution/fyers_broker.py`: order placement/modification/cancel, position & margin queries — behind the same Broker interface; **`--mode paper|live` flag with live requiring an explicit config unlock**.
- [ ] Safety interlocks: market-hours check, circuit-breaker halt detection, max-order-size cap, "panic flatten" command, mandatory kill-switch test before every live session.
- [ ] Stage rollout: (1) live data + paper broker for ≥2 weeks → (2) live with 1 lot minimum size → (3) scale per Phase-4 sizing.
- [ ] Nightly job: append the day's live bars to the historical store; retrain per schedule; morning pre-flight report (model loaded, data fresh, calendar/expiry correct).

**Exit criteria:** two clean weeks of paper trading on live data with performance consistent with backtest expectations before any real order.

## Phase 8 — Continuous Improvement Loop

- [ ] Drift monitoring: live feature distributions & calibration vs. training (alert when off).
- [ ] Auto-generated weekly performance report (paper + live vs. backtest).
- [ ] Champion/challenger: new candidate models shadow-trade in paper before promotion.
- [ ] Research backlog: LSTM/temporal models on bar sequences, order-flow features, spread strategies (vertical spreads to cap risk instead of naked long options), NIFTY+BANKNIFTY portfolio allocation.

---

## Sequencing & effort guide

| Phase | Depends on | Rough effort | Milestone commit |
|-------|-----------|--------------|------------------|
| 0 Foundation | — | 1 session | `Phase 0: package restructure + config + tests` |
| 1 Correctness | 0 | 1 session | `Phase 1: per-symbol targets + cost model` |
| 2 Walk-forward | 1 | 2–3 sessions | `Phase 2: feature store + 5yr walk-forward` |
| 3 Model | 2 | 2–3 sessions | `Phase 3: LightGBM + calibration + registry` |
| 4 Risk | 2 | 1–2 sessions | `Phase 4: risk manager + dual-direction` |
| 5 Events/News | 2 (4 helps) | 2 sessions | `Phase 5: event risk layer (manual + auto)` |
| 6 Sim-live loop | 4, 5 | 2–3 sessions | `Phase 6: replay orchestrator + dashboard` |
| 7 Fyers live | 6 | 2–3 sessions | `Phase 7: live feed + broker integration` |
| 8 Continuous | 7 | ongoing | — |

**Process rule:** every phase ends with tests green, an updated run report in
`reports/`, a checked-off section here, and a commit pushed to
`https://github.com/anubhaw0raj/nse_ai_options_bot`.

## Honest expectations

Minute-level long-options scalping is one of the hardest edges to find: you
pay theta, spread, and costs on every trade. The purpose of Phases 1–3 is to
measure the edge *honestly* (post-cost, 5 years, calibrated). If net
expectancy is negative, the framework still pays off — the same infrastructure
backtests spreads, longer horizons, or positional strategies by changing
config, not code. Do not skip from Phase 3 to Phase 7.
