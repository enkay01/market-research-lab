# Stacked implementation plan for issues 99 and 101

## Stack

1. Issue #99 uses `origin/main` at `7e396e297b1e85990b9cc7689c46fe214e16b7d0` as its fixed review point. Its pull request targets `main`.
2. Issue #101 starts from the final reviewed issue #99 commit. Its pull request targets the issue #99 branch.

## Issue #99: deepen Option Backtest internal seams

The public `run_option_backtest` function, `OptionsBacktestSpecification`, result types, API, persistence, UI, and Definition Revisions do not change.

| Requirement | Code module | Test | Check |
|---|---|---|---|
| Isolate Black-Scholes pricing, implied volatility bisection, and analytical Greeks. | `engine/src/market_research_lab/option_pricing.py` | `engine/tests/test_option_pricing.py` | Known-value pricing, volatility recovery, Greek values, and invalid input cases pass. |
| Isolate DTE, Delta, width, trend, and pullback candidate rules. | `engine/src/market_research_lab/option_spread_selection.py` | `engine/tests/test_option_spread_selection.py` | Synthetic contracts and daily bars accept and reject candidates for each rule. |
| Use explicit state for entry, trailing profit changes, stop loss, and expiration. | `engine/src/market_research_lab/option_position_lifecycle.py` | `engine/tests/test_option_position_lifecycle.py` | Deterministic minute sequences produce the expected state transitions and settlement. |
| Separate post-exit counterfactual results from replay. | `engine/src/market_research_lab/option_counterfactual.py` | `engine/tests/test_option_counterfactual.py` | Synthetic post-exit prices produce exact recovery and expiration results. |
| Preserve the external behavior. | `engine/src/market_research_lab/option_backtest.py` | `engine/tests/test_options_backtest.py` and `engine/tests/test_api_options.py` | Existing golden and API checks pass without contract changes. |

Risks are numerical drift at pricing boundaries, a change in candidate rejection order, stale-price use, future-data leakage, and a lifecycle transition that changes the primary worst-price path. Tests use fixed Option Contracts, minute trades, daily bars, earnings facts, and direct state values. They do not need network or filesystem doubles.

Python design-patterns decision: use frozen dataclasses and functions. The lifecycle has real state variation, so explicit state values and transition results are justified. The pricing and selection modules each have one implementation. Do not add factories, abstract base classes, or provider interfaces.

## Issue #101: consolidate Predictive Model evaluation

Add `engine/src/market_research_lab/model_evaluation.py` as the single owner of chronological splits, walk-forward fold execution, fold-local fitting, metric calculation, and Naive Benchmark comparison. Keep model registry, parameter parsing, supervised-frame construction, and each Predictive Model's fit and forecast callables in `predictive_models.py`.

| Requirement | Code module | Test | Check |
|---|---|---|---|
| Consolidate holdout, expanding, and rolling splits. | `model_evaluation.py`; remove duplicate orchestration from `predictive_models.py` | Add focused `test_model_evaluation.py`; retain `test_predictive_models.py` | Exact split dates, training bounds, and fold counts pass for synthetic chronological data. |
| Fit features and preprocessing inside each eligible training fold. | `model_evaluation.py` with injected typed fit and forecast callables | Leakage checks in `test_model_evaluation.py` and `test_predictive_models.py` | Later observations do not change earlier folds. Labels unavailable at prediction time never enter training. |
| Unify zero-return, historical-mean, and persistence benchmarks. | `model_evaluation.py` | Parameterized benchmark checks in `test_model_evaluation.py` | Each benchmark uses the same labelled period keys as the Predictive Model and rejects misalignment. |
| Keep Predictive Model implementations limited to fitting and forecasting. | `predictive_models.py` | `test_predictive_models.py` and `test_potts_predictive_model.py` | Momentum and Potts Models use the same runner and keep their current public results. |
| Preserve API and saved result compatibility. | Existing API and persistence adapters consume unchanged result types | `test_predictive_model_api.py` and `test_predictive_model_persistence.py` | Response and stored JSON checks pass without schema regeneration changes. |

Risks are look-ahead leakage, label leakage across the forecast horizon, inconsistent period alignment, rolling-window off-by-one errors, benchmark use of future values, changed serialized output, and model-specific branching that remains in the runner. Test data uses short dated DailyBar sequences whose future values can be changed to prove isolation. Fit and forecast callables are passed directly as typed test doubles. No mock framework is needed.

Python design-patterns decision: use a Parameter Object for evaluation inputs because split policy, benchmark choice, frame data, and fit and forecast callables travel together. Use callable injection for the model boundary. Do not add a class hierarchy or Factory because the existing registry already selects Predictive Models and only one evaluation algorithm owns the execution flow.

## Verification for each stack layer

Run focused tests first. Then run `uv run --project engine market-research-lab-check` and `uv run --project engine market-research-lab-build`. Run the global anti-slop checker against the worktree. Run `git diff --check`, inspect the three-dot diff and commit list from the fixed point, and confirm that no secret, generated cache, or unrelated file entered the change.

Run separate Standards and Spec reviews against each layer's fixed point. Fix all actionable findings in the same branch, repeat affected focused checks, and repeat full checks and anti-slop before push.
