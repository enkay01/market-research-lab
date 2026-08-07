# Working Product Design

Status: accepted product baseline

## Product

Market Research Lab is a personal, local-first application for learning and applying equity research, valuation, technical analysis, and quantitative modelling. It helps the Analyst turn ideas into explicit, testable implementations, but it does not execute or route trades.

The first coverage universe is US-listed equities and ETFs using daily data. The architecture may later gain additional data sources and analytical techniques through normal code changes at stable module interfaces.

## Runtime

The application is one repository with two runtime parts:

- A Python engine owns data ingestion, validation, analytics, model training, backtesting, artifacts, and scheduled evaluation.
- A React and TypeScript interface owns interaction, visualization, and workflow orchestration.

FastAPI and Pydantic define the application boundary. External payloads, project commands, and filesystem inputs are validated there. Internal domain code receives trusted typed values and does not repeat boundary validation. The TypeScript client is generated from the OpenAPI description.

One command starts the local engine and opens the application in a browser. The production engine serves the built interface and API on one localhost origin. Vite provides the frontend development server.

`uv` manages Python dependencies, environments, and top-level project commands. Frontend packages retain their native lockfile; `uv` commands orchestrate the complete development workflow.

There is no authentication, cloud runtime, GitHub Pages deployment, cloud database, embedded LLM, broker integration, or order execution.

## Core flow

```text
Public API or local import
        |
        v
validated, versioned local data
        |
        +----> research thesis ----> valuation
        |
        +----> indicator or predictive model
                              |
                              v
                           strategy
                              |
                              v
                     portfolio backtest
                              |
                              v
                  artifacts and dashboards
                              |
                              v
                    in-app signal alerts
```

## Projects and files

A Project is a durable research workspace that may contain many Securities, Research Theses, Valuations, Indicators, Predictive Models, Strategies, Runs, and reports. Projects share the machine's market-data catalogue rather than copying large datasets.

Authored material remains inspectable on disk. Each definition has a mutable draft and immutable `v1`, `v2`, and later revision directories. Runs and generated outputs live in their own artifact directories and identify the Definition Revisions and Dataset Versions they consumed. There is no application-level branching or merging.

DuckDB and Parquet form the shared analytical data layer. Project files, definitions, research, configuration, and result manifests remain ordinary readable files.

## Market data

The first data source uses a free public API with credentials stored in `.env.local`, alongside CSV, JSON, or Parquet imports. Provider-specific code returns canonical market records. Extract a formal adapter interface when a second provider makes the varying behavior concrete.

The ingestion path validates provider payloads, maps them to canonical schemas, and records provenance and availability times. Historical simulations can consume only data that was available at the simulated decision time. Raw and adjusted prices remain distinguishable, and corporate actions are explicit.

The initial required data is security identity, daily OHLCV, splits, dividends, and quarterly and annual financial statements. Provider selection happens after these fields are specified precisely.

## Research

The Analyst can maintain a lightweight Research Thesis for each Security with Markdown narrative, evidence, risks, catalysts, assumptions, sources, and dated updates. Research links directly to relevant Valuations, Strategies, and results. Basic symbol search, filtering, and watchlists are sufficient; there is no screening subsystem or query builder.

An external development agent may receive a paper link, article, summary, or theoretical idea. Following `AGENTS.md`, it summarizes the technique, writes an implementation plan, implements the required data and analytical modules, tests temporal correctness, and produces a reproducible example Run. The application itself does not contain an agent or preserve an archive of research papers.

## Valuation

Valuation is a Python domain module with typed assumptions. Initial methods are FCFF discounted cash flow and comparable-company analysis. Results include scenarios, sensitivities, actual-versus-forecast periods, units, currency, provenance, and explicit warnings. Downloaded fundamentals seed editable model inputs; the application does not maintain a separate override ledger.

Additional valuation methods are implemented as new code satisfying the valuation interface and accompanied by tests and UI metadata. This is feature development, not plugin installation.

## Indicators and predictive modelling

Indicators and Predictive Models are code-first Python definitions with typed parameters exposed to the interface. Indicators produce time-aligned series. Predictive Models produce timestamped forecasts or scores with a named target and horizon. Neither directly creates simulated orders.

A Project may contain and compare multiple model types, including LightGBM and sentiment models. They share the Project's locked Python environment and may be combined or ensembled. If two techniques require irreconcilable dependency versions, they use separate Projects initially. Code is written in the Analyst's IDE; the application provides parameter controls and results, not a code editor or notebook layer.

Training uses chronological splits and rolling or expanding walk-forward evaluation. Preprocessing is fitted inside each training window. Model artifacts, seeds, features, revisions, Dataset Versions, and out-of-sample metrics are recorded in artifact directories.

## Strategies and backtesting

A Strategy converts eligible Indicators, predictions, and market observations into desired portfolio weights. An Execution Model converts weight changes into simulated orders and fills. This separation prevents trading assumptions from being hidden inside research logic.

Backtesting is its own Epic. Its target scope is multi-Security long and short portfolios with leverage, margin constraints, commissions, slippage, borrow costs and availability, cash interest, dividends, splits, delistings, and explicit trade rejections. Implementation may proceed in smaller stories, beginning with one Security and long/flat positions while retaining the same portfolio result model.

For daily strategies, a Signal computed from a completed bar is executable no earlier than the next eligible bar by default. Standard weekends and exchange holidays are baseline behavior. Multi-exchange sessions, half-days, and exceptional closures may follow later.

Look-ahead protection is structural: temporal data queries take an as-of time, model fitting receives bounded training windows, Signals record their decision time, and fills validate that their inputs and price were eligible.

## Jobs, reports, and alerts

Imports, training, backtests, and report generation are backend tasks. The Python engine runs them and the interface polls their status. Use direct subprocesses only for tasks that need isolation or cancellation; there is no generic queue framework.

Each completed Run produces an interactive dashboard, a local HTML report, CSV result tables, and a JSON manifest of data, definitions, assumptions, environment, warnings, and artifacts. Selected Runs or Valuations may be compared side by side; there is no dashboard builder.

When the engine is running, enabled Strategies may evaluate newly available data and place new Signals into an in-app alert list. Alerts reference the exact Strategy revision and market-data time. The Analyst reviews them and manually executes any trade outside the application, potentially using a phone. The application does not record the Analyst's trading decision.

## Delivery sequence

1. Local application shell, Project files, generated API client, and job foundation.
2. Shared data catalogue, imports, and one free public-data adapter.
3. Research Thesis workspace.
4. FCFF DCF and comparable-company Valuations.
5. Code-first Indicators and Run artifacts.
6. Backtesting Epic, delivered through progressively richer portfolio stories.
7. Predictive Models and agent-driven technique implementation.
8. Reporting dashboards and reproducible exports.
9. In-app scheduled Signal evaluation and Alerts.
