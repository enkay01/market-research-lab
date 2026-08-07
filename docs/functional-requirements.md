# Functional Requirements

Status: accepted scope

This document is the source of truth for product behavior. Domain terms are defined in [`CONTEXT.md`](../CONTEXT.md); implementation belongs in [`software-design.md`](./software-design.md).

## Product constraints

| ID | Requirement |
|---|---|
| CORE-001 | The application must run on one local machine from one top-level `uv` command and open in a browser. |
| CORE-002 | The application must operate without authentication, a cloud runtime, a cloud database, or paid data integrations. |
| CORE-003 | FastAPI/Pydantic must validate untrusted interface, file, and provider input before internal modules consume it. |
| CORE-004 | Internal modules may trust values produced by the validated application interface. |
| CORE-005 | Authored definitions must support one mutable draft and immutable sequential revisions named `v1`, `v2`, and so on. |
| CORE-006 | Every Run must identify its Definition Revisions, Dataset Versions, parameters, software revision, and environment. |
| CORE-007 | Repeating a deterministic Run with identical inputs must reproduce the same outputs. |
| CORE-008 | A failed import, calculation, training task, or Run must preserve its error and logs without presenting partial output as complete. |
| CORE-009 | The application must never place, route, or submit an order. |
| CORE-010 | Code for techniques must be written in an external IDE; the application must not provide a code editor or notebook environment. |

## Projects and revisions

| ID | Requirement |
|---|---|
| PRJ-001 | The Analyst must be able to create, list, open, rename, and delete a Project. |
| PRJ-002 | A Project must group its research, saved definitions, Definition Revisions, Runs, reports, and Alerts. |
| PRJ-003 | Projects must share the local Market Dataset catalogue rather than duplicating large datasets. |
| PRJ-004 | Saving a draft must copy its complete reproducible definition into the next revision directory. |
| PRJ-005 | A revision referenced by a Run must be read-only through the application. |
| PRJ-006 | Run artifacts must live in a dedicated directory identified by a stable Run ID. |

Completion criterion: a Project can be created, receive a revised definition, execute a Run, close, reopen, and display the same revision and artifacts.

## Market data

| ID | Requirement |
|---|---|
| DATA-001 | The Analyst must be able to import daily market data from CSV, JSON, and Parquet files. |
| DATA-002 | The Analyst must be able to download data from an initial free public provider using credentials from `.env.local` when required. |
| DATA-003 | Initial coverage must include US-listed equities and ETFs, daily OHLCV, splits, dividends, security identity, and quarterly and annual fundamentals. |
| DATA-004 | Ingestion must map source records into canonical typed records and report rejected rows with reasons. |
| DATA-005 | Every canonical observation must retain source, retrieval time, units, and the time it became eligible for analysis. |
| DATA-006 | Each successful import or download must create a Dataset Version. |
| DATA-007 | The Analyst must be able to inspect source, coverage dates, row counts, missing fields, and validation warnings before using a Dataset Version. |
| DATA-008 | Point-in-time queries must exclude observations whose eligibility time is later than the requested as-of time. |
| DATA-009 | Data lacking sufficient temporal provenance may support current research but must be rejected from affected historical Runs. |
| DATA-010 | Raw prices, adjusted values, and corporate actions must remain distinguishable. |

Completion criterion: an imported or downloaded dataset can be inspected, versioned, queried as of a historical time, and rejected by a synthetic future-data test.

## Market research

| ID | Requirement |
|---|---|
| RES-001 | The Analyst must be able to search locally available Securities by symbol or name. |
| RES-002 | The Analyst must be able to maintain lightweight Project watchlists. |
| RES-003 | Each watched Security may have one current Research Thesis stored as Markdown. |
| RES-004 | A Research Thesis must support a summary, evidence, risks, catalysts, assumptions, source links, and dated updates without requiring every section. |
| RES-005 | A Security view must link its available data, Research Thesis, Valuations, relevant Runs, and Alerts. |
| RES-006 | Basic field filtering and sorting are sufficient; a saved-screen engine and visual query builder are outside scope. |

Completion criterion: the Analyst can find a Security, add it to a watchlist, write a thesis, close the application, and recover the same research.

## Valuation

| ID | Requirement |
|---|---|
| VAL-001 | The first release must implement FCFF discounted cash flow and comparable-company valuation methods. |
| VAL-002 | Fundamentals may seed valuation inputs, which the Analyst can edit directly for the current Valuation. |
| VAL-003 | DCF inputs must include forecast periods, revenue or cash-flow assumptions, margins where applicable, tax, reinvestment, WACC, terminal method, shares, cash, debt, currency, and units. |
| VAL-004 | DCF results must include enterprise value, equity value, per-share value, forecast cash flows, terminal value contribution, and warnings. |
| VAL-005 | The DCF view must support bear, base, and bull cases plus WACC/terminal-assumption sensitivity. |
| VAL-006 | Comparable-company analysis must support an analyst-selected peer set and at least P/E, EV/revenue, EV/EBITDA, and free-cash-flow yield when inputs exist. |
| VAL-007 | Every result must identify the valuation method revision, Dataset Versions, input values, provenance, units, currency, and calculation time. |
| VAL-008 | The Analyst must be able to save a new Definition Revision and compare selected valuation results side by side. |
| VAL-009 | Adding another valuation method must require ordinary Python code, tests, and UI metadata rather than a runtime plugin mechanism. |

