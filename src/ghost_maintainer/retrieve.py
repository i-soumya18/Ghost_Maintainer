"""Evidence retrieval engine using boosted BM25 index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import bm25s
import Stemmer

from ghost_maintainer.config import GHOST_REFUSAL_MESSAGE, settings
from ghost_maintainer.gitlog import Commit
from ghost_maintainer.index import index_repo


@dataclass(frozen=True, slots=True)
class Evidence:
    """Retrieved evidence item tagged with rank (E1..Ek), commit, and score."""

    tag: str
    commit: Commit
    score: float


def retrieve(
    query: str,
    repo_path: Path | str,
    k: int = 8,
    *,
    cache_dir: Path | None = None,
) -> list[Evidence]:
    """Retrieve top-k ranked evidence commits for a query from the BM25 index.

    Clamps k = min(k, len(corpus)) to guard against library exceptions and
    filters out documents with score <= 0.0.

    Args:
        query: User question or search query string.
        repo_path: Path to target git repository.
        k: Maximum number of evidence items to return (default: 8).
        cache_dir: Optional cache directory override.

    Returns:
        Ranked list of Evidence instances sorted by descending score.
        Returns empty list if repository has no commits or no query terms match.
    """
    resolved = Path(repo_path).resolve()
    commit_store, retriever, _ = index_repo(resolved, cache_dir=cache_dir)
    if len(commit_store) == 0 or retriever is None:
        return []

    # Guard k against corpus size to prevent bm25s ValueError
    effective_k = min(k, len(commit_store))
    if effective_k <= 0 or not query.strip():
        return []

    # Tokenize query with English stemmer and stopwords
    stemmer = Stemmer.Stemmer("english")
    query_tokens = bm25s.tokenize(
        [query],
        stopwords="en",
        stemmer=stemmer,
        show_progress=False,
    )

    # If query produced 0 tokens (e.g. all stopwords)
    if not hasattr(query_tokens, "ids") or not query_tokens.ids or len(query_tokens.ids[0]) == 0:
        return []

    # Query BM25 index
    doc_indices, scores = retriever.retrieve(
        query_tokens,
        k=effective_k,
        show_progress=False,
    )

    # Build ranked Evidence list with positive score filter
    evidence_list: list[Evidence] = []
    for i in range(effective_k):
        score = float(scores[0, i])
        if score <= 0.0:
            break
        doc_idx = int(doc_indices[0, i])
        evidence_list.append(
            Evidence(
                tag=f"E{i + 1}",
                commit=commit_store[doc_idx],
                score=score,
            )
        )

    return evidence_list


def check_retrieval_gate(
    evidence: list[Evidence],
    min_score: float | None = None,
) -> tuple[bool, str]:
    """Check if retrieved evidence passes the retrieval gate threshold.

    Stage 1 of the honesty pipeline.

    Args:
        evidence: List of retrieved evidence items.
        min_score: Minimum required BM25 score. Defaults to settings.min_score (0.8).

    Returns:
        (True, "") if top score >= min_score.
        (False, GHOST_REFUSAL_MESSAGE) if evidence is empty or top score < min_score.
    """
    threshold = min_score if min_score is not None else settings.min_score
    if not evidence or evidence[0].score < threshold:
        return False, GHOST_REFUSAL_MESSAGE
    return True, ""
