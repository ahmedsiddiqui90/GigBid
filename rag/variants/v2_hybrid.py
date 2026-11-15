"""Retrieval variant v2_hybrid - a preset of rag/variants/pipeline.py switches (see PRESETS)."""
from rag.index.store import PersonaIndex
from rag.variants.pipeline import PRESETS, retrieve as _retrieve

SWITCHES = PRESETS["v2_hybrid"]


def retrieve(idx: PersonaIndex, job: dict, k: int = 5, candidates: int = 30) -> list[dict]:
    return _retrieve(idx, job, k, SWITCHES, candidates)
