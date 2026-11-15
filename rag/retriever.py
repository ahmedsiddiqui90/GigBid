"""Retriever factory: variant chosen by config (`retrieval.variant`) or explicitly (evals)."""
from __future__ import annotations

import importlib

from agent.settings import config
from rag.index.store import load_index

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v8_corrective"]


def get_variant(name: str | None = None):
    name = name or config().retrieval["variant"]
    if name not in VARIANTS:
        raise ValueError(f"unknown variant {name!r}")
    return importlib.import_module(f"rag.variants.{name}")


def search(persona: str, job: dict, k: int | None = None, variant: str | None = None) -> list[dict]:
    return get_variant(variant).retrieve(load_index(persona), job, k or config().retrieval["k"])
