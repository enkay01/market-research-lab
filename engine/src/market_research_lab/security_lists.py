"""Named, dated groups of securities for market data download and research."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class SecurityListNotFoundError(ValueError):
    """Raised when a requested Security List cannot be found."""


@dataclass(frozen=True)
class SecurityListMember:
    """One member security with uppercase symbol and optional 10-digit SEC CIK."""

    symbol: str
    cik: str | None = None


@dataclass(frozen=True)
class SecurityListSummary:
    """Discovery summary for one Dated Security List."""

    id: str
    name: str
    member_count: int
    as_of_date: str
    source_url: str


@dataclass(frozen=True)
class DatedSecurityList:
    """One immutable Dated Security List with fixed snapshot membership."""

    id: str
    name: str
    as_of_date: str
    source_url: str
    members: tuple[SecurityListMember, ...]


@lru_cache(maxsize=1)
def _load_snapshot_data() -> dict[str, DatedSecurityList]:
    data_file = Path(__file__).parent / "security_lists_data.json"
    raw_lists = json.loads(data_file.read_text(encoding="utf-8"))
    snapshot: dict[str, DatedSecurityList] = {}
    for list_id, raw in raw_lists.items():
        members = tuple(
            SecurityListMember(
                symbol=m["symbol"].upper(),
                cik=str(m["cik"]).zfill(10) if m.get("cik") else None,
            )
            for m in raw["members"]
        )
        snapshot[list_id] = DatedSecurityList(
            id=raw["id"],
            name=raw["name"],
            as_of_date=raw["as_of_date"],
            source_url=raw["source_url"],
            members=members,
        )
    return snapshot


def list_security_lists() -> tuple[SecurityListSummary, ...]:
    """Return summaries of all available Dated Security Lists."""
    snapshot = _load_snapshot_data()
    return tuple(
        SecurityListSummary(
            id=item.id,
            name=item.name,
            member_count=len(item.members),
            as_of_date=item.as_of_date,
            source_url=item.source_url,
        )
        for item in snapshot.values()
    )


def get_security_list(list_id: str) -> DatedSecurityList:
    """Resolve one Dated Security List by its identifier."""
    snapshot = _load_snapshot_data()
    if list_id not in snapshot:
        raise SecurityListNotFoundError(f"Security List '{list_id}' does not exist.")
    return snapshot[list_id]
