"""Fuzzy matching helpers with an optional rapidfuzz dependency.

The bridge works better with rapidfuzz, but basic lookup should still function
in environments where that wheel is not installed yet.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable

try:
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore
    from rapidfuzz import process as _rf_process  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised indirectly in tests
    _rf_fuzz = None
    _rf_process = None


def weighted_ratio(left: str, right: str) -> float:
    """Return a rapidfuzz-like 0-100 similarity score."""
    if _rf_fuzz is not None:
        return float(_rf_fuzz.WRatio(left, right))
    return SequenceMatcher(None, left.lower(), right.lower()).ratio() * 100.0


def extract(
    query: str,
    choices: Iterable[str],
    *,
    limit: int = 5,
    score_cutoff: float = 0,
):
    """Return rapidfuzz-style extract tuples.

    Each item is `(match, score, index_or_none)`.
    """
    if _rf_process is not None and _rf_fuzz is not None:
        return _rf_process.extract(
            query,
            choices,
            scorer=_rf_fuzz.WRatio,
            limit=limit,
            score_cutoff=score_cutoff,
        )

    ranked = []
    for idx, choice in enumerate(choices):
        score = weighted_ratio(query, choice)
        if score >= score_cutoff:
            ranked.append((choice, score, idx))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:limit]
