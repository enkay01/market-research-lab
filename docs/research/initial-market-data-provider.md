# Initial free Market Dataset provider

Decision date: 2026-08-07  
Decision issue: [Select the initial free Market Dataset provider](https://github.com/enkay01/market-research-lab/issues/3)

## Decision

No single reviewed free API satisfies the accepted scope. Use **Tiingo Starter as the initial market-data provider**, complemented by **SEC EDGAR as the authoritative fundamentals source**.

- Tiingo supplies daily US equity and ETF OHLCV, raw and adjusted prices, split factors, cash dividends, and basic Security metadata. Its free Starter account provides 30+ years of price history, 500 unique symbols per month, 50 requests per hour, 1,000 requests per day, and 1 GB per month. [Tiingo pricing](https://www.tiingo.com/about/pricing) and [EOD API documentation](https://www.tiingo.com/documentation/end-of-day)
- SEC EDGAR supplies quarterly and annual company facts, filing identity, accession numbers, units, and filing/acceptance timing without an API key. The APIs update as filings are disseminated; bulk archives are available for deterministic acquisition. [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [Financial Statement Data Sets specification](https://www.sec.gov/dera/data/fsds.pdf)

Treat this as two explicit ingestion functions that produce the same canonical records, not as a general provider framework. Tiingo remains the named initial provider; EDGAR is a required public-source complement because every reviewed commercial free tier with usable prices paywalls or materially restricts fundamentals.

## Fit against the accepted scope

| Need | Source and treatment | Fit |
|---|---|---|
| Daily US equity and ETF OHLCV | Tiingo EOD returns raw OHLCV and separate adjusted OHLCV. Its catalogue includes US stocks, ETFs, and mutual funds. | Yes |
| Splits and dividends | Tiingo EOD rows include `splitFactor` and `divCash`; raw and adjusted values remain distinguishable. | Yes for effective events; announcement-time history is not supplied |
| Security identity | Tiingo EOD metadata supplies ticker, name, exchange code, description, and coverage dates; its supported-tickers file is refreshed daily. Create a local stable Security ID because a ticker is not a permanent identifier. | Yes, with local identity mapping |
| Quarterly and annual fundamentals | SEC Company Facts and filing archives expose structured XBRL facts for 10-Q and 10-K filings, with taxonomy, unit, fiscal-period, form, accession, and filing metadata. | Yes for SEC-reporting issuers |
| Market-availability timestamps | Use the EDGAR acceptance timestamp for fundamental facts. Use a conservative **20:00 America/New_York on the session date** for Tiingo daily bars because Tiingo says most prices arrive by 17:30 ET but exchange corrections may continue until 20:00 ET. | Yes for bars and SEC facts; limited for corporate-action announcements |
| Credentials | Tiingo requires an API token in `.env.local`. SEC public data requires no key, but requests must identify the client and follow fair-access guidance. | Yes |
| Reproducibility | Persist the exact raw payload or downloaded archive, request parameters, retrieval time, source URL, checksum, validation report, and resulting Dataset Version. Runs use the snapshot, never a fresh refetch. | Yes locally; neither upstream is immutable |

## Point-in-time rules

1. A Tiingo daily bar becomes eligible at 20:00 ET on its session date. This deliberately gives up same-evening timeliness in exchange for a documented correction boundary. Tiingo notes that most US equity prices arrive around 17:30 ET and corrections can continue until 20:00 ET. [Tiingo EOD availability](https://www.tiingo.com/documentation/end-of-day)
2. An SEC fundamental fact becomes eligible at the filing's EDGAR acceptance timestamp, not its fiscal-period end or a provider retrieval time. The SEC Financial Statement Data Sets define `accepted` as the Commission acceptance date and time; amendments are separate later observations. [SEC Financial Statement Data Sets](https://www.sec.gov/dera/data/fsds.pdf)
3. Company Facts provide normalized facts and accession links, while the filing metadata or quarterly Financial Statement Data Sets provide the acceptance time. Retain accession number and form so every fact can be traced to the filing. [SEC XBRL APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
4. Tiingo's EOD split/dividend fields identify the effective/ex-date event but do not establish when it was announced. They may drive portfolio accounting on the effective date, but must not be exposed to a Strategy as advance information. Any historical strategy that depends on announcement knowledge must reject these records for lack of temporal provenance.
5. Security metadata is eligible only from its recorded retrieval time unless the source record itself carries an earlier `startDate`/`endDate`. Do not reconstruct a historical universe from today's supported-ticker catalogue.

## Free-tier comparison

| Candidate | Free market data | Corporate actions and identity | Fundamentals | Limits and point-in-time result |
|---|---|---|---|---|
| **Tiingo Starter** | 30+ years EOD; raw and adjusted OHLCV; US stocks and ETFs | `divCash`, `splitFactor`, metadata, daily supported-ticker list | Full API is an add-on; free evaluation is limited to three years of Dow 30 companies | Best market-data fit: 500 symbols/month, 50 requests/hour, 1,000/day, 1 GB/month. EOD correction window is documented. [Pricing](https://www.tiingo.com/about/pricing), [EOD docs](https://www.tiingo.com/documentation/end-of-day), [fundamentals docs](https://www.tiingo.com/documentation/fundamentals) |
| Massive Stocks Basic | Two years of EOD US stock data, five calls/minute | Reference data, splits, and dividends are included | Financials cost $29/month separately or require the $199/month Stocks Advanced plan | Too little history for the default backtesting source and no free fundamentals. [Pricing](https://massive.com/pricing?product=stocks), [stock API](https://massive.com/docs/rest/stocks) |
| Alpha Vantage free | Raw daily OHLCV is free, but full daily history and Daily Adjusted are premium; the free key is limited to 25 calls/day | Search, dividend, and split endpoints exist | Annual and quarterly statement endpoints exist, but responses do not establish an acceptance timestamp suitable for historical eligibility | Inadequate free price history and throughput; fundamental temporal provenance is insufficient. [Documentation](https://www.alphavantage.co/documentation/), [limits](https://www.alphavantage.co/support/) |
| Twelve Data Basic | Daily time series and US equities/ETFs; EOD becomes available after midnight ET on the next trading day | Reference data is free | Splits, dividends, and fundamentals require Grow ($79/month list price) | Cannot meet actions or fundamentals at no cost. Basic provides 8 credits/minute and 800/day. [Pricing](https://twelvedata.com/pricing), [API docs](https://twelvedata.com/docs/advanced), [US EOD availability](https://support.twelvedata.com/en/articles/9935903-us-equities-market-data) |
| Financial Modeling Prep Basic | Five years of end-of-day history | Profile and reference data | Annual fundamentals begin at Starter; fuller fundamentals are on higher paid plans | Free plan is 250 calls/day and 500 MB/30 days, but does not meet the fundamental requirement. [Pricing](https://site.financialmodelingprep.com/developer/docs/pricing/) |
| SEC EDGAR | None | Company identity, ticker/exchange metadata, and filing history for reporting entities | Authoritative quarterly/annual XBRL facts, filing metadata, and bulk archives | Essential complement, not a market-price provider. No key; keep total automated access at or below 10 requests/second and prefer bulk archives. [API docs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces), [developer guidance](https://www.sec.gov/about/developer-resources) |

## Licensing and operational constraints

- Tiingo labels the free plan **Internal Use Only**: data may be used personally but not displayed or shared with another person or organization. Therefore the repository may contain the adapter and schemas, but must never commit downloaded Tiingo data or an API token. Each Analyst supplies their own token and accepts Tiingo's terms. [Tiingo pricing and license summary](https://www.tiingo.com/about/pricing)
- SEC data is publicly accessible without authentication, but automated access must comply with the SEC privacy/security and fair-access policy. Keep a descriptive `User-Agent`, prefer bulk archives, and remain below 10 requests/second. [SEC developer resources](https://www.sec.gov/about/developer-resources)
- Both sources can correct history. Dataset Versions must be content-addressed local snapshots; storing only provider URLs is not reproducible.
- The 500-unique-symbol Tiingo monthly cap is sufficient for analyst-selected Securities and small peer sets, not a full-universe backtest. A broad or survivorship-free universe is outside what this free choice can promise.

## Requirements this choice cannot satisfy

1. **One-provider purity:** fundamentals require SEC EDGAR; Tiingo's complete fundamentals API is paid.
2. **Corporate-action announcement-time research:** EOD rows lack historical announcement availability, so those records cannot support anticipatory Strategies.
3. **Non-SEC issuers and ETF fundamentals:** EDGAR coverage follows regulatory filings and does not provide normalized operating fundamentals for every Security type. Missing fundamentals must be explicit, not imputed.
4. **Full-universe research:** Tiingo Starter caps unique symbols at 500 per month.
5. **Upstream immutable replay:** exact reproduction depends on retaining raw local snapshots because provider corrections can change later downloads.
6. **Redistribution or multi-user use:** Tiingo Starter is for internal personal use only.

These are accepted constraints for the local, single-Analyst first release. Historical Runs must reject any observation whose eligibility cannot be proven under the rules above.
