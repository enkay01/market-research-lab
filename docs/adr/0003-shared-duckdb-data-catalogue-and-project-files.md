# Use a shared DuckDB data catalogue and readable Project files

Large normalized market datasets will live in a shared local DuckDB/Parquet catalogue, while research, definitions, revisions, and manifests remain readable files inside Project directories. DuckDB provides embedded analytical SQL over columnar files without a database server; keeping authored work outside it preserves inspectability and straightforward filesystem revisioning.