Completion criterion: the Analyst can value one Security with DCF and peers, revise assumptions, compare results, and reproduce either result from its manifest.

## Indicators and Predictive Models

| ID | Requirement |
|---|---|
| MOD-001 | Indicators and Predictive Models must be implemented as Python code with typed parameters and a saved Definition Revision. |
| MOD-002 | An Indicator must return a time-aligned series and make its warm-up or missing period explicit. |
| MOD-003 | The interface must allow parameter entry, execution, charting against source data, and inspection of derived values. |
| MOD-004 | A Predictive Model must state its target, prediction horizon, features, training window, and output meaning. |
| MOD-005 | Model evaluation must use chronological train/validation/test splits and support rolling or expanding walk-forward evaluation. |
| MOD-006 | Preprocessing and feature fitting must occur inside each training window. |
| MOD-007 | Each model Run must preserve the fitted artifact, feature definition, parameters, seed where supported, Dataset Versions, and in-sample versus out-of-sample metrics. |
| MOD-008 | A Project must be able to contain, compare, and combine multiple compatible Predictive Models. |
| MOD-009 | A technique must be compared with an explicit naive benchmark before it can be used by an enabled Strategy. |
| MOD-010 | LightGBM and sentiment analysis are supported future techniques, not mandatory initial implementations. |

Completion criterion: a code-defined Indicator can be graphed and used by a Strategy, and one later Predictive Model can complete leakage-safe walk-forward evaluation with reproducible artifacts.

## Strategies and backtesting

| ID | Requirement |
|---|---|
| BT-001 | A Strategy must consume only data eligible at its decision time and return desired portfolio weights. |
| BT-002 | A Backtest Run must specify the Strategy revision, Dataset Versions, universe, date range, starting cash, rebalance schedule, and Execution Model assumptions. |
| BT-003 | A Signal calculated from a completed daily bar must default to execution no earlier than the next eligible bar. |
| BT-004 | The engine must maintain cash, positions, orders, fills, costs, and portfolio value in a dated ledger. |
| BT-005 | The first vertical slice may support one Security and long/flat weights. |
| BT-006 | The completed Backtesting Epic must support multiple Securities, long and short positions, leverage and margin limits, commissions, slippage, borrow fees and availability, cash interest, splits, dividends, delistings, and rejected trades. |
| BT-007 | Standard weekends and exchange holidays must be honored. Multi-exchange session coordination, half-days, and exceptional closures may be added later. |
| BT-008 | The engine must prevent a fill from using a price or input unavailable at its simulated time. |
| BT-009 | A completed Backtest Run must produce trades, fills, positions, equity curve, drawdown curve, exposure, turnover, cost breakdown, warnings, and a manifest. |
| BT-010 | Summary metrics must include total and annualized return, annualized volatility, Sharpe ratio, Sortino ratio, maximum drawdown, Calmar ratio, hit rate, turnover, gross/net exposure, and benchmark-relative return where applicable. |
| BT-011 | Tests must cover future-data leakage, next-bar execution, fees, slippage, splits, dividends, shorts, borrow cost, leverage rejection, and deterministic replay using small synthetic datasets. |

Completion criterion: the target Epic can reproducibly simulate the same long/short portfolio twice with identical ledger entries and can prove that future observations change no earlier decisions.

## Dashboards and reports

| ID | Requirement |
|---|---|
| REP-001 | The interface must provide curated views for data coverage, Security research, Valuation results, Indicator or model output, Backtest Runs, and comparisons. |
| REP-002 | A Backtest dashboard must show headline metrics, benchmark comparison, equity and drawdown, exposure, turnover, trades, costs, and warnings. |
| REP-003 | A model dashboard must separate training, validation, and out-of-sample performance. |
| REP-004 | The Analyst must be able to compare selected compatible Runs or Valuations side by side. |
| REP-005 | Each completed Run must export a local HTML report, relevant CSV tables, and a JSON manifest. |
| REP-006 | Reports must label assumptions, data coverage, revisions, warnings, and whether values are in-sample or out-of-sample. |
| REP-007 | Dashboard construction and arbitrary drag-and-drop layouts are outside scope. |

Completion criterion: a completed Backtest Run can be understood from the interface and reproduced using only its report, manifest, referenced revisions, and available datasets.

## Signals and Alerts

| ID | Requirement |
|---|---|
| ALT-001 | While the engine is running, the Analyst must be able to evaluate an enabled Strategy against newly available data. |
| ALT-002 | A resulting Signal must show Security, intended position or action, decision time, data time, Strategy revision, and concise rationale. |
| ALT-003 | New Signals must appear in an in-app Alert list. |
| ALT-004 | The interface must state when the engine is offline or data is stale. |
| ALT-005 | Alerts must not place orders, send mobile notifications, or maintain a manual-trade journal. |

Completion criterion: refreshing eligible data can produce a traceable in-app Alert without any path to broker execution.

## Agent-assisted technique implementation

| ID | Requirement |
|---|---|
| AGT-001 | Agent-assisted work must occur through an external development agent operating on the repository. |
| AGT-002 | The application itself must not require an LLM or agent runtime. |
| AGT-003 | For a paper, link, summary, or idea, the agent must summarize, plan, implement, validate, and hand off according to `AGENTS.md`. |
| AGT-004 | The implementation must be ordinary product code and must remain inactive until its tests and reproducible example Run pass. |

Completion criterion: an agent can implement a documented technique end to end without adding an agent runtime or general plugin platform to the product.

