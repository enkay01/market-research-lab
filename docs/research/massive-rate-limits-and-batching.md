# Massive rate limits and batching for market downloads

Status: research finding  
Evidence checked: 2026-08-31

## Finding

Massive Basic permits five REST requests per minute. Paid plans have unlimited REST requests, but Massive recommends that paid users stay below 100 requests per second. This rule applies to the free and paid product tiers described in Massive's current [REST rate-limit guidance](https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis). The current [Stocks pricing](https://massive.com/pricing?product=stocks) and [Options pricing](https://massive.com/pricing?product=options) pages confirm five requests per minute for each Basic plan and unlimited calls for each paid plan.

Massive does not state whether the Basic minute is a fixed window or a rolling window. Its public docs also do not document quota response headers, a reset header, or a guaranteed `Retry-After` header. The downloader must not depend on undocumented window or header behavior.

Use these request policies:

- Basic: one shared gate with 12.25 seconds between request starts. This sends about 4.90 requests per minute and leaves a small margin below the published maximum. Do not burst five requests and then sleep.
- Paid: one shared gate capped at 95 request starts per second. Begin with eight concurrent HTTP workers. The request-rate cap and worker limit solve different problems.
- HTTP 429: pause all Massive work. Use `Retry-After` if the response contains a valid value. If it does not, wait 60 seconds before the first retry, then use capped exponential backoff with jitter.

Stocks and Options subscriptions are separate. The application must store a plan profile for each asset class. One `request_interval_seconds` value cannot represent a paid Stocks plan and a Basic Options plan at the same time.

## What can be batched

