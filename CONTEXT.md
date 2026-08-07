# Market Research Lab

A personal workspace for researching listed securities, expressing market ideas as explicit models and strategies, and evaluating them reproducibly before acting outside the system.

## Language

**Analyst**:
The single person who researches securities, defines models and strategies, evaluates results, and receives alerts.
_Avoid_: User, trader, account

**Security**:
A listed equity or exchange-traded fund within the initial coverage universe.
_Avoid_: Stock, asset, instrument

**Market Dataset**:
A provenance-linked collection of historical market observations or company fundamentals available for analysis.
_Avoid_: Feed, data dump

**Dataset Version**:
An immutable identification of the exact Market Dataset state used by an analysis or simulation.
_Avoid_: Latest data, current data

**Research Thesis**:
An explicit investment case for or against a Security, including supporting evidence, assumptions, risks, and catalysts.
_Avoid_: Note, opinion

**Research Source**:
A summary, publication, paper, dataset description, or other cited material from which an investment claim or Modelling Technique is derived.
_Avoid_: Link, attachment, reference

**Modelling Technique**:
A documented market hypothesis or analytical method that can be translated into data preparation, feature construction, evaluation, and one or more Strategies.
_Avoid_: Model, paper, algorithm

**Valuation**:
An estimate of a Security's value produced from a named method, a Dataset Version, and explicit assumptions.
_Avoid_: Price target

**Indicator**:
A deterministic transformation of time-ordered market observations into a time-aligned derived series.
_Avoid_: Signal, metric

**Predictive Model**:
A fitted analytical definition that emits time-stamped forecasts or scores for a stated target and horizon without deciding portfolio positions.
_Avoid_: Strategy, model, indicator

**Strategy**:
Explicit decision and position rules that transform only information available at a simulated or evaluation time into intended actions.
_Avoid_: Algorithm, indicator, model

**Portfolio**:
The cash, positions, and resulting exposures governed together during a Backtest Run or Strategy evaluation.
_Avoid_: Account, book, watchlist

**Execution Model**:
The explicit assumptions and constraints that translate desired portfolio changes into simulated orders, fills, costs, and rejections.
_Avoid_: Strategy, broker, execution engine

**Signal**:
A time-stamped Strategy output that identifies an intended action or state without executing an order.
_Avoid_: Trade, alert

**Run**:
An immutable record of executing a saved definition against identified Dataset Versions and parameters, together with its status and artifacts.
_Avoid_: Experiment, job, result

**Backtest Run**:
A Run that reproducibly simulates one Strategy against historical data and explicit execution assumptions.
_Avoid_: Test, simulation result

**Alert**:
A local notification that a Signal satisfies criteria chosen by the Analyst; it never places or routes an order.
_Avoid_: Signal, order

**Definition Revision**:
An immutable, sequentially numbered snapshot of a Valuation, Indicator, Predictive Model, or Strategy definition that can be referenced by results and reproduced later.
_Avoid_: Draft, Git commit, Dataset Version
