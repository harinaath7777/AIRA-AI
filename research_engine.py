# research_engine.py
# Enhanced wrapper around research_agent.py.
# Imports the original functions directly — nothing is redefined.
# Adds: structured JSON output, research modes, progress callbacks, error handling.

import time

import numpy as np
from scipy.spatial.distance import cosine

# ── Import everything from the original research_agent ──────────────────────
from research_agent import (
    EMBEDDING_MODEL,
    SentenceTransformer,
    chunk_passages,
    fetch_text,
    search_web,
    split_sentences,
    unwrap_ddg,
)
from urllib.parse import urlparse

# ─────────────────────────────────────────────────────────────
# RESEARCH MODE PRESETS
# ─────────────────────────────────────────────────────────────

RESEARCH_MODES = {
    "quick": {
        "SEARCH_RESULTS":   4,
        "PASSAGES_PER_PAGE": 3,
        "TOP_PASSAGES":      4,
        "SUMMARY_SENTENCES": 3,
        "TIMEOUT":           6,
    },
    "normal": {
        "SEARCH_RESULTS":   6,
        "PASSAGES_PER_PAGE": 4,
        "TOP_PASSAGES":      5,
        "SUMMARY_SENTENCES": 3,
        "TIMEOUT":           8,
    },
    "deep": {
        "SEARCH_RESULTS":   10,
        "PASSAGES_PER_PAGE": 6,
        "TOP_PASSAGES":      10,
        "SUMMARY_SENTENCES": 6,
        "TIMEOUT":           12,
    },
}

# ─────────────────────────────────────────────────────────────
# PROGRESS STAGE LABELS
# ─────────────────────────────────────────────────────────────

STAGES = [
    "Searching the web...",
    "Finding relevant sources...",
    "Reading webpages...",
    "Processing information...",
    "Finding relevant passages...",
    "Creating summary...",
    "Research complete.",
]


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return url


# ─────────────────────────────────────────────────────────────
# ENHANCED RESEARCH AGENT
# ─────────────────────────────────────────────────────────────

