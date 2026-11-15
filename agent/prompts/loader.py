"""Loads versioned prompt files from agent/prompts/<name>.md.

Each file starts with a front-matter block:
---
node: proposal_writer
version: 3
---
Body uses $variables (string.Template), so JSON braces in prompts are safe.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

import yaml

PROMPT_DIR = Path(__file__).resolve().parent


class Prompt:
    def __init__(self, name: str, meta: dict, body: str):
        self.name = name
        self.meta = meta
        self.version = meta.get("version", 1)
        self._tpl = Template(body)

    def render(self, **variables: object) -> str:
        return self._tpl.safe_substitute({k: str(v) for k, v in variables.items()})


@lru_cache
def load_prompt(name: str) -> Prompt:
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt {name!r} not found in agent/prompts/")
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    else:
        body = text
    return Prompt(name, meta, body.strip())
