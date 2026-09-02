"""Lexical ranking for web results (ROADMAP PR 15).

A dependency-free TF scorer with document-frequency weighting (a compact BM25
variant). Pure functions so ranking is deterministic and unit-testable offline;
the embedding-based reranker can be layered on later without changing callers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class ScoredDoc:
    index: int
    score: float


def _bm25_idf(n_docs: int, df: int) -> float:
    # Standard BM25 idf with +1 so it is always non-negative.
    return math.log(1 + (n_docs - df + 0.5) / (df + 0.5))


def rank(query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[ScoredDoc]:
    """Rank ``documents`` against ``query`` (BM25). Returns them sorted, best first."""

    q_terms = set(tokenize(query))
    if not documents or not q_terms:
        return [ScoredDoc(i, 0.0) for i in range(len(documents))]

    doc_tokens = [tokenize(d) for d in documents]
    doc_len = [len(t) for t in doc_tokens]
    avg_len = (sum(doc_len) / len(doc_len)) or 1.0
    n_docs = len(documents)

    # Document frequency per query term.
    df: dict[str, int] = {}
    for term in q_terms:
        df[term] = sum(1 for toks in doc_tokens if term in toks)

    scores: list[ScoredDoc] = []
    for i, toks in enumerate(doc_tokens):
        score = 0.0
        length = doc_len[i] or 1
        for term in q_terms:
            if df[term] == 0:
                continue
            tf = toks.count(term)
            if tf == 0:
                continue
            idf = _bm25_idf(n_docs, df[term])
            denom = tf + k1 * (1 - b + b * length / avg_len)
            score += idf * (tf * (k1 + 1)) / denom
        scores.append(ScoredDoc(i, round(score, 4)))

    scores.sort(key=lambda s: s.score, reverse=True)
    return scores
