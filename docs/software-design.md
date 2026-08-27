# Software Design

Status: implementation baseline

This document owns module seams, data ownership, and execution flow. Product behavior is specified in [`functional-requirements.md`](./functional-requirements.md); durable trade-offs are recorded in [`adr/`](./adr/).

## Shape

The product is a local modular monolith:

```text
Browser: React + TypeScript
             |
     generated HTTP client
             |
FastAPI/Pydantic application interface
             |
Python domain modules
             |
DuckDB + Parquet + readable Project files
```

The interface validates untrusted values and converts them to internal domain values. Domain modules contain calculations and return results; they do not depend on FastAPI, the browser, or filesystem layout.

Production uses one localhost origin: FastAPI serves the built Vite assets and JSON endpoints. Development uses Vite with a proxy to FastAPI. `uv` manages Python and top-level commands; the frontend keeps its native package lock.

## Initial repository shape

```text
AGENTS.md
CONTEXT.md
docs/
engine/
  pyproject.toml
  src/market_research_lab/
    api.py
    projects.py
    market_data.py
    research.py
    valuation/
    analytics/
    backtest/
    reporting.py
    alerts.py
web/
  package.json
  src/
workspace/                 # local data; ignored by Git
  catalogue.duckdb
  datasets/
  projects/
```

Start with these modules. Split a file only when its implementation develops a distinct interface or becomes difficult to navigate.

## Application interface

FastAPI owns transport, Pydantic request/response models, path validation, and error translation. It calls domain modules with trusted values and maps results back to response models.

The interface groups operations by Project, data, research, valuation, definitions, Runs, reports, and Alerts. OpenAPI generates the TypeScript client. The browser does not reconstruct domain calculations.

Errors use a small stable shape:

```json
{
  "code": "point_in_time_data_required",
  "message": "Fundamental observations lack market-availability timestamps.",
  "details": {}
}
```

Expected validation or domain failures use typed error codes. Unexpected failures keep a traceback in the backend log and return a Run or request identifier.

## Storage ownership

### Shared data catalogue

DuckDB owns canonical tabular metadata and queries. Parquet owns larger immutable observations. The catalogue records Dataset Versions and points to their files.

Minimum canonical records:

| Record | Required fields |
|---|---|
| Security | stable ID, symbol, name, exchange, currency |
| DailyBar | Security ID, session date, OHLCV, source, available-at time |
| CorporateAction | Security ID, type, effective date, value or factor, source, available-at time |
| FundamentalFact | Security ID, field, fiscal period, value, unit, filed-at/available-at time, source |
| DatasetVersion | ID, source, retrieval time, coverage, files, validation summary |

All historical consumers query through an as-of function that filters `available_at <= decision_time`. Derived values carry the latest eligibility time of their inputs. Missing eligibility is a domain error for historical use.

The first free provider and file imports are concrete ingestion functions returning canonical records. Introduce a provider interface only when the second remote provider reveals actual variation.

### Project files

Each Project is a readable directory:

```text
projects/<project>/
  project.json
  watchlist.json
  research/<security-id>.md
  definitions/<kind>/<name>/
    draft/
    v1/
    v2/
  runs/<run-id>/
    status.json
    manifest.json
    logs.txt
    artifacts/
```

Saving a revision writes a complete new directory and then atomically updates the draft metadata. Referenced revision directories are immutable. Artifacts are written to a temporary Run directory and renamed into place only after successful completion; failures retain logs and status but are never marked complete.

## Domain modules

### Projects

`projects.py` hides paths, atomic writes, revision numbering, and Run directory creation behind operations to create/open a Project, save a revision, create/read a Run, list Project Runs, and delete a Run. Tests exercise the same operations used by the application interface. Run deletion accepts only one Run ID inside the selected Project directory.

### Market data

`market_data.py` owns ingestion, validation, Dataset Version creation, coverage inspection, point-in-time queries, and deletion of Dataset Version metadata plus owned Parquet files. Provider-specific parsing remains internal until more than one provider requires a real seam. The application interface checks Project Run references before it calls Dataset Version deletion.

Its important interface is behavioral rather than class-heavy:

```python
ingest(source, request) -> DatasetVersion
coverage(dataset_version) -> CoverageReport
history(query, *, as_of) -> MarketFrame
fundamentals(query, *, as_of) -> FundamentalFrame
```

`history` and `fundamentals` never expose observations ineligible at `as_of`.

### Research

`research.py` reads and writes lightweight Markdown plus minimal structured metadata. It owns no analytics. Links to Valuations and Runs are identifiers resolved by the Projects module.

### Valuation

Valuation methods are pure functions registered by name:

```python
evaluate(method, inputs) -> ValuationResult
```

The method registry initially contains `fcff_dcf` and `trading_comparables`, making the seam real from the first release. Inputs and results are typed, serializable, and free of filesystem or interface concerns. Each method owns its validation, calculation warnings, and result tables behind this one interface.

### Indicators

Indicators are deterministic functions:

```python
calculate_indicator(name, market_frame, parameters) -> IndicatorSeries
```

