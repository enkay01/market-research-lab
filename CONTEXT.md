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

**CorporateAction**:
A dated split, dividend, or other issuer action for a Security, including its effective date, value, units, source, retrieval time, and eligibility time.
_Avoid_: Adjustment, event

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

**Naive Benchmark**:
An explicit simple forecast rule that is evaluated over the same eligible periods as a Predictive Model for comparison.
_Avoid_: Hidden baseline, hindsight benchmark

**Strategy**:
Explicit decision and position rules that transform only information available at a simulated or evaluation time into intended actions.
_Avoid_: Algorithm, indicator, model

**Portfolio**:
The cash, positions, and resulting exposures governed together during a Backtest Run or Strategy evaluation.
_Avoid_: Account, book, watchlist

**Execution Model**:
The explicit assumptions and constraints that translate desired portfolio changes into simulated orders, fills, costs, and rejections.
_Avoid_: Strategy, broker, execution engine

**Cash Interest**:
A signed annualized Execution Model assumption applied to eligible cash-holding periods. A positive rate credits the Portfolio's cash. A negative rate charges it.
_Avoid_: Cash yield, funding cost

**Cost Attribution**:
A Backtest Run breakdown of commissions, slippage, borrow fees, and cash interest, with the Portfolio impact of each category and the net result.
_Avoid_: Total costs without categories

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

**Option Contract**:
One listed put or call contract with a Security, strike, expiration, multiplier, exercise style, and settlement type.
_Avoid_: Option position, leg

**Put Credit Spread**:
One short put and one lower-strike long put with the same Security and expiration.
_Avoid_: Credit spread without naming the legs

**Entry Credit**:
The money received when a Put Credit Spread opens.
_Avoid_: Premium yield

**Spread Value**:
The cost to close both legs at a supported historical minute price.
_Avoid_: Option price

**Stop Level**:
The Spread Value that tells the Strategy to close a spread.
_Avoid_: Stop order

**Full Possible Loss**:
The spread width less Entry Credit, multiplied by contract quantity and multiplier.
_Avoid_: Margin at risk

**Option Dataset Version**:
An immutable Dataset Version containing timestamped Option Contracts, option trades, underlying minute bars, and any event facts used by an options Backtest Run.
_Avoid_: Options feed
