# Download Tiingo prices and SEC EDGAR fundamentals locally

Status: Accepted
Decision date: 2026-08-11

## Context

Issue 16 requires the Analyst to acquire the initial free Market Dataset without a cloud or paid-data dependency. The provider selection research chose Tiingo for daily US equity and ETF prices and corporate-action fields, with SEC EDGAR as the public fundamentals source.

## Decision

Implement two explicit download functions behind the existing market-data ingestion path:

- Tiingo EOD price responses become canonical daily bars. Its `divCash` and `splitFactor` fields become canonical CorporateAction records. Credentials are read from `TIINGO_API_TOKEN` in the process environment or local `.env.local`; the token is sent in an HTTP header and never returned to the browser.
- SEC EDGAR submissions and Company Facts responses become canonical FundamentalFact records. The local configuration supplies `SEC_EDGAR_USER_AGENT`, as required for identified automated access; no API key is used.
- A Tiingo download may produce one Dataset Version for daily bars and one for corporate actions, because the existing canonical storage keeps those record families distinct. The API returns all created identifiers and makes the first one the primary result.
- Tiingo bars use the snapshot retrieval time as a conservative eligibility boundary because the EOD response does not carry a publication timestamp. SEC facts use the filing acceptance timestamp when available; facts without it retain missing provenance and are excluded from historical use.

Provider responses are fetched completely before any Dataset Version is created. Every response then goes through the same canonical validation and rejection reporting used by file imports.

## Consequences

This keeps the first release local and reproducible while acknowledging provider limits. Tiingo data remains subject to the account's terms and free-tier limits; SEC EDGAR coverage follows reporting issuers. Downloaded snapshots remain local and are never committed by the application.

## Sources

- [Tiingo End-of-Day API documentation](https://www.tiingo.com/documentation/end-of-day)
- [SEC EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC developer resources](https://www.sec.gov/about/developer-resources)
