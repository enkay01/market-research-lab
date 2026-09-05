# Implementation Plan

Status: ready for execution

Each Epic ends with a runnable product increment. Implement one story at a time; do not scaffold later Epics early.

## Epic 1 — Local foundation

Outcome: one command opens an empty local Project interface backed by a validated Python application interface.

Stories:

1. Create the `uv` Python project and Vite React/TypeScript project.
2. Add top-level `uv` commands for development, checks, build, and local startup.
3. Serve the built interface from FastAPI in production mode.
4. Generate the TypeScript client from OpenAPI.
5. Create/open a Project and persist `project.json` atomically.
6. Add draft-to-`v1` revision saving and Run artifact directories.

Done when one command opens the browser, creates a Project, saves a revision, and restores it after restart.

## Epic 2 — Trusted market data

Outcome: daily equity data enters the local catalogue with enough provenance for point-in-time use.

Stories:

1. Define canonical Security, DailyBar, CorporateAction, FundamentalFact, and DatasetVersion records.
2. Create DuckDB/Parquet storage and coverage inspection.
3. Import CSV first, then JSON and Parquet.
4. Add future-data rejection tests using a tiny synthetic dataset.
5. Spike free providers against the required fields and terms; select the smallest viable option.
6. Implement the selected free provider using `.env.local` credentials.
7. Display coverage, validation failures, warnings, and Dataset Versions.

Done when the same historical as-of query never changes after later observations are added to its Dataset Version inputs.

## Epic 3 — Research and valuation

Outcome: the Analyst can form a thesis and produce reproducible DCF and peer valuations for one Security.

Stories:

1. Add symbol/name search, a watchlist, and the Security view.
2. Store and edit lightweight Markdown Research Theses.
3. Implement the pure FCFF DCF method with calculation checks.
4. Add editable forecast inputs, three scenarios, and sensitivity results.
5. Implement trading comparables with an analyst-selected peer set.
6. Save Valuation revisions and compare selected results.
7. Export valuation result data and its manifest.

Done when one Security can move from watchlist to thesis to two reproducible valuation methods.

## Epic 4 — Indicator-to-report vertical slice

Outcome: the agreed MVP workflow works end to end before the full Backtesting Epic expands.

Stories:

1. Define the code-first Indicator function and typed parameter metadata.
2. Implement one moving-average Indicator and preview it against price history.
3. Implement one long/flat moving-average Strategy that emits target weights.
4. Build the minimum single-Security portfolio ledger and next-bar Execution Model.
5. Produce Signals, fills, costs, equity, drawdown, and core metrics.
6. Add future-data and deterministic-replay golden checks.
7. Build the Backtest dashboard and HTML/CSV/JSON exports.

Done when import → research → valuation → Indicator → Strategy → Backtest Run → report works from the interface on real daily data.

## Epic 5 — Backtesting engine

Outcome: the basic runner becomes the target long/short portfolio simulator without changing its external interface.

Stories:

1. Multiple Securities and target-weight reconciliation.
2. Long-only portfolio constraints and benchmark comparison.
3. Short positions, borrow availability, and borrow cost.
4. Gross/net exposure, leverage, margin limits, and rejected trades.
5. Commissions, configurable slippage, and cash interest.
6. Splits, dividends, and delistings.
7. Standard exchange calendars and missing-session behavior.
8. Full metric set, cost attribution, exposure, turnover, and side-by-side Run comparison.
9. Synthetic regression checks for every accounting and temporal rule.
10. Daily Dataset Version compatibility checks in the interface and FastAPI.
11. Cross-sectional Strategy evaluation with deterministic Candidate Rankings, top-N selection, and recorded weights.
12. Dated Universe Snapshots with explicit coverage failures when historical membership is missing.
13. Broad-market daily download estimates, reusable local response caching, and incremental refresh.

Done when two identical long/short Runs produce identical ledgers and future observations cannot alter earlier Signals or fills.

## Epic 6 — Predictive modelling

Outcome: a modelling technique can train and evaluate safely, then feed a Strategy.

Stories:

1. Define fit/predict functions and artifact storage.
2. Implement chronological train/validation/test splits.
3. Implement rolling or expanding walk-forward execution with fold-local preprocessing.
4. Add naive benchmarks and separate in-sample/out-of-sample metrics.
5. Implement the first simple predictive baseline before LightGBM.
6. Add LightGBM only when the baseline pipeline is proven.
7. Compare and combine compatible model outputs in a Strategy.
8. Verify the `AGENTS.md` workflow by implementing one published technique end to end.

Done when an external agent can add one technique whose reproducible out-of-sample Run passes leakage checks and appears in the interface.

## Epic 7 — Signals and Alerts

Outcome: an enabled Strategy can evaluate fresh local data and present an actionable but non-executable Signal.

Stories:

1. Mark a validated Strategy revision as enabled.
2. Refresh its required data while the engine is running.
3. Evaluate the Strategy at the latest eligible decision time.
4. Display new Signals in the in-app Alert list with rationale and provenance.
5. Display stale-data and offline-engine states clearly.

Done when fresh data produces a traceable Alert and the codebase contains no route to broker execution.

## Epic 8 — Workspace cleanup

Outcome: the Analyst can remove app-owned generated Runs and imported or downloaded Dataset Versions without breaking Run provenance by accident.

Stories:

1. Add Project Run summaries and deletion behind the ProjectStore seam.
2. Add guarded Dataset Version deletion for catalogue metadata and owned Parquet files.
3. Add Cleanup view actions for Project Runs, Dataset Versions, and whole Projects.
4. Add confirmation and clear errors for missing items and Dataset Versions still referenced by Runs.
5. Add API and storage regression checks for successful deletion, reference protection, and file cleanup.

Done when the Analyst can remove a failed or completed Run, remove an unused imported or downloaded Dataset Version, and delete a whole Project from the interface.

## Epic 9 — Options credit-spread Backtest

Outcome: the Analyst can replay a Put Credit Spread against named Alpaca minute data and inspect the result without any execution path.

Stories:

1. Add typed Option Contracts, trades, underlying minutes, and eligible event records.
2. Add Alpaca Basic download and options Dataset Version persistence.
3. Add local implied volatility and Greek calculations.
4. Add automatic contract selection and the agreed entry rules.
5. Add worst and best linked-leg fills, collateral, fees, sizing, limits, and rejections.
6. Add stop ladder, profit, breach, earnings, expiration, gap, and counterfactual rules.
7. Persist options Runs, Definition Revision and Dataset Version inputs, source fingerprints, and exports.
8. Add the candlestick master-detail view, ledger, audit tray, warnings, and blocked candidates.
9. Verify deterministic replay, future-data isolation, and the reference Run gates.

Done when a named options Dataset Version produces a saved, reloadable, exportable, deterministic Put Credit Spread Run with worst and best supported paths.

## Definition of done for every story

- The relevant requirement IDs are named in the change plan.
- Trust-boundary validation and user-visible errors are present where input enters the system.
- Non-trivial money, temporal, parser, or branching logic has a runnable regression check.
- New domain language is reflected in `CONTEXT.md`.
- Durable trade-offs that meet the ADR threshold are recorded once.
- Documentation describes only behavior or reasoning that the code cannot state reliably itself.
