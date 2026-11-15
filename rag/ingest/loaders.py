"""Loaders for a persona's portfolio folder: Markdown (CV, case studies, READMEs), code excerpts,
JSON (reviews, past proposals with outcomes) and PDF CVs uploaded by users.

Every item gets metadata: persona, type, project, skills, date, client_industry, outcome.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, text.strip()


def _item(meta: dict, text: str, path: Path, persona: str) -> dict:
    iid = meta.get("id") or f"doc-{persona}-{hashlib.md5(str(path).encode()).hexdigest()[:8]}"
    first = text.splitlines()[0].lstrip("# ").strip() if text else iid
    return {
        "id": iid, "persona": meta.get("persona", persona), "type": meta.get("type", "document"),
        "project": meta.get("project"), "title": meta.get("title", first), "text": text,
        "skills": meta.get("skills", []), "date": str(meta.get("date", "")),
        "client_industry": meta.get("client_industry"), "outcome": meta.get("outcome"),
        "source": str(path.as_posix()), "synthetic": bool(meta.get("synthetic", False)),
        "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
    }


def load_pdf(path: Path, persona: str) -> dict:
    from pypdf import PdfReader

    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    return _item({"type": "cv"}, text, path, persona)


def load_persona_dir(folder: Path, persona: str | None = None) -> list[dict]:
    folder = Path(folder)
    persona = persona or folder.name
    items: list[dict] = []
    for path in sorted(folder.rglob("*")):
        if path.is_dir():
            continue
        suf = path.suffix.lower()
        if suf in (".md", ".txt"):
            meta, body = _front_matter(path.read_text(encoding="utf-8"))
            if path.name == "main_snippet.txt" or suf == ".txt":
                meta.setdefault("type", "code")
            items.append(_item(meta, body, path, persona))
        elif suf == ".pdf":
            items.append(load_pdf(path, persona))
        elif suf == ".json" and path.name in ("reviews.json", "past_proposals.json"):
            for rec in json.loads(path.read_text(encoding="utf-8")):
                text = rec["text"] if rec["type"] == "review" else f"Job: {rec.get('job_title', '')}\n{rec['text']}"
                items.append(_item(rec, text, path, persona))
    return items
