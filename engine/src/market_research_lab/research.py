"""Domain model and storage for Markdown Research Theses."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SECURITY_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class InvalidSecurityIdError(ValueError):
    """Raised when a security_id contains invalid characters or path traversal sequences."""


class SecurityNotWatchedError(Exception):
    """Raised when an operation requires a watched security that is not in the project watchlist."""


@dataclass(frozen=True)
class ResearchThesis:
    security_id: str
    content: str
    updated_at: str
    summary: str | None = None
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    dated_updates: list[str] = field(default_factory=list)


def validate_security_id(security_id: str) -> str:
    """Validate security_id as a safe, canonical identifier."""
    cleaned = security_id.strip()
    if not cleaned or not SECURITY_ID_REGEX.fullmatch(cleaned):
        raise InvalidSecurityIdError(
            f"Security ID '{security_id}' is invalid. "
            "Allowed: alphanumeric, underscores, hyphens (1-64 chars)."
        )
    return cleaned


def resolve_thesis_path(project_dir: Path, security_id: str) -> Path:
    """Resolve and guarantee containment of a thesis file path within project/research/."""
    valid_id = validate_security_id(security_id)
    research_dir = (project_dir / "research").resolve()
    target_path = (research_dir / f"{valid_id}.md").resolve()
    if not target_path.is_relative_to(research_dir):
        raise InvalidSecurityIdError(f"Security ID '{security_id}' violates directory containment.")
    return target_path


def parse_thesis_sections(content: str) -> dict[str, object]:
    """Extract optional structured sections from a Markdown thesis."""
    lines = content.splitlines()
    sections: dict[str, list[str]] = {
        "summary": [],
        "evidence": [],
        "risks": [],
        "catalysts": [],
        "assumptions": [],
        "sources": [],
        "dated_updates": [],
    }

    current_section: str | None = None
    for line in lines:
        stripped = line.strip()
        header_match = re.match(r"^#{1,3}\s+(.+)$", stripped)
        if header_match:
            header_name = header_match.group(1).strip().lower()
            if "summary" in header_name:
                current_section = "summary"
            elif "evidence" in header_name:
                current_section = "evidence"
            elif "risk" in header_name:
                current_section = "risks"
            elif "catalyst" in header_name:
                current_section = "catalysts"
            elif "assumption" in header_name:
                current_section = "assumptions"
            elif "source" in header_name:
                current_section = "sources"
            elif "update" in header_name:
                current_section = "dated_updates"
            else:
                current_section = None
            continue

        if current_section and stripped:
            if stripped.startswith(("-", "*", "•")):
                item = re.sub(r"^[-*•]\s*", "", stripped).strip()
                if item:
                    sections[current_section].append(item)
            else:
                sections[current_section].append(stripped)

    summary_text = " ".join(sections["summary"]).strip() or None

    return {
        "summary": summary_text,
        "evidence": sections["evidence"],
        "risks": sections["risks"],
        "catalysts": sections["catalysts"],
        "assumptions": sections["assumptions"],
        "sources": sections["sources"],
        "dated_updates": sections["dated_updates"],
    }


def default_thesis_template(symbol: str) -> str:
    """Return a standard Markdown starter template containing all optional sections."""
    return f"""# Research Thesis: {symbol.upper()}

## Summary
Brief investment case summary.

## Evidence
- Primary data and supporting market evidence.

## Risks
- Primary operational, market, or valuation risks.

## Catalysts
- Expected catalysts and timing.

## Assumptions
- Key financial and operational assumptions.

## Research Sources
- Source documents, filings, and citations.

## Dated Updates
- {datetime.now(UTC).strftime('%Y-%m-%d')}: Initial research thesis created.
"""


def get_thesis(project_dir: Path, security_id: str) -> ResearchThesis | None:
    """Read a saved Markdown Research Thesis from the project research directory."""
    path = resolve_thesis_path(project_dir, security_id)
    if not path.is_file():
        return None

    content = path.read_text(encoding="utf-8")
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    parsed = parse_thesis_sections(content)

    return ResearchThesis(
        security_id=security_id,
        content=content,
        updated_at=mtime,
        summary=parsed["summary"] if isinstance(parsed["summary"], str) else None,
        evidence=list(parsed["evidence"]) if isinstance(parsed["evidence"], list) else [],
        risks=list(parsed["risks"]) if isinstance(parsed["risks"], list) else [],
        catalysts=list(parsed["catalysts"]) if isinstance(parsed["catalysts"], list) else [],
        assumptions=list(parsed["assumptions"]) if isinstance(parsed["assumptions"], list) else [],
        sources=list(parsed["sources"]) if isinstance(parsed["sources"], list) else [],
        dated_updates=(
            list(parsed["dated_updates"]) if isinstance(parsed["dated_updates"], list) else []
        ),
    )


def save_thesis(project_dir: Path, security_id: str, content: str) -> ResearchThesis:
    """Atomically save a Markdown Research Thesis to the project research directory."""
    path = resolve_thesis_path(project_dir, security_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as tmp:
        tmp.write(content)
        if not content.endswith("\n"):
            tmp.write("\n")
        tmp_path = Path(tmp.name)

    os.replace(tmp_path, path)
    return get_thesis(project_dir, security_id) or ResearchThesis(
        security_id=security_id,
        content=content,
        updated_at=datetime.now(UTC).isoformat(),
    )


def list_theses(project_dir: Path) -> dict[str, ResearchThesis]:
    """List all saved Research Theses for a project."""
    research_dir = project_dir / "research"
    if not research_dir.is_dir():
        return {}

    theses: dict[str, ResearchThesis] = {}
    for entry in research_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == ".md":
            security_id = entry.stem
            try:
                thesis = get_thesis(project_dir, security_id)
                if thesis:
                    theses[security_id] = thesis
            except InvalidSecurityIdError:
                continue
    return theses
