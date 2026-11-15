"""Retrieval variant v1_decompose - a preset of rag/variants/pipeline.py switches (see PRESETS)."""
from rag.index.store import PersonaIndex
from rag.variants.pipeline import PRESETS, retrieve as _retrieve

SWITCHES = PRESETS["v1_decompose"]


def retrieve(idx: PersonaIndex, job: dict, k: int = 5, candidates: int = 30) -> list[dict]:
    return _retrieve(idx, job, k, SWITCHES, candidates)
