# Options testing capability gap audit

Research ticket: [Audit the lab options-testing capability gaps](https://github.com/enkay01/market-research-lab/issues/79)

## Scope

This audit compares the current lab with the minimum capability needed to run a reproducible historical Backtest Run of a two-leg US equity or ETF vertical credit spread. The test must be able to select contracts from information available at the decision time, enter both legs as one spread, mark and manage the open spread, and settle or close it without using later information.

The supplied technique adds concrete demands beyond a stock Backtest Run:

- Select a put or call vertical by expiration, strike width, short-leg delta, implied volatility, and liquidity.
- Enter for a net credit with both legs linked.
- Size from the spread's maximum loss and Portfolio allocation limits.
- Manage a stop ladder from the spread's replacement cost and elapsed time.
- Close, expire, assign, exercise, or roll the complete spread.
- Compare out-of-sample results after fills, commissions, slippage, assignment risk, and idle-capital treatment.

The labels below have strict meanings.

- **Present** means the capability satisfies part of this historical test now.
- **Reusable with change** means working code or a stable seam can carry forward, but its current contract cannot run the test.
- **Absent** means the repository has no domain implementation for the capability.

## Finding

The lab cannot run a credit-spread Backtest Run today. It has a useful equity backtesting base, but every option-specific capability is absent. The largest break is not the Strategy rule. The lab has no historical option contract or quote record that a Strategy or Execution Model could consume.

The reusable base is substantial. Dataset Versions, point-in-time rejection, deterministic replay, dated cash and position ledgers, persisted Runs, exports, and browser result views already exist. These parts reduce the work, but none is option-ready without a contract change.

## Capability matrix

| Area | Present | Reusable with change | Absent |
|---|---|---|---|
| Market Dataset records | Immutable Dataset Versions, source, retrieval time, coverage, warnings | File/provider ingestion and DuckDB/Parquet catalogue | Option contracts, quote snapshots, bid/ask sizes, open interest, option volume, Greeks, implied volatility, multiplier, exercise style, settlement, and deliverables |
| Temporal eligibility | `available_at` filtering and rejection of incomplete provenance | As-of query mechanism | Quote-time and contract-lifecycle eligibility rules, intraday eligibility, survivorship-safe chain discovery |
| Strategy | Registry, typed scalar parameters, rationale, decision time | Eligible Market View and revision storage | Spread intent, linked legs, quantity or risk budget, persistent position state, stop ladder, roll intent, expiry and assignment policy |
| Backtest clock and ledger | Deterministic dated replay, next-bar execution, cash and close marks | Event loop, warnings, cost attribution, metrics | Intraday quote clock, option market marks, expiration and exercise events, explicit order ledger |
| Multi-leg execution | Buy and sell fills for single Securities | Fill and rejection records | Atomic or controlled partial combo execution, net-credit limit fills, legging policy, spread bid/ask, per-contract fees |
| Portfolio | Cash, signed share positions, exposure, leverage, margin, interest | Ledger arithmetic and Portfolio metrics | Contract positions, premium cash flow, multiplier, defined-risk collateral, buying power, settlement and assignment shares, spread-level realized and unrealized P&L |
| Runs and revisions | Revision directories, Run IDs, status, artifacts, HTML/CSV/JSON export | Project storage and manifests | Verified revision loading, complete multi-dataset provenance, real software revision, option-data environment details |
| API | Validated backtest request and typed response | Existing endpoint and generated TypeScript client | Option Dataset routes, spread specification, option execution assumptions, contract and leg results |
| Browser and reports | Run setup, metrics, charts, trades, fills, ledger, warnings, manifest, comparisons | Existing Backtest view and report generators | Chain and spread selection, option inputs, leg and spread tables, expiry and assignment outcomes, stop and roll attribution |
| Regression checks | Equity leakage, next-bar, cost, corporate action, short, leverage, and replay checks | Synthetic and golden-test style | Option chain leakage, multi-leg fills, pricing, multiplier, collateral, stops, expiration, assignment, exercise, rolls, and contract adjustments |

## Market Dataset records and temporal eligibility

### Present

The catalogue has immutable Dataset Version metadata and stores larger observations as Parquet. Its canonical records are limited to Security, DailyBar, CorporateAction, FundamentalFact, and DatasetVersion. The design states the same boundary in [software-design.md](../../software-design.md#L78-L92). The code declares only three dataset families, `daily_bars`, `corporate_actions`, and `fundamentals`, in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L31-L34). `DailyBar` has OHLCV, source, retrieval time, `available_at`, units, and adjusted prices in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L68-L95).

The point-in-time guard is real. A historical query rejects a Dataset Version if any observation lacks a valid eligibility timestamp, then filters `available_at <= as_of` in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L403-L413) and [market_data.py](../../../engine/src/market_research_lab/market_data.py#L1109-L1140). The tests cover missing timestamps, invalid timestamps, exclusion of later observations, and immutable earlier queries in [test_market_data.py](../../../engine/tests/test_market_data.py#L82-L130) and [test_market_data.py](../../../engine/tests/test_market_data.py#L275-L369).

### Reusable with change

The ingestion path validates rows, writes one immutable Parquet file, records coverage, and persists validation warnings in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L608-L709). This machinery can store another canonical record family after its validation and query rules exist.

The current temporal rule is generic enough to reuse, but daily equity handling is too coarse for the technique. The provider maps a Tiingo end-of-day bar's eligibility to download retrieval time because Tiingo does not supply a publication timestamp in [providers.py](../../../engine/src/market_research_lab/providers.py#L198-L207). An options test needs the timestamp at which each quote and Greek could have been observed. A later download time does not establish that historical chain state.

### Absent

The ingestion discriminator recognizes a row only as a fundamental, corporate action, or OHLCV daily bar. It rejects any other shape in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L425-L441). `history()` always reconstructs `DailyBar` objects in [market_data.py](../../../engine/src/market_research_lab/market_data.py#L1142-L1184).

There is no record for:

- The option contract identity and its underlying Security.
- Put or call type, strike, expiration, multiplier, exercise style, settlement, or deliverable.
- Timestamped bid, ask, sizes, last, volume, open interest, implied volatility, or Greeks.
- The historical set of contracts that existed at each decision time.
- Earnings and ex-dividend timestamps needed by the technique's entry and assignment rules.
- Option contract adjustments after an underlying corporate action.

The only remote market provider returns daily equity bars and equity corporate actions. The other provider returns SEC facts. The dispatch is closed over those two request types in [downloads.py](../../../engine/src/market_research_lab/downloads.py#L19-L46), and the validated HTTP union exposes only Tiingo and SEC EDGAR in [provider_routes.py](../../../engine/src/market_research_lab/provider_routes.py#L23-L87). No option data provider or provider-neutral option import exists.

## Strategy outputs and state

### Present

Strategies use typed parameter metadata and emit a decision time, rationale, and intended weight. `MarketView` contains one Security ID, session dates, and prices. `StrategyTarget` contains one Security ID and one weight in [strategies.py](../../../engine/src/market_research_lab/strategies.py#L24-L86). The dispatcher evaluates named Python Strategies over eligible data in [strategies.py](../../../engine/src/market_research_lab/strategies.py#L695-L717).

### Reusable with change

The registry, Pydantic parameter validation, rationale, and point-in-time Market View pattern are useful. The saved Definition Revision path can also record a spread Strategy definition.

### Absent

The implemented `evaluate_strategy` signature has no state argument, even though the design's intended seam includes one in [software-design.md](../../software-design.md#L174-L182). Every implemented target is a scalar weight for one Security. The backtest divides that weight by universe size in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L1084-L1110).

A vertical credit spread needs an intended position that can identify two contracts, each side, contract count, entry credit rule, and joint risk. It also needs state across decisions for the original credit, entry time, DTE, maximum favorable state, current stop tier, and any roll chain. None of those values can be expressed by `StrategyTarget` or passed back into the current Strategy.

The current browser also assigns a revision label such as `long_flat_moving_average:v1` from local component state rather than choosing a saved revision. It only offers the two moving-average Strategies in [BacktestView.tsx](../../../web/src/views/BacktestView.tsx#L619-L631).

## Backtest clock and ledger

### Present

`run_backtest` is deterministic and accepts a specification plus supplied bars and corporate actions in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L528-L547). It requires `available_at` on every bar. It maintains cash, positions, pending targets, fills, trades, ledger rows, warnings, and rejections in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L549-L612).

The event loop applies corporate actions, accrues cash interest, fills prior targets at the current open, evaluates the Strategy, and marks positions at the close. Next-bar timing has an exact regression check in [test_backtest.py](../../../engine/tests/test_backtest.py#L162-L175). Deterministic replay and future-data invariance are checked in [test_backtest.py](../../../engine/tests/test_backtest.py#L210-L233).

### Reusable with change

The explicit event sequence, point-in-time Market View, pending intent, immutable ledger rows, warning collection, and pure runner are useful bases for a different event cadence.

### Absent

The clock has one row per Security per `session_date`. Indexing assigns `bars_by_symbol[security_id][session_date] = bar`, so a later observation for the same Security and date overwrites the earlier one in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L562-L565). The simulation dates are daily strings, and all pending fills use the next session's open in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L573-L591) and [backtest.py](../../../engine/src/market_research_lab/backtest.py#L749-L785).

This clock cannot faithfully determine which event happened first inside a session. That blocks tests of an intraday stop ladder, limit-order touch, bid/ask movement, short-strike breach, or an earnings exit at a stated timestamp. An end-of-day approximation could test a reduced technique, but it would not test the supplied stop protocol.

The result contains Signals, fills, trades, and ledger rows, but no explicit order records in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L177-L193). This is also a gap against BT-004, which requires orders in the dated ledger in [functional-requirements.md](../../functional-requirements.md#L102-L112).

## Multi-leg execution

### Present

The equity Execution Model can apply commissions and symmetric percentage slippage. A `Fill` records one Security, side, share quantity, price, notional, commission, and slippage in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L32-L83). It also records constraint rejections.

### Reusable with change

Fill, rejection, cost-attribution, and next-eligible-execution concepts carry over. The current regression checks establish a useful standard for exact money arithmetic in [test_backtest_regression.py](../../../engine/tests/test_backtest_regression.py#L127-L220).

### Absent

Execution reconciles independent share deltas. It deliberately sends sells before buys in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L773-L820), then creates one Fill at a time from an equity open price in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L833-L869) and [backtest.py](../../../engine/src/market_research_lab/backtest.py#L913-L1036).

There is no spread order, leg link, atomic fill policy, controlled partial-fill policy, net-credit limit, spread bid and ask, per-contract fee, or rejection of a fill that would leave one naked leg. The current sell-first rule would create exactly the temporary naked short exposure that the supplied technique forbids.

There is also no expiration, automatic exercise, early assignment, pin risk, or roll execution. A roll needs a linked close of the old spread and open of a new spread, plus a check that the combined transaction receives a net credit. The current trade lifecycle only opens and closes signed share positions.

## Portfolio accounting

### Present

The Portfolio is full-precision cash plus a dictionary of share quantities in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L200-L205). Each close mark calculates signed position value, gross exposure, net exposure, and Portfolio value in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L1254-L1305). The engine supports leverage limits, equity margin, borrow fees, cash interest, dividends, splits, delistings, and warnings.

