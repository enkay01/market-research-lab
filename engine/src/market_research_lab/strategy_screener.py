"""Backwards compatibility alias for Candidate Ranking (CONTEXT.md).

Project vocabulary designates this concept as "Candidate Ranking".
All implementations live in `market_research_lab.candidate_ranking`.
"""

from __future__ import annotations

from .candidate_ranking import (
    KNOWN_SECTORS,
    KNOWN_SECURITY_NAMES,
    CandidateRanking,
    CandidateRankingResult,
    CandidateRankingSpecification,
    DiagnosticBanner,
    RankedCandidate,
    ScreenerCandidate,
    StrategyScreenerResult,
    StrategyScreenerSpecification,
    build_diagnostic_banner,
    evaluate_candidate_ranking,
    evaluate_screener_sweep,
)

__all__ = [
    "KNOWN_SECTORS",
    "KNOWN_SECURITY_NAMES",
    "CandidateRanking",
    "CandidateRankingResult",
    "CandidateRankingSpecification",
    "DiagnosticBanner",
    "RankedCandidate",
    "ScreenerCandidate",
    "StrategyScreenerResult",
    "StrategyScreenerSpecification",
    "build_diagnostic_banner",
    "evaluate_candidate_ranking",
    "evaluate_screener_sweep",
]
