"""Per-persona index: item chunks + fixed-size chunks, dense vectors (fastembed, CPU) and BM25.

Vectors are kept in a numpy matrix on disk (data/processed/index/<persona>/). The corpus per persona
is a few hundred items, so exact cosine search is fast and avoids running a separate vector database.
Incremental re-index: items are keyed by content hash; only changed items are re-embedded.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import bm25s
import numpy as np

from agent.settings import ROOT, config

INDEX_DIR = ROOT / "data" / "processed" / "index"
CACHE = ROOT / ".cache" / "fastembed"


@lru_cache
def embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(config().embeddings["model"], cache_dir=str(CACHE))


@lru_cache
def reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(config().reranker["model"], cache_dir=str(CACHE))


def embed(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    v = np.array(list(embedder().embed(texts)), dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def _tok(t: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", t.lower())


def fixed_chunks(item: dict, size: int = 300, overlap: int = 60) -> list[str]:
    t = item["text"]
    return [t[i: i + size] for i in range(0, max(1, len(t)), size - overlap)] or [t]


def item_text(item: dict) -> str:
    """Item-level chunk: title + metadata line + text (structure-aware; items are short)."""
    meta = f"[{item['type']}] project={item.get('project') or '-'} industry={item.get('client_industry') or '-'}"
    return f"{item['title']}\n{meta}\n{item['text']}"


class PersonaIndex:
    def __init__(self, persona: str, items: list[dict], emb_item: np.ndarray, fixed: list[dict], emb_fixed: np.ndarray):
        self.persona = persona
        self.items = items
        self.by_id = {it["id"]: it for it in items}
        self.emb_item = emb_item
        self.fixed = fixed
        self.emb_fixed = emb_fixed
        self.bm25 = bm25s.BM25()
        self.bm25.index([_tok(item_text(it)) for it in items], show_progress=False)

    # ---------------------------------------------------------------- search primitives
    def dense_items(self, query: str, n: int) -> list[tuple[str, float]]:
        q = embed([query])[0]
        s = self.emb_item @ q
        idx = np.argsort(-s)[:n]
        return [(self.items[i]["id"], float(s[i])) for i in idx]

    def dense_fixed(self, query: str, n: int) -> list[tuple[str, float]]:
        q = embed([query])[0]
        s = self.emb_fixed @ q
        idx = np.argsort(-s)[: n * 4]
        out, seen = [], set()
        for i in idx:  # map chunk -> parent item, keep best chunk per item
            iid = self.fixed[i]["item_id"]
            if iid not in seen:
                seen.add(iid)
                out.append((iid, float(s[i])))
            if len(out) >= n:
                break
        return out

    def bm25_items(self, query: str, n: int) -> list[tuple[str, float]]:
        toks = _tok(query)
        if not toks:
            return []
        res, scores = self.bm25.retrieve([toks], k=min(n, len(self.items)), show_progress=False)
        return [(self.items[int(i)]["id"], float(s)) for i, s in zip(res[0], scores[0]) if s > 0]

    # ---------------------------------------------------------------- persistence
    def save(self) -> None:
        d = INDEX_DIR / self.persona
        d.mkdir(parents=True, exist_ok=True)
        (d / "items.json").write_text(json.dumps(self.items), encoding="utf-8")
        (d / "fixed.json").write_text(json.dumps(self.fixed), encoding="utf-8")
        np.save(d / "emb_item.npy", self.emb_item)
        np.save(d / "emb_fixed.npy", self.emb_fixed)


def build_index(persona: str, items: list[dict], previous: PersonaIndex | None = None) -> PersonaIndex:
    """Embed items; re-use vectors of unchanged items (incremental re-index)."""
    old = {}
    if previous is not None:
        old = {it["hash"]: previous.emb_item[i] for i, it in enumerate(previous.items)}
    todo = [it for it in items if it["hash"] not in old]
    new = dict(zip([it["hash"] for it in todo], embed([item_text(it) for it in todo]), strict=False))
    emb_item = np.array([old.get(it["hash"], new.get(it["hash"])) for it in items], dtype=np.float32)
    fixed = [{"item_id": it["id"], "text": c} for it in items for c in fixed_chunks(it)]
    emb_fixed = embed([f["text"] for f in fixed])
    idx = PersonaIndex(persona, items, emb_item, fixed, emb_fixed)
    idx.save()
    return idx


_cache: dict[str, PersonaIndex] = {}


def load_index(persona: str) -> PersonaIndex:
    if persona in _cache:
        return _cache[persona]
    d = INDEX_DIR / persona
    if not (d / "items.json").exists():
        from rag.ingest.build import build_persona

        return build_persona(persona)
    idx = PersonaIndex(persona, json.loads((d / "items.json").read_text(encoding="utf-8")), np.load(d / "emb_item.npy"),
                       json.loads((d / "fixed.json").read_text(encoding="utf-8")), np.load(d / "emb_fixed.npy"))
    _cache[persona] = idx
    return idx


def set_cached(idx: PersonaIndex) -> None:
    _cache[idx.persona] = idx
