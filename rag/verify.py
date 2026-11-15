"""Claim verification (B3, R5).

1. Split a proposal into atomic claims (sentences that assert the freelancer's experience/results).
2. Check each claim against the evidence it cites (or all retrieved evidence if it cites none):
   supported | partial | unsupported.
3. Repair: drop unsupported claims; strip unverifiable numbers from partial claims.
Unsupported-claim counts before and after repair are reported per proposal.

Offline heuristic: a claim is supported when its content words and every number it states appear in
the cited evidence. In the `open` profile an LLM judges support (prompt: claim_verifier.md).
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent.llm import Usage, llm_json

CLAIM_HINTS = re.compile(
    r"(?i)(\b(i've|i have|i built|i delivered|i led|i designed|i developed|i shipped|i created|i worked|i helped|"
    r"built|delivered|shipped|launched|improved|reduced|raised|cut|increased|grew|saved|years of|clients|"
    r"my (past|previous|recent))\b|\d+\s?%)")
FUTURE = re.compile(r"(?i)\b(i would|i will|i'll|i can|i'd|we can|we will|you will|you'll|let's)\b")


def _tech_vocab() -> set[str]:
    """Technology terms the portfolios use; naming one that the cited evidence lacks is a fabrication."""
    import json
    from pathlib import Path

    vocab: set[str] = set()
    for p in (Path(__file__).resolve().parent.parent / "data" / "personas").glob("*/profile.json"):
        vocab |= {s.lower() for s in json.loads(p.read_text(encoding="utf-8"))["skills"] if len(s) > 2}
    return vocab


TECH = _tech_vocab()


def specific_violation(claim: str, ev_text: str) -> str | None:
    """Deterministic check that overrides a lenient model: numbers and named technologies must be in evidence."""
    ev = ev_text.lower().replace("‑", "-")
    body = CITE.sub("", claim).lower().replace("‑", "-")
    missing_n = [n for n in _numbers(body) if n not in ev]
    if missing_n:
        return f"numbers not in evidence: {missing_n}"
    missing_t = [t for t in TECH if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", body) and t not in ev]
    if missing_t:
        return f"technologies not in cited evidence: {missing_t}"
    return None
CITE = re.compile(r"\[([a-z]{2,4}-[\w-]+)\]")
STOP = set("the a an and or of to in for on with by at from is are was were be been this that it as i my we our "
           "your you have has had will can using used into over than more less which who".split())


class ClaimCheck(BaseModel):
    claim: str
    cited: list[str] = []
    label: str  # supported | partial | unsupported
    reason: str = ""


class ClaimChecks(BaseModel):
    checks: list[ClaimCheck]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[\"'])|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_claims(text: str) -> list[str]:
    return [s for s in split_sentences(text) if CITE.search(s) or (CLAIM_HINTS.search(s) and not FUTURE.search(s))]


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9+#.-]{2,}", t.lower()) if w not in STOP}


def _numbers(t: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", CITE.sub("", t)))


def heuristic_check(claim: str, evidence: dict[str, dict]) -> ClaimCheck:
    cited = CITE.findall(claim)
    pool = [evidence[c] for c in cited if c in evidence] or list(evidence.values())
    if cited and not any(c in evidence for c in cited):
        return ClaimCheck(claim=claim, cited=cited, label="unsupported", reason="cites evidence that does not exist")
    ev_text = " ".join(e.get("snippet", e.get("text", "")) + " " + " ".join(e.get("skills", [])) for e in pool).lower()
    words = _words(CITE.sub("", claim))
    nums = _numbers(claim)
    if not words:
        return ClaimCheck(claim=claim, cited=cited, label="supported", reason="no factual content")
    overlap = len([w for w in words if w in ev_text]) / len(words)
    nums_ok = all(n in ev_text for n in nums)
    if not cited and overlap < 0.6:
        return ClaimCheck(claim=claim, cited=cited, label="unsupported", reason=f"no citation, overlap {overlap:.2f}")
    if nums_ok and overlap >= 0.45:
        return ClaimCheck(claim=claim, cited=cited, label="supported", reason=f"overlap {overlap:.2f}")
    if overlap >= 0.3:
        return ClaimCheck(claim=claim, cited=cited, label="partial",
                          reason=("numbers not in evidence; " if not nums_ok else "") + f"overlap {overlap:.2f}")
    return ClaimCheck(claim=claim, cited=cited, label="unsupported", reason=f"overlap {overlap:.2f}")


async def verify_claims(text: str, evidence: list[dict]) -> tuple[list[ClaimCheck], Usage]:
    ev = {e["id"]: e for e in evidence}
    claims = split_claims(text)
    if not claims:
        return [], Usage("verifier", "heuristic")

    def heuristic() -> ClaimChecks:
        return ClaimChecks(checks=[heuristic_check(c, ev) for c in claims])

    ev_block = "\n".join(f"[{e['id']}] {e.get('title', '')}: {e.get('snippet', '')[:400]}" for e in evidence)
    res, usage = await llm_json("verifier", "claim_verifier", ClaimChecks, heuristic,
                                claims="\n".join(f"- {c}" for c in claims), evidence=ev_block)
    checks = res.checks
    # Hard rule regardless of the model: citing a non-existent evidence id is unsupported.
    for c in checks:
        c.cited = CITE.findall(c.claim)
        if c.cited and not any(x in ev for x in c.cited):
            c.label, c.reason = "unsupported", "cites evidence that does not exist"
            continue
        pool = [ev[x] for x in c.cited if x in ev] or list(ev.values())
        ev_text = " ".join(e.get("snippet", e.get("text", "")) + " " + " ".join(e.get("skills", [])) for e in pool)
        v = specific_violation(c.claim, ev_text)
        if v and c.label != "unsupported":
            c.label, c.reason = "unsupported", v
    return checks, usage


def repair(text: str, checks: list[ClaimCheck], evidence: list[dict]) -> str:
    """Remove unsupported claims; drop numbers from partial claims that the evidence does not contain."""
    ev_text = " ".join(e.get("snippet", "") for e in evidence)
    out = text
    for c in checks:
        if c.label == "unsupported":
            out = out.replace(c.claim, "")
        elif c.label == "partial":
            fixed = c.claim
            for n in _numbers(c.claim):
                if n not in ev_text:
                    fixed = re.sub(rf"\b{re.escape(n)}%?", "", fixed)
            out = out.replace(c.claim, re.sub(r"\s{2,}", " ", fixed))
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", out)).strip()


def unsupported_count(checks: list[ClaimCheck]) -> int:
    return sum(c.label == "unsupported" for c in checks)