class ShortResearchAgent:
    """
    Enhanced ShortResearchAgent that wraps the functions from research_agent.py.
    Returns fully structured, frontend-consumable results.
    Supports configurable modes and progress callbacks.
    """

    def __init__(self, embed_model=EMBEDDING_MODEL):
        print(f"Loading embedder: {embed_model}...")
        self.embedder = SentenceTransformer(embed_model)

    # ──────────────────────────────────────────────────────────
    # PUBLIC: run research
    # ──────────────────────────────────────────────────────────

    def run(self, query: str, mode: str = "normal", progress_callback=None) -> dict:
        """
        Run a full research pipeline using the original research_agent functions.

        Args:
            query:             The research question.
            mode:              "quick" | "normal" | "deep"
            progress_callback: Optional callable(stage_index, stage_message)

        Returns:
            {
                "query", "summary", "passages", "sources",
                "time", "total_sources", "total_passages", "mode", "error"
            }
        """
        cfg   = RESEARCH_MODES.get(mode, RESEARCH_MODES["normal"])
        start = time.time()

        def _emit(idx: int):
            if progress_callback:
                try:
                    progress_callback(idx, STAGES[idx])
                except Exception:
                    pass

        # ── Stage 0: Search ───────────────────────────────────
        _emit(0)
        raw_results = search_web(query, max_results=cfg["SEARCH_RESULTS"])

        if not raw_results:
            return self._empty(query, mode, start, "No search results found.")

        # ── Stage 1: Source evaluation ────────────────────────
        _emit(1)
        # search_web now returns list of dicts {"url", "title"}
        # (see updated search_web below — if it still returns plain URLs,
        #  we normalise here gracefully)
        url_meta = {}
        for r in raw_results:
            if isinstance(r, dict):
                url_meta[r["url"]] = r.get("title", "")
            else:
                url_meta[r] = ""
        urls = list(url_meta.keys())

        # ── Stage 2: Fetch webpages ───────────────────────────
        _emit(2)
        docs = []
        for u in urls:
            txt = fetch_text(u, timeout=cfg["TIMEOUT"])
            if not txt:
                continue
            chunks = chunk_passages(txt, max_words=120)
            for c in chunks[: cfg["PASSAGES_PER_PAGE"]]:
                docs.append({"url": u, "passage": c})

        if not docs:
            return self._empty(
                query, mode, start,
                "Could not retrieve usable content from any source."
            )

        # ── Stage 3: Embed passages ───────────────────────────
        _emit(3)
        passage_texts = [d["passage"] for d in docs]
        passage_embs  = self.embedder.encode(
            passage_texts, convert_to_numpy=True, show_progress_bar=False
        )
        q_emb = self.embedder.encode(query, convert_to_numpy=True)

        # ── Stage 4: Rank passages ────────────────────────────
        _emit(4)
        sims       = [float(1 - cosine(e, q_emb)) for e in passage_embs]
        sorted_idx = np.argsort(sims)[::-1][: cfg["TOP_PASSAGES"]]

        top_passages = [
            {
                "url":     docs[i]["url"],
                "passage": docs[i]["passage"],
                "score":   round(float(sims[i]), 4),
            }
            for i in sorted_idx
        ]

        # ── Stage 5: Summarize ────────────────────────────────
        _emit(5)
        summary = self._summarize(top_passages, q_emb, cfg["SUMMARY_SENTENCES"])

        # ── Stage 6: Build sources list ───────────────────────
        _emit(6)
        sources = self._build_sources(top_passages, url_meta)

        return {
            "query":          query,
            "summary":        summary,
            "passages":       top_passages,
            "sources":        sources,
            "time":           round(time.time() - start, 2),
            "total_sources":  len(sources),
            "total_passages": len(top_passages),
            "mode":           mode,
            "error":          None,
        }

    # ──────────────────────────────────────────────────────────
    # PRIVATE: extractive summarization (original logic from research_agent.py)
    # ──────────────────────────────────────────────────────────

    def _summarize(self, top_passages, q_emb, summary_sentences: int) -> str:
        sentences = []
        for tp in top_passages:
            for s in split_sentences(tp["passage"]):
                sentences.append({"sent": s, "url": tp["url"]})

        if not sentences:
            return "No summary could be generated."

        sent_texts = [s["sent"] for s in sentences]
        sent_embs  = self.embedder.encode(
            sent_texts, convert_to_numpy=True, show_progress_bar=False
        )
        sent_sims  = [float(1 - cosine(e, q_emb)) for e in sent_embs]

        sorted_idx = np.argsort(sent_sims)[::-1][:summary_sentences]
        chosen     = [sentences[i] for i in sorted_idx]

        seen, lines = set(), []
        for s in chosen:
            key = s["sent"].lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            lines.append(s["sent"])

        return " ".join(lines)

    # ──────────────────────────────────────────────────────────
    # PRIVATE: deduplicate passages → per-source entries
    # ──────────────────────────────────────────────────────────

    def _build_sources(self, top_passages, url_meta: dict) -> list:
        best: dict[str, dict] = {}
        for p in top_passages:
            u = p["url"]
            if u not in best or p["score"] > best[u]["score"]:
                best[u] = {
                    "url":    u,
                    "title":  url_meta.get(u) or _extract_domain(u),
                    "domain": _extract_domain(u),
                    "score":  p["score"],
                }
        return sorted(best.values(), key=lambda x: x["score"], reverse=True)

    # ──────────────────────────────────────────────────────────
    # PRIVATE: empty result on failure
    # ──────────────────────────────────────────────────────────

    def _empty(self, query, mode, start, error) -> dict:
        return {
            "query":          query,
            "summary":        "",
            "passages":       [],
            "sources":        [],
            "time":           round(time.time() - start, 2),
            "total_sources":  0,
            "total_passages": 0,
            "mode":           mode,
            "error":          error,
        }
