import io

import pandas as pd
from fastapi.testclient import TestClient

from market_research_lab.api import create_app
from market_research_lab.json_types import JsonValue


def _option_rows() -> list[dict[str, JsonValue]]:
    rows = [
        {
            "record_type": "contract",
            "contract_id": "short",
            "security_id": "SPY",
            "expiration": "2024-02-20",
            "strike": 95,
            "right": "put",
            "multiplier": 100,
            "available_at": "2024-01-02T14:00:00Z",
        },
        {
            "record_type": "contract",
            "contract_id": "long",
            "security_id": "SPY",
            "expiration": "2024-02-20",
            "strike": 90,
            "right": "put",
            "multiplier": 100,
            "available_at": "2024-01-02T14:00:00Z",
        },
    ]
    for index, (short, long) in enumerate(((2.0, 0.5), (4.0, 1.0), (4.0, 1.0))):
        timestamp = f"2024-01-02T15:{index:02d}:00Z"
        available = f"2024-01-02T15:{index + 1:02d}:00Z"
        rows.extend(
            [
                {
                    "record_type": "underlying_bar",
                    "security_id": "SPY",
                    "timestamp": timestamp,
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100,
                    "volume": 1000,
                    "available_at": available,
                },
                {
                    "record_type": "trade",
                    "contract_id": "short",
                    "timestamp": timestamp,
                    "price": short,
                    "size": 100,
                    "available_at": available,
                },
                {
                    "record_type": "trade",
                    "contract_id": "long",
                    "timestamp": timestamp,
                    "price": long,
                    "size": 100,
                    "available_at": available,
                },
            ]
        )
    return rows


def test_options_api_persists_named_dataset_and_run(tmp_path):
    client = TestClient(create_app(workspace_root=tmp_path))
    content = io.BytesIO()
    pd.DataFrame(_option_rows()).to_csv(content, index=False)
    content.seek(0)

    imported = client.post(
        "/api/datasets",
        data={"source": "alpaca-test"},
        files={"file": ("options.csv", content, "text/csv")},
    )
    assert imported.status_code == 201
    dataset_id = imported.json()["dataset_version_id"]
    assert client.get(f"/api/datasets/{dataset_id}/coverage").json()["dataset_type"] == "options"

    project = client.post("/api/projects", json={"name": "Options"}).json()
    response = client.post(
        f"/api/projects/{project['id']}/options-backtests",
        json={
            "dataset_version_id": dataset_id,
            "symbol": "SPY",
            "start_date": "2024-01-02",
            "end_date": "2024-01-02",
            "fixed_short_contract_id": "short",
            "fixed_long_contract_id": "long",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["run_id"]
    assert result["manifest"]["kind"] == "options_backtest"
    assert result["manifest"]["input_dataset_versions"]["options_market_data"] == dataset_id
    assert str(result["manifest"]["source_sha256"]).startswith("sha256:")

    run_id = result["run_id"]
    loaded = client.get(f"/api/projects/{project['id']}/runs/{run_id}/options_backtest")
    assert loaded.status_code == 200
    assert loaded.json()["run_id"] == run_id
    listed = client.get(f"/api/projects/{project['id']}/options-backtests")
    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == run_id
    assert result["positions"][0]["candles"]

    for format_name, media_type in (
        ("json", "application/json"),
        ("csv", "text/csv"),
        ("html", "text/html"),
    ):
        exported = client.get(
            f"/api/projects/{project['id']}/options-backtests/{run_id}/export/{format_name}"
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith(media_type)