| Repository need | Massive endpoint or delivery | Multiple securities in one request or file | Limit and pagination | Decision |
| --- | --- | --- | --- | --- |
| Historical stock daily bars | [`GET /v2/aggs/ticker/{stocksTicker}/range/...`](https://massive.com/docs/rest/stocks/aggregates/custom-bars) | No. The path contains one stock ticker. | Default 5,000 and maximum 50,000 base aggregates per page, with `next_url`. | Keep for narrow Security Lists and follow every page. |
| Historical stock daily bars | [`GET /v2/aggs/grouped/locale/us/market/stocks/{date}`](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary) | Yes. It returns all US stocks for one trading date. | One date per request. No ticker-list parameter. | Use only when requests per date are fewer than requests per selected ticker. Filter the response locally. |
| Historical stock minute bars | [`GET /v2/aggs/ticker/{stocksTicker}/range/...`](https://massive.com/docs/rest/stocks/aggregates/custom-bars) | No. | Maximum 50,000 base aggregates. | There is no historical multi-stock minute REST request in the reviewed docs. |
| Current stock or option state | [`GET /v3/snapshot`](https://massive.com/docs/rest/stocks/snapshots/unified-snapshot) | Yes. The official Python example passes `ticker_any_of` with stock and option tickers. | Maximum 250 results per page and `next_url` pagination. | Useful for current snapshots only. It cannot replace historical bars. |
| Current full stock market state | [`GET /v2/snapshot/locale/us/markets/stocks/tickers`](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot) | Yes. `tickers` accepts a comma-separated list. An empty value returns more than 10,000 active tickers. | No ticker-count maximum or pagination is documented. | Good current-state batching, but not historical data. |
| Stock reference records | [`GET /v3/reference/tickers`](https://massive.com/docs/rest/stocks/tickers/all-tickers) | It can list all matching records, but the docs show one exact ticker or range filters rather than a comma-separated exact list. | Default 100, maximum 1,000, with `next_url`. | Use for reference discovery, not historical prices. |
| Option contract reference | [`GET /v3/reference/options/contracts`](https://massive.com/docs/rest/options/contracts/all-contracts) | The endpoint can list many contracts, but the documented `underlying_ticker` filter takes one underlying. There is no documented exact-list filter for several underlyings. | Default 10, maximum 1,000, with `next_url`. | Fetch each selected underlying and follow every page. An unfiltered full contract scan is not a practical substitute for an exact batch. |
| Historical option aggregates | [`GET /v2/aggs/ticker/{optionsTicker}/range/...`](https://massive.com/docs/rest/options/aggregates/custom-bars) | No. The path contains one option contract. | Maximum 50,000 base aggregates. | One REST request per contract and date slice. |
| Historical option trades | [`GET /v3/trades/{optionsTicker}`](https://massive.com/docs/rest/options/trades-quotes/trades) | No. The path contains one option contract. | Default 1,000, maximum 50,000, with `next_url`. | One paginated stream per contract. |
| Current option chain | [`GET /v3/snapshot/options/{underlyingAsset}`](https://massive.com/docs/rest/options/snapshots/option-chain-snapshot) | It returns the current chain for one underlying. | Default 10, maximum 250, with `next_url`. | It does not provide historical chain bars or trades. |

The endpoint name is not enough to prove batching. The historical stock and option aggregate paths each require one ticker. A comma-separated list is not documented for either endpoint.

## Daily stock request choice

Let `S` be the selected Security count and `D` be the number of requested trading dates.

- Per-ticker custom bars need about `S` requests when each ticker fits below the 50,000-base limit.
- Grouped daily bars need `D` requests and return every US stock on each date.

Choose grouped daily only when `D` is meaningfully lower than `S`. For example, a broad 500-stock list over one year needs about 500 per-ticker requests or about 252 grouped-date requests. A 30-stock list over two years needs about 30 per-ticker requests or about 504 grouped-date requests, so grouping would make it much slower and download far more unused data.

This choice applies only to daily bars. Massive does not document a grouped historical minute endpoint.

## Bulk historical alternatives

Massive states that Flat Files are the bulk path for large historical jobs and REST is for smaller on-demand queries in its [Flat Files quickstart](https://massive.com/docs/flat-files/quickstart). Each compressed CSV file covers one trading date and all securities in that asset class. The importer can stream the file and keep only the requested Security List.

### Stocks

- [Stock day aggregate files](https://massive.com/docs/flat-files/stocks/day-aggregates) contain all US equities for one date. Stocks Starter, Developer, and Advanced include them. Basic does not.
- [Stock minute aggregate files](https://massive.com/docs/flat-files/stocks/minute-aggregates) contain all US equities at one-minute cadence for one date. Stocks Starter, Developer, and Advanced include them. Basic does not.
- Massive states that stock flat files contain unadjusted data. The importer must apply CorporateActions locally if it needs the adjusted values produced by `adjusted=true` REST requests. See the [Stocks Flat Files overview](https://massive.com/docs/flat-files/stocks/overview).

### Options

- [Option day aggregate files](https://massive.com/docs/flat-files/options/day-aggregates) contain all US option contracts for one date. Options Starter, Developer, and Advanced include them. Basic does not.
- [Option minute aggregate files](https://massive.com/docs/flat-files/options/minute-aggregates) contain all US option contracts for one date. Options Starter, Developer, and Advanced include them. Basic does not.
- [Option trade files](https://massive.com/docs/flat-files/options/trades) contain all OPRA trades for one date. Options Developer and Advanced include them. Basic and Starter do not.

Flat files batch market data, but they do not remove the need for point-in-time contract reference data. The importer still needs contract identity, expiration, strike, right, exercise style, multiplier, and adjusted deliverables for the contracts that survive local filtering.

## Consequences for the current downloader

The current Massive stock flow makes one custom-bars request per Security. That is the correct REST shape for historical minute bars and narrow daily downloads. It should not sleep outside `download_massive`, because option work can make many requests inside one call.

The current option flow first lists contracts for one underlying, then requests minute aggregates once for every returned contract. On Basic, one underlying can therefore consume far more than five requests. More threads would only create HTTP 429 responses. The UI must estimate the contract and page count before work starts and warn when a Basic request is impractical.

The implementation should select a transport before it schedules requests:

1. Narrow daily stock selection: per-ticker REST aggregates.
2. Broad daily stock selection where `D < S`: grouped daily REST aggregates.
3. Narrow minute stock selection: per-ticker REST aggregates.
4. Broad paid stock history: stock day or minute flat files.
5. Small paid option contract set: per-contract REST aggregates or trades with bounded concurrency.
6. Broad paid option history: option aggregate or trade flat files, then local ticker filtering.
7. Basic option history: keep REST serial at 12.25-second spacing and show the lower-bound duration before start. Do not present it as a fast bulk path.

Every pagination request counts as a request. The same shared gate must wrap custom date slices, option-contract pages, option aggregate calls, option-trade pages, retries, and any other Massive REST call. A provider-level sleep between Securities is not sufficient.

The HTTP seam must expose the response status and headers to the request controller. The current JSON-only result is not enough to coordinate a global 429 pause or use `Retry-After` when Massive sends it.

## Tests required before implementation

- A fake clock proves at least 12.25 seconds between all Basic request starts, including pagination and per-contract calls.
- A one-minute sliding observation window never contains more than five Basic starts.
- Paid scheduling never exceeds 95 starts in any one-second window and never exceeds the configured in-flight worker count.
- HTTP 429 stops new requests across every Massive worker. Tests cover `Retry-After` present, absent, and invalid.
- Daily planning selects per-ticker REST when `S <= D` and grouped daily when `D` is meaningfully lower than `S`.
- Grouped daily mapping keeps only requested Securities and restores Security List order.
- Minute-bar planning never selects grouped daily or the current snapshot endpoints.
- Contract and trade pagination follows every `next_url` through the shared gate.
- Flat-file planning rejects Basic plans and selects only data types included in the configured Stocks or Options plan.
- An Options Starter plan can select aggregate flat files but cannot select option trade flat files.

## Evidence gaps

Massive's public docs do not define the Basic rate-limit window, quota response headers, or a guaranteed retry delay. A short authenticated probe against the user's account can record status and response headers, but it must not be used to exceed five requests per minute. The conservative gate remains necessary unless Massive publishes a stronger contract.
