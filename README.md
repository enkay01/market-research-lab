# Market Research Lab

A local-first workspace for explicit, reproducible market research. It does not require an account, cloud services, or provider credentials for the local foundation.

## Start development

From the repository root, run one command:

```powershell
uv run dev
```

It opens the browser interface at `http://localhost:5173`. Vite proxies API calls to the validated FastAPI application while you develop.

## Run the production build

```powershell
uv run --project engine market-research-lab-serve
```

This builds the browser interface, then FastAPI serves both the interface and JSON API from `http://127.0.0.1:8000`.

## Checks

```powershell
uv run --project engine market-research-lab-check
uv run --project engine market-research-lab-build
```
