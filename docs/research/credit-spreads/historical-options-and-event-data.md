# Historical options and event data for credit-spread research

Status: research finding  
Evidence checked: 2026-08-23  
Wayfinder ticket: [Identify viable historical options and event data sources](https://github.com/enkay01/market-research-lab/issues/78)

## Finding

Several current providers can supply enough US equity and ETF option data for a credit-spread Backtest Run. No public product description proves that one product supplies every required fact with point-in-time eligibility.

There are two practical data paths:

1. Buy a prepared chain dataset with bid and ask quotes, open interest, implied volatility, Greeks, underlying prices, and reference data.
2. Buy raw or normalized OPRA data, then join point-in-time contract definitions, underlying prices, dividends, interest rates, CorporateActions, and earnings-calendar vintages. Calculate implied volatility and Greeks locally.

End-of-day data can test entry selection and exits evaluated once per day. It cannot test an intraday stop rule faithfully. One-minute snapshots can test a bar-based stop approximation. Tick quotes can test quote-triggered stops, but the Execution Model must still define latency, leg order, partial fills, and slippage.

None of these datasets reports the assignment that would have happened to a simulated short option. The lab must model exercise and assignment from contract terms, moneyness, time, ex-dividend facts, and an explicit assignment rule.

## Required import contract

Before the lab accepts a Dataset Version for this technique, the import must preserve these fields or record why they are absent:

- Option Contract identity: provider identifier, raw OSI or OPRA symbol, underlying Security identifier, call or put, strike, expiration, exercise style, settlement type, multiplier, deliverables, listing time, and inactivation time.
- Market observation: event time, provider receive time when available, trade price and size, bid and ask price and size, exchange or NBBO source, condition codes, volume, and open interest effective date.
- Pricing inputs: time-aligned underlying bid and ask or trade, interest-rate input, dividend inputs, and any borrow or residual-yield input.
- Derived values: implied volatility, Greeks, pricing model, model version, input timestamps, and calculation status.
- Point-in-time facts: provider publication time, retrieval time, correction or revision identifier, and the earliest time at which the Analyst could use the record.
- Corporate facts: split, merger, spin-off, special dividend, symbol change, adjusted deliverable, and OCC memo or equivalent source.
- Earnings facts: expected date and time, before or after market classification, confirmation status, the time that version became known, later revisions, and the actual release time.
- Provenance: provider, product, license class, query or file name, checksum, schema version, time zone, and import code version.

The lab must keep each raw acquisition immutable. A later vendor correction must create a new Dataset Version or a patch layer. It must not alter a completed Backtest Run.

## Summary matrix

| Candidate | Documented cadence and history | IV and Greeks | Contract and survivorship support | Local access | Current public price | Main evidence gap |
| --- | --- | --- | --- | --- | --- | --- |
| OptionMetrics | EOD from 1996; three intraday cuts from 2018 | Included | Permanent IDs, delisted names, CorporateActions, daily patches | Locally hosted database | Quote | License, schema detail, and earnings vintages |
| Cboe DataShop | EOD, one-minute or custom intervals, and tick trades from 2012 | Optional | Root, expiry, strike, and type; adjusted roots need more reference data | CSV over SFTP | Configurator or quote | Permanent IDs, deliverables, corrections, and events |
| ORATS | Near EOD from 2007; one-minute from 2020; two-minute archive from 2015 | Included | Basic contract keys; known errata; lifecycle proof is incomplete | REST CSV or verified physical-drive CSV | $99 EOD API; $399 intraday API; $2,000 drive return option | Adjusted contracts, survivorship, and earnings vintages |
| ThetaData | EOD, minute, second, and tick from June 2012, subject to plan depth | Calculated | Underlying, expiry, strike, and right only in reviewed schema | Local terminal to CSV, JSON, or NDJSON | $40 to $160 individual; $1,600 commercial | Contract lifecycle, CorporateActions, revisions, and events |
| Massive | Minute, daily, and trades from 2014; tick quotes from 2022 | Current snapshots only | Active and expired contracts, as-of reference, exercise style, and deliverables | REST and S3 CSV | $0 to $199 individual; $1,999 business | Historical analytics, open interest, revisions, and schedule vintages |
| Databento | Schema-dependent OPRA history from 2013; consolidated tick NBBO from 2023 | Calculate locally | Timestamped definitions; no permanent cross-day contract ID | API and batch DBN, CSV, or JSON | Historical per GB; live Standard $199 | Contract terms, derived inputs, correction semantics, and exact cost |
| algoseek | Tick and minute market data from 2014; contract master from 2007 | Daily values included | Listed and delisted contracts, stable root IDs, settlement and deliverables | CSV, SQL, and REST | $3,000 monthly package on a two-year term | Earnings vintages, correction policy, and retained-use rights |

## Provider comparison

### OptionMetrics IvyDB US

OptionMetrics has the longest documented prepared end-of-day history in this review. [IvyDB US](https://optionmetrics.com/data-products/) covers US exchange-traded equity and index options, including ETF and ADR options, from January 1996. The daily data includes closing bid and ask quotes, volume, open interest, underlying prices, interest rates, dividends, CorporateActions, implied volatility, and delta, gamma, vega, and theta. OptionMetrics assigns permanent identifiers and carries symbol changes, splits, spin-offs, and securities that no longer trade. It issues daily patch files for corrections.

[IvyDB US Intraday](https://optionmetrics.com/wp-content/uploads/2025/07/OM_IvyDB-US_Intraday_Flyer_WEB.pdf) starts in 2018. It has synchronized cuts at 10:00, 14:00, and 15:45 ET, with bid and ask quotes, underlying prices, volume, implied volatility, and Greeks. Its public flyer does not list open interest for this intraday product.

Local reproducibility is feasible because OptionMetrics permits clients to host the database locally rather than access it only through a platform. Public pages do not state current prices, export limits, retention rights after termination, the full US file schema, or earnings-event coverage. Sales provides the quote and license terms.

Fit exposed by the evidence: prepared long-history end-of-day research, with a three-snapshot intraday extension. Evidence still needed: price, license, exact file delivery, retained-use rights, intraday open interest, exercise and settlement fields, and earnings-calendar vintages.

### Cboe DataShop

[Option EOD Summary](https://datashop.cboe.com/option-eod-summary) supplies a 15:45 ET snapshot and an end-of-day snapshot for US stock, ETF, and index options. It includes NBBO bid and ask with sizes, underlying bid and ask for stocks and ETFs, option OHLC, volume, VWAP, and open interest. Implied volatility and Greeks are optional. The product page states history from January 2012, while the [DataShop FAQ](https://datashop.cboe.com/faqs) says January 2010. A purchase should resolve this conflict before use.

[Option Quotes](https://datashop.cboe.com/option-quote-intervals) supplies one-minute or custom interval NBBO snapshots, sizes, OHLC, volume, optional open interest, and optional implied volatility and Greeks. History starts in January 2012. Cboe estimates one year of full-market one-minute data at about 2.3 TB compressed with calculations, or 1.2 TB without them. [Option Trades](https://datashop.cboe.com/option-trades) is a separate product with trade price, size, execution exchange, NBBO at trade time, underlying bid and ask, condition mappings, and optional trade Greeks.

Files arrive as CSV through SFTP. Cboe removes them from the SFTP folder after 30 days, so the lab must archive each file and checksum locally. The purchase form calculates a price from symbols, dates, cadence, calculations, open interest, customer type, and distribution rights. No stable public bundle price applies. The public pages do not describe permanent contract identifiers, a correction or restatement policy, full adjusted deliverables, delisted-underlying handling, or earnings events. Cboe notes that a digit in the option root identifies many non-standard contracts after a CorporateAction, but that fact alone does not describe the deliverable.

Fit exposed by the evidence: configurable exchange-source EOD, interval, and tick-trade files. Evidence still needed: exact quote, correction policy, retained-use terms, full contract master, adjusted deliverables, symbol lifecycle, and earnings-calendar vintages.

### ORATS

[ORATS EOD API](https://orats.com/data-api) supplies near-close chains from about 14 minutes before the close, with history from 2007. Fields include strike and expiration, call and put bid and ask, sizes, volume, open interest, stock price, bid, mid, and ask implied volatility, theoretical values, and Greeks. The same $99 per month individual delayed API tier documents dividend, earnings, split, and IV-rank history, with 20,000 requests per month.

[ORATS Intraday API](https://orats.com/intraday-data-api) supplies one-minute chain snapshots from August 2020. It lists more than 5,000 symbols, one-minute bid and ask chains, volume, open interest, implied volatility, Greeks, timestamps, and derived values. The individual live intraday tier is $399 per month with 1,000,000 requests. ORATS also offers [physical-drive delivery](https://orats.com/hard-drive-delivery). The current individual price is $2,000 plus a refundable $1,000 drive deposit for the one-minute archive from October 2020, with the 2015 to September 2020 two-minute archive as a $1,000 add-on. The files are gzip CSV and include SHA-256 manifests.

The drive documentation is unusually candid about data quality. The [one-minute README](https://orats.com/readme-1min.pdf) explains timestamp range changes and a historical index-derived-price issue. The raw quotes remain valid, but some old index Greeks and implied volatilities should only be used at specified five-minute timestamps. The [two-minute README](https://orats.com/readme-2min.pdf) includes an errata file for missing days, missing minutes, and low ticker counts.

The [earnings-history endpoint](https://orats.com/docs/historical-data-api) supplies an earnings date, before, after, during, or unknown time-of-day code, and an update timestamp. The public docs do not show the historical versions of expected dates that existed before each entry decision. They also do not prove full delisted-symbol coverage, permanent identifiers through mergers, adjusted deliverables, exercise style, a correction replacement policy, or API retention rights. The hard-drive page says that its purchase includes a data license. The OPRA delayed agreement prohibits redistribution outside the subscriber's organization.

Fit exposed by the evidence: prepared EOD and one-minute chains with local bulk delivery and known errata. Evidence still needed: point-in-time earnings schedule revisions, contract lifecycle and deliverables, assignment terms, survivorship, API revision semantics, and exact institutional license terms.

### ThetaData

[ThetaData options coverage](https://www.thetadata.net/options-data) states that it has every OPRA trade and NBBO quote, daily open interest, tick, one-second, one-minute, and end-of-day output, and history from June 2012. The [quote endpoint](https://docs.thetadata.us/operations/option_history_quote.html) returns timestamped NBBO price, size, exchange, and condition data for a contract or full chain. The [trade endpoint](https://docs.thetadata.us/operations/option_history_trade.html) returns every OPRA trade. Open interest is normally published once per day around 06:30 ET and represents the prior day's close. Greeks endpoints calculate first-, second-, and third-order values from time-aligned option and underlying midpoints.

The API runs through a local Theta Terminal and exports CSV, JSON, or NDJSON. Current individual option plans are $40, $80, and $160 per month for four, eight, and twelve years of history. Tick data starts at $80. Current commercial options pricing is $1,600 per month, billed annually, with startup discounts offered through sales.

The public schema identifies a contract by underlying symbol, expiration, strike, and right. The reviewed docs do not describe a permanent contract identifier, adjusted deliverables, exercise or settlement style, delisted-underlying coverage, CorporateActions, earnings events, correction history, export retention after cancellation, or reproducible bulk snapshot manifests. These are material gaps for adjusted contracts and point-in-time reruns.

Fit exposed by the evidence: low-cost local API access to tick and interval OPRA observations and calculated Greeks. Evidence still needed: contract and Security lifecycle data, CorporateActions, event data, correction behavior, commercial export terms, and immutable bulk acquisition.

### Massive

[Massive option flat files](https://massive.com/docs/flat-files/options/overview) provide daily downloadable CSV files through an S3-compatible interface. Minute and daily aggregates and trades go back to June 2014. [Tick quote files](https://massive.com/docs/flat-files/options/quotes) start on 2022-03-07 and use nanosecond timestamps. The full quote archive is large. The documented 2025 quote files total about 30.1 TB.

The [contract reference endpoint](https://massive.com/docs/rest/options/contracts) includes active and expired contracts, an as-of date filter, OSI-like tickers, correction number, call or put, strike, expiration, exercise style, shares per contract, exchange, and additional deliverables. Massive states that it carries OCC and OPRA contract changes after CorporateActions. Its current individual options plans cost $0, $29, $79, and $199 per month. Only the $199 tier includes historical tick quotes. Individual plans restrict use to the individual. The business options plan is $1,999 per month and documents more than ten years of trades but only about 2.5 years of quotes.

Historical flat files do not contain historical Greeks, implied volatility, or open interest. The snapshot endpoints expose current derived values and daily open interest, but the public docs do not establish a historical point-in-time series for them. The base option product also does not supply earnings events. Two separate $99 per month expansions can help: [Benzinga Earnings](https://massive.com/docs/rest/partners/benzinga/earnings) has dates, reported or scheduled times, confirmation status, last-updated timestamps, and history from 2010; [TMX Corporate Events](https://massive.com/docs/rest/partners/tmx/corporate-events) has status and event metadata from 2018. Neither public endpoint documents a complete archive of every prior schedule version.

The reviewed docs do not state a vendor restatement policy, historical snapshot manifests, or retained-use rights after cancellation. Local reproducibility requires saving the raw S3 objects, contract reference results as of each date, companion underlying and CorporateAction data, event responses, schemas, and checksums.

Fit exposed by the evidence: accessible raw minute and trade history, recent tick quotes, strong contract reference, and optional event APIs. Evidence still needed: historical Greeks and open interest, earnings-schedule vintages, correction policy, retained-use terms, and a practical storage plan for tick quotes.

### Databento OPRA.PILLAR

[Databento OPRA.PILLAR](https://databento.com/datasets/OPRA.PILLAR) covers 18 US option venues and advertises availability from 2013-04-01, although history varies by schema. It supplies trades, consolidated NBBO at tick, one-second, and one-minute cadences, OHLCV, statistics, status, and point-in-time definitions. Tick consolidated NBBO history starts later than the aggregate schemas. The [2025 normalization notice](https://databento.com/blog/opra-migration) states that CMBP-1 and TCBBO history starts on 2023-03-28.

Raw option symbols use OSI symbology. Parent symbology can fetch an entire chain. Definitions include strike, expiration, activation, contract class, and add, modify, or delete actions. Definitions are timestamped so an intraday Backtest Run can avoid knowing about a strike before it was listed. Instrument IDs are only guaranteed unique within one day, so the lab cannot use them as permanent Option Contract identifiers without its own lifecycle mapping. The statistics schema supplies start-of-day open interest. Databento also offers a separate point-in-time CorporateActions service with listed and delisted Securities.

Databento does not publish option implied volatility or Greeks in the OPRA schemas. The lab must calculate them after joining synchronized underlying data, rates, dividends, contract terms, and pricing-model choices. The reviewed definition docs say that expiration can have date-only precision. They do not establish exercise style, settlement method, or adjusted deliverables for every US equity Option Contract.

Historical data uses per-GB pricing and $125 of initial credit. Exact OPRA unit prices and request costs come from the authenticated catalogue or metadata API. A $199 per month OPRA Standard plan exists for live access, while historical pay-as-you-go remains available. Output supports DBN, CSV, and JSON through streaming or batch APIs. Batch files expire after 30 days but can be downloaded again during that period. Licensing and redistribution rights depend on the dataset and selected use in the License Manager.

The reviewed docs expose record quality flags and schema release notes, but not a historical-restatement policy that would let the lab reproduce an old response from the API alone. The lab must retain the bytes, metadata, schema version, and checksum.

Fit exposed by the evidence: high-resolution raw market records and genuinely point-in-time definitions. Evidence still needed: exact historical cost for the target universe, exercise and deliverable completeness, correction semantics, companion underlying and rate cost, and derived-value validation.

### algoseek US Options

[algoseek US Options](https://algoseek.com/options/) has OPRA trades, NBBO quotes, minute bars, open interest, daily Greeks, and reference data. Its full trade and quote archive starts in 2014. It preserves expired contracts for survivorship-bias-free research. Tick records include millisecond timestamps, exchange and condition codes, and trade-only data can include NBBO and underlying quotes at the trade time.

The [options contract security master](https://algoseek.com/docs/rest-api/reference/us-equity-opt-ref-sec-master-lookups) covers listed and delisted contracts from 2007. It includes root and underlying symbols, full contract ticker, call or put, strike, expiration, trading dates, settlement type, and adjusted-deliverable data. Detailed settlement coverage starts in 2018. A stable ASID exists at the option-root level, not necessarily for each strike and expiration. The separate OCC Listed Options Daily and Special Settlements datasets add listed-series and adjusted-deliverable facts. Daily option analytics use Black-Scholes-Merton for European options and a finite-difference method for American options.

Current published prices are $2,000 per month for tick trades and NBBO quotes, $1,800 for minute bars, and $1,200 for open interest. The 15-dataset Options Research Package is $3,000 per month on a two-year term and covers history from 2014. Historical subscriptions include the full archive and daily updates. The sandbox provides up to one year without a credit card. Delivery supports CSV, SQL, and REST queries.

The reviewed public docs do not state earnings-event coverage, earnings-calendar vintages, vendor correction and restatement handling, exact local export rights, or retained-use rights after the license ends. The pricing page says its displayed prices are samples, so a written quote remains necessary.

Fit exposed by the evidence: integrated raw market, reference, settlement, survivorship, and derived daily data. Evidence still needed: earnings data, correction policy, license and retention terms, final price, and whether every needed dataset can be exported and checksummed locally.

## Companion sources

An option provider may need one or more of these sources:

- [Wall Street Horizon DateBreaks](https://www.wallstreethorizon.com/upload/WSHDatebreaksSales.pdf) advertises optional point-in-time earnings-date history back to 2006, including prior, current, forecast, confirmed, and revised dates. This is the clearest documented answer to look-ahead bias in an earnings exclusion rule. Price, delivery format, time-of-day history, export rights, and retention terms require a quote.
- [OCC product and series data](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/data-sales) includes exercise style, classification, settlement method, underlying, activation and inactivation dates, expiration, strike, and listed exchanges. The non-distribution price is $1,750 per month. OCC also publishes [daily open interest](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest), [special-settlement and contract-adjustment memos](https://infomemo.theocc.com/infomemo/search), and other reports. Public report retention varies and is not a substitute for a licensed historical contract master.
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) provide free real-time filing dissemination metadata and nightly bulk files. They can verify when an 8-K or earnings exhibit became public. They do not provide a reliable future earnings schedule, and the filing acceptance time is not always the first public release time.

## Evidence gaps to resolve with samples and contracts

A short paid pilot should answer these questions before any provider decision:

1. Can the provider reproduce a full chain from a delisted Security and an adjusted contract, including its original deliverable and settlement method?
2. Does the option quote timestamp represent exchange event time, provider receive time, interval end, or file publication time?
3. Does an interval row carry the last quote, a time-weighted quote, or only a quote that changed inside the interval?
4. Are zero volume and zero open interest true zeros or missing messages? Which trade conditions count toward OHLC and volume?
5. Can the provider produce the original file and each later correction? Does a correction replace history or arrive as a patch?
6. Are calculated Greeks reproducible from documented inputs, model family, dividends, rates, borrow assumptions, and rounding rules?
7. Does the license allow permanent local retention for internal Backtest Runs, derived values, checksums, backups, and use after cancellation?
8. Can the lab export all selected symbols and dates without an undocumented row, request, or file limit?
9. Does the earnings product store every schedule version with its known-at timestamp, confirmation state, and before or after market time?
10. What exact quote applies to a small pilot universe, a broad US equity and ETF universe, and each required cadence?

## Minimum sample test

Do not judge a provider from AAPL and SPY alone. Request the same dates and symbols from each candidate:

- one liquid ETF with weeklies;
- one liquid single-name Security across an earnings release;
- one delisted Security;
- one split or merger that created a non-standard deliverable;
- one dividend-paying Security near ex-dividend date;
- one half trading day;
- one zero-volume but quoted Option Contract;
- one corrected or canceled trade if the source preserves it.

Hash the raw files. Import them into a temporary Dataset Version. Reconcile contract counts, NBBO, trades, volume, open interest, CorporateActions, and earnings-known-at times. Then run one EOD exit and one intraday stop scenario. This test will expose more than a provider sales matrix.

## Decision consequence

The next decision is not simply "which provider?" It is which data architecture the lab will support:

- a prepared-chain adapter that trusts and records vendor analytics;
- a raw-OPRA adapter with a local analytics pipeline;
- or both behind one canonical Option Contract and observation schema.

This research does not select a provider. It defines the facts that a provider pilot and license review must prove.