### Reusable with change

Cash accounting, dated snapshots, aggregate risk metrics, cost attribution, and benchmark comparison are reusable. The current tests cover row arithmetic, costs, and exposure. For example, [test_backtest.py](../../../engine/tests/test_backtest.py#L200-L207) asserts `cash + position_value == portfolio_value`, and [test_backtest.py](../../../engine/tests/test_backtest.py#L335-L361) checks cost attribution.

### Absent

The Portfolio cannot represent a contract quantity or multiplier. It does not debit the long premium and credit the short premium as a linked opening transaction. It cannot reserve defined maximum-loss collateral, calculate buying-power use, or distinguish the option sleeve from core Security holdings and cash.

Marks use one equity price times shares. They do not value two option legs from executable bid and ask quotes or record spread-level realized and unrealized P&L. There is no settlement cash flow, assigned underlying share position, exercise decision, expiration outcome, or adjusted contract deliverable. Equity short-borrow rules are not a substitute for a short option's assignment and margin rules.

## Runs and Definition Revisions

### Present

`ProjectStore` writes immutable sequential revision directories with atomic replacement in [projects.py](../../../engine/src/market_research_lab/projects.py#L170-L238). It creates stable Run directories with status, manifest, log, and artifact locations in [projects.py](../../../engine/src/market_research_lab/projects.py#L355-L373). Completed Backtest Runs persist a result plus HTML, CSV, and JSON artifacts in [projects.py](../../../engine/src/market_research_lab/projects.py#L491-L525). Failed Backtest Runs keep a manifest, error artifact, and failed status in [projects.py](../../../engine/src/market_research_lab/projects.py#L527-L554).

### Reusable with change

The Project directory model and Run artifact model fit option research. `BacktestRunRecord` already accepts a list of Dataset Version IDs in [projects.py](../../../engine/src/market_research_lab/projects.py#L64-L71).

### Absent or incomplete

Current Backtest Run provenance is not sufficient for a reproducible option result:

- The API accepts `strategy_revision` from the request but does not read that revision before running. It uses request `strategy_name` and `parameters` directly in [api.py](../../../engine/src/market_research_lab/api.py#L2668-L2696). A caller can label arbitrary parameters with any revision string.
- The API reads corporate actions from every other corporate-action Dataset Version in the catalogue in [api.py](../../../engine/src/market_research_lab/api.py#L2649-L2666), but persists only the requested Dataset Version ID in [api.py](../../../engine/src/market_research_lab/api.py#L2709-L2716). Replaying the manifest cannot identify all consumed data.
- The Backtest specification has one `dataset_version_id`, not distinct identified inputs for underlying bars, option contracts, option quotes, corporate actions, earnings, and other calendars in [backtest.py](../../../engine/src/market_research_lab/backtest.py#L50-L67).
- Completed and failed Backtest manifests hard-code `software_revision` to `uncommitted`, and the environment contains only the Python version in [projects.py](../../../engine/src/market_research_lab/projects.py#L501-L509) and [projects.py](../../../engine/src/market_research_lab/projects.py#L535-L543).
- Completed Backtest artifacts are written directly into the live artifact directory, while the design requires temporary artifacts and an atomic rename in [software-design.md](../../software-design.md#L94-L114). The predictive-model path uses that safer pattern, but Backtest persistence does not.

These gaps already weaken equity replay. They become blocking when a Run consumes several large option Dataset Versions and a specific historical chain-selection rule.

## API boundary

### Present

FastAPI and Pydantic validate the current request. The Backtest endpoint accepts one Strategy name and revision label, one Dataset Version, one or more Security symbols, date bounds, starting cash, daily schedule, and equity execution assumptions in [api.py](../../../engine/src/market_research_lab/api.py#L892-L929). Responses expose fills, positions, trades, metrics, warnings, manifest, benchmark curve, and rejections in [api.py](../../../engine/src/market_research_lab/api.py#L932-L1065). The TypeScript client consumes generated schema types in [client.ts](../../../web/src/api/client.ts#L44-L58) and calls the saved Backtest endpoints in [client.ts](../../../web/src/api/client.ts#L389-L409).

### Reusable with change

The validated request-to-domain boundary, generated client, saved Run endpoints, exports, and Run comparison endpoint are suitable patterns.

### Absent

The API has no option contract, option quote, chain, expiration, spread, leg, premium, collateral, stop, assignment, exercise, or roll model. The execution request permits only a daily schedule and equity percentage costs. It cannot accept a net-credit limit, per-contract commission, quote-side fill rule, combo-fill rule, assignment assumption, or intraday stop policy.

The endpoint loads only `DailyBar` history and CorporateAction rows before it calls `run_backtest` in [api.py](../../../engine/src/market_research_lab/api.py#L2628-L2696). There is no route from an option Dataset Version to the runner.

## Browser views and reporting

### Present

The Backtest view can run and reload saved Runs. It shows headline metrics, equity and drawdown, trades, fills, daily ledger rows, rejections, a manifest, and side-by-side Run comparison. It exports HTML, CSV, and JSON in [BacktestView.tsx](../../../web/src/views/BacktestView.tsx#L487-L596). The report generator shows assumptions, Dataset Versions, warnings, rejections, metrics, costs, trades, fills, and daily marks in [reporting.py](../../../engine/src/market_research_lab/reporting.py#L802-L880) and [reporting.py](../../../engine/src/market_research_lab/reporting.py#L1001-L1176).

### Reusable with change

The result navigation, comparison flow, charts, tables, manifest inspection, and export controls are useful. The reporting module consumes typed results and does not recalculate the Backtest, as required by [software-design.md](../../software-design.md#L210-L214).

### Absent

The setup form only accepts Security symbols, one daily Dataset Version, two moving-average periods, bps costs, stock shorting, borrow, leverage, and equity margin in [BacktestView.tsx](../../../web/src/views/BacktestView.tsx#L608-L773). It has no way to inspect a historical option chain or configure DTE, delta, strike width, implied-volatility range, option volume, earnings timing, spread credit, risk per trade, active-spread allocation, stop ladder, profit exits, or rolls.

The result tables are equity-shaped. Trades show one Security, entry and exit price, and quantity. Fills show one Security and share-like quantity. The ledger shows shares and one close price. Reports cannot show linked legs, opening credit, current debit, width, maximum risk, collateral, DTE, Greeks, assignment, expiration, exercise, roll ancestry, or which exit rule fired.

The report also labels every Backtest result as `Out-of-sample` in [reporting.py](../../../engine/src/market_research_lab/reporting.py#L921-L939), and the browser repeats that assertion in [BacktestView.tsx](../../../web/src/views/BacktestView.tsx#L1260-L1269). The current runner does not establish a Strategy development sample or holdout boundary. That label should not be treated as proof of an out-of-sample credit-spread result.

## Regression checks

### Present

The equity suite has strong synthetic checks for the existing scope. It covers future-data leakage, next-bar fills, commissions, slippage, splits, dividends, short positions, borrow fees, leverage constraints, deterministic replay, margin, corporate actions, and API persistence. The consolidated regression file names these checks directly in [test_backtest_regression.py](../../../engine/tests/test_backtest_regression.py#L63-L127) and [test_backtest_regression.py](../../../engine/tests/test_backtest_regression.py#L470-L515).

I ran the relevant data, backtest, Project, and API suites from this branch:

```text
129 passed, 1 warning in 34.28s
```

The warning is a Starlette deprecation notice from the test environment. No test failed.

### Reusable with change

The synthetic-fixture style, exact ledger assertions, future-data mutation checks, golden replay equality, API workflow tests, and report checks are the right verification methods for option support.

### Absent

No Python or TypeScript test covers an option contract, quote, chain, spread, premium, or option lifecycle event. A credible vertical-spread test is still missing regression cases for:

- Point-in-time contract discovery and quote eligibility.
- Chain survivorship and expired-contract retention.
- Strike, expiration, DTE, delta, IV, volume, and bid/ask filters.
- Joint two-leg entry and exit, including rejected and partial combos.
- Contract multiplier, net credit, maximum loss, collateral, and buying power.
- Conservative bid/ask marks, per-contract commissions, and stop slippage.
- Stop-tier transitions with ambiguous intraday price paths.
- Profit exits, short-strike breach, and roll-for-credit rules.
- Expiration below, between, and above strikes for put and call spreads.
- Early assignment, exercise, pin handling, and resulting Security positions.
- Splits and other contract adjustments.
- Full-Portfolio allocation between option spreads, cash, and core holdings.
- Deterministic replay across all consumed Dataset Versions and the exact Definition Revision.
- Browser configuration, leg-level results, warnings, comparison, and export.

## Scope documents that must change before implementation

The repository still says that Securities are only listed equities and ETFs in [CONTEXT.md](../../../CONTEXT.md#L11-L13). The accepted requirements prohibit paid data integrations and any order submission in [functional-requirements.md](../../functional-requirements.md#L9-L20). The design explicitly defers paid providers, intraday data, derivatives, multi-asset accounting, and broker execution in [software-design.md](../../software-design.md#L248-L257).

The Wayfinder discussion has removed the paid-provider and broker-execution prohibitions. The repository documents have not caught up. This audit does not decide the replacement language or broker scope. It only records the mismatch because implementation against the current accepted requirements would violate them.

## Boundary of this audit

This document identifies capabilities and gaps. It does not choose a provider, data schema, pricing rule, assignment model, execution policy, or target module structure. Those are decisions for later Wayfinder tickets.
