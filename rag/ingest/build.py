"""Build (or incrementally rebuild) persona indexes. Run: python -m rag.ingest.build"""
from __future__ import annotations

from rag.index.store import INDEX_DIR, build_index, load_index, set_cached
from rag.ingest.loaders import load_persona_dir

from agent.settings import ROOT

PERSONA_ROOT = ROOT / "data" / "personas"


def build_persona(persona: str, extra_dirs: list | None = None) -> object:
    items = load_persona_dir(PERSONA_ROOT / persona, persona)
    for d in extra_dirs or []:
        items += load_persona_dir(d, persona)
    prev = None
    if (INDEX_DIR / persona / "items.json").exists():
        try:
            prev = load_index(persona)
        except Exception:  # noqa: BLE001
            prev = None
    idx = build_index(persona, items, prev)
    set_cached(idx)
    return idx


def main() -> None:
    for p in sorted(x.name for x in PERSONA_ROOT.iterdir() if x.is_dir()):
        idx = build_persona(p)
        print(f"{p}: {len(idx.items)} items, {len(idx.fixed)} fixed chunks")


if __name__ == "__main__":
    main()
