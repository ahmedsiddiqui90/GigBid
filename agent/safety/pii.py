"""PII masking for logs, traces and the audit log."""
from __future__ import annotations

import logging
import re
from typing import Any

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d"), "<phone>"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<card>"),
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "<iban>"),
]


def mask(text: str) -> str:
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def mask_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, dict):
        return {k: ("<redacted>" if "token" in k.lower() or "password" in k.lower() else mask_obj(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v) for v in obj]
    return obj


class PIIFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask(str(record.msg))
        if record.args:
            record.args = tuple(mask_obj(a) for a in record.args) if isinstance(record.args, tuple) else record.args
        return True


def install_pii_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(PIIFilter())
