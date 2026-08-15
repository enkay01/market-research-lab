"""Unit tests for the Research Thesis domain module."""

from __future__ import annotations

from pathlib import Path

import pytest

from market_research_lab.research import (
    InvalidSecurityIdError,
    default_thesis_template,
    get_thesis,
    list_theses,
    parse_thesis_sections,
    resolve_thesis_path,
    save_thesis,
    validate_security_id,
)


def test_validate_security_id_accepts_valid_ids() -> None:
    assert validate_security_id("AAPL") == "AAPL"
    assert validate_security_id("sec-aapl") == "sec-aapl"
    assert validate_security_id("BRK_B") == "BRK_B"
    assert validate_security_id("sec-123_45") == "sec-123_45"


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        "   ",
        "../etc/passwd",
        "sec/aapl",
        "sec\\aapl",
        "a" * 65,
        "aapl;drop table",
        "sec.aapl",
    ],
)
def test_validate_security_id_rejects_unsafe_or_invalid_ids(invalid_id: str) -> None:
    with pytest.raises(InvalidSecurityIdError):
        validate_security_id(invalid_id)


def test_resolve_thesis_path_guarantees_containment(tmp_path: Path) -> None:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)
    resolved = resolve_thesis_path(project_dir, "sec-aapl")
    assert resolved == project_dir / "research" / "sec-aapl.md"
    assert resolved.resolve().is_relative_to((project_dir / "research").resolve())


def test_resolve_thesis_path_rejects_directory_traversal(tmp_path: Path) -> None:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)
    with pytest.raises(InvalidSecurityIdError):
        resolve_thesis_path(project_dir, "../../escaped")


def test_save_and_get_thesis_roundtrip(tmp_path: Path) -> None:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)

    markdown = """# Research Thesis: AAPL

## Summary
Strong ecosystem lock-in and high-margin services growth.

## Evidence
- Services revenue grew 12% year-over-year.
- Installed device base exceeds 2.2 billion active devices.

## Risks
- Antitrust pressure on App Store commission structure.

## Catalysts
- Adoption of on-device intelligence features.

## Assumptions
- Operating margin remains above 30%.

## Research Sources
- 10-K FY2025: sec.gov
- Earnings call transcript Q3

## Dated Updates
- 2026-08-15: Maintained bullish outlook.
"""

    thesis = save_thesis(project_dir, "sec-aapl", markdown)
    assert thesis.security_id == "sec-aapl"
    assert thesis.content == markdown
    assert thesis.summary == "Strong ecosystem lock-in and high-margin services growth."
    assert len(thesis.evidence) == 2
    assert "Services revenue grew 12% year-over-year." in thesis.evidence[0]
    assert len(thesis.risks) == 1
    assert len(thesis.catalysts) == 1
    assert len(thesis.assumptions) == 1
    assert len(thesis.sources) == 2
    assert len(thesis.dated_updates) == 1

    # Read back
    loaded = get_thesis(project_dir, "sec-aapl")
    assert loaded is not None
    assert loaded.security_id == "sec-aapl"
    assert loaded.content == markdown
    assert loaded.summary == thesis.summary
    assert loaded.updated_at == thesis.updated_at


def test_get_thesis_returns_none_when_file_absent(tmp_path: Path) -> None:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)
    assert get_thesis(project_dir, "sec-msft") is None


def test_list_theses_returns_all_saved_theses(tmp_path: Path) -> None:
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)

    save_thesis(project_dir, "sec-aapl", "# AAPL Thesis\n\n## Summary\nApple summary.")
    save_thesis(project_dir, "sec-msft", "# MSFT Thesis\n\n## Summary\nMicrosoft summary.")

    theses = list_theses(project_dir)
    assert len(theses) == 2
    assert "sec-aapl" in theses
    assert "sec-msft" in theses
    assert theses["sec-aapl"].summary == "Apple summary."
    assert theses["sec-msft"].summary == "Microsoft summary."


def test_parse_thesis_sections_handles_partial_sections() -> None:
    content = """# Minimal Thesis

## Summary
Only summary and risks provided.

## Risks
- Supply chain disruption.
"""
    sections = parse_thesis_sections(content)
    assert sections["summary"] == "Only summary and risks provided."
    assert sections["risks"] == ["Supply chain disruption."]
    assert sections["evidence"] == []
    assert sections["catalysts"] == []
    assert sections["assumptions"] == []
    assert sections["sources"] == []
    assert sections["dated_updates"] == []


def test_default_thesis_template_contains_all_optional_headers() -> None:
    template = default_thesis_template("NVDA")
    assert "# Research Thesis: NVDA" in template
    assert "## Summary" in template
    assert "## Evidence" in template
    assert "## Risks" in template
    assert "## Catalysts" in template
    assert "## Assumptions" in template
    assert "## Research Sources" in template
    assert "## Dated Updates" in template