The returned series retains the input time index and represents warm-up values as missing. Indicator implementations never query the catalogue themselves; the caller supplies eligible data.

### Predictive Models

Predictive Models use a small fit/predict seam:

```python
artifact = fit_model(name, training_frame, parameters, seed)
predictions = predict(artifact, eligible_frame)
```

The walk-forward runner owns chronological folds and calls feature fitting inside each training fold. Model implementations receive bounded data rather than filtering dates themselves. Artifacts and predictions are serializable into the Run directory.

Each Predictive Model Run also stores one named Naive Benchmark, model and benchmark metrics for training, validation, and out-of-sample periods, and the assumptions, warnings, limitations, and unsupported claims used to interpret the comparison. The benchmark uses the same labelled eligible periods as the model. A Strategy guard reads this persisted evaluation and rejects model output until the out-of-sample comparison is complete.

### Strategies

Strategies receive a read-only view restricted to a decision time and return target weights:

```python
targets = evaluate_strategy(name, market_view, state, parameters)
```

The interface returns desired weights rather than orders. This keeps Indicators and Predictive Models reusable and moves fill assumptions into the Execution Model.

### Backtesting

The backtest module is a deep module with one primary interface:

```python
run_backtest(specification, *, bars) -> BacktestResult
```

The caller supplies the point-in-time-eligible `DailyBar` history (mirroring the
Indicators seam: the module never queries the catalogue itself), so the engine
stays testable with synthetic data. The implementation owns the event loop,
calendar, Strategy evaluation, target reconciliation, simulated orders and fills,
corporate actions, portfolio ledger, constraints, metrics, and artifacts.

Daily event order is explicit:

1. Apply events eligible before the decision time.
2. Build a Market View limited to that time.
3. Evaluate the Strategy and record its Signal.
4. Schedule target changes for the next eligible execution time.
5. Apply the Execution Model to produce fills or rejections.
6. Update cash, positions, costs, and portfolio value.
7. Append immutable ledger and metric rows.

The first implementation supports one Security and long/flat weights. Later stories deepen the same module with multiple positions, shorts, leverage, borrow, and richer corporate actions; callers retain the same `run_backtest` interface.

### Options Backtesting

`option_backtest.py` is a focused domain module for the first derivatives slice. It owns typed Option Contracts, minute trades, local Black-Scholes calculations, Put Credit Spread selection, linked-leg pricing, stop and exit rules, collateral, risk limits, reliability, and counterfactual diagnostics. Its primary interface is:

```python
run_option_backtest(specification, *, market_data) -> OptionsBacktestResult
```

`OptionMarketData` is loaded from one named Option Dataset Version. It may include named daily bars and earnings facts for the rules that use them. The module does not access FastAPI, the browser, the provider, or the filesystem. It uses completed option trade ranges because historical Alpaca buyer and seller quotes are not available. The worst supported path is primary; the best path is retained for comparison.

Options Runs use `kind: options_backtest`, share ProjectStore persistence, and record each input Dataset Version by purpose. They never route or submit orders. Assignment, rolling, and call spreads remain outside the first slice.

### Reporting and Alerts

`reporting.py` converts typed results into dashboard response data, HTML, CSV, and JSON. It does not recalculate analytics.

`alerts.py` evaluates enabled Strategies against the latest eligible data and writes new Signals to the Project's Alert list. It has no execution integration or decision journal.

## Backend tasks

Imports, model training, Backtest Runs, and report generation execute in the Python backend. A Run starts with `status.json`, performs work, writes logs and artifacts, then atomically marks itself complete or failed. The browser polls Run status.

Allow one heavy task at a time initially. Use a standard-library subprocess only when isolation or cancellation is required. Add parallel scheduling only after measured demand.

## Frontend

The interface has eight focused areas:

1. Project overview and watchlist
2. Data coverage and import/download
3. Security research
4. Valuation
5. Indicators and Predictive Models
6. Backtests and reports
7. Alerts

The Cleanup view lists Project Runs and shared Dataset Versions. It requires an explicit confirmation for deletion. A Dataset Version that a Run references stays protected until the Analyst deletes that Run. Deleting a Project remains the Project-level option for removing all Project files together.

Forms are generated from typed parameter metadata where practical. Curated visualizations consume backend result tables. The browser may format values for display but does not calculate valuations, indicators, model metrics, or backtest results.

## Correctness strategy

The smallest useful verification layers are:

- Pure calculation checks for Valuation, Indicators, metrics, and ledger arithmetic.
- Synthetic temporal datasets that make leakage immediately observable.
- Golden Backtest Runs with exact expected Signals, fills, cash, positions, and equity.
- Interface contract checks against generated TypeScript types.
- One end-to-end workflow: ingest data, write research, value, calculate an Indicator, backtest, and open the report.

Every money or temporal defect receives a regression check at the deepest module interface that exposes it.

## Deferred deliberately

- Runtime plugin framework
- Embedded agent or LLM
- Browser code editor or notebook environment
- Generic distributed task queue
- Dashboard builder
- Cloud synchronization and collaboration
- Mobile application and broker execution
- Paid providers, intraday data, derivatives, and multi-asset accounting
