"""Explicit promotion rules for long-term memory (R7). Raw tool output never enters memory.

Style memory: each user edit is diffed into candidate patterns. A pattern becomes a style rule only
after it has been observed in `memory.style_promotion_min_occurrences` separate edits.

Outcome memory: per job category, counts of submitted / replied / hired proposals, taken only from
confirmed marketplace events. Rates are used by decisions only once a category has
`memory.outcome_min_samples` outcomes.
"""
from __future__ import annotations

import re

from rag.verify import split_sentences

PATTERN_RULES = {
    "cut_first_sentence": "Cut the generic first sentence; open with the client's problem.",
    "shorter": "Keep proposals short: about 20% shorter than the first draft.",
    "no_exclamations": "Do not use exclamation marks.",
    "no_greeting_name": "Do not open with 'Hi there' or 'Hello'; start with the substance.",
}
BANNED_WORD_RULE = "Never use the word '{w}'."
WATCH_WORDS = ["passionate", "excited", "expert", "guru", "rockstar", "ninja", "hard-working", "dedicated", "thrilled",
               "delighted", "seamless", "cutting-edge", "leverage"]


def edit_patterns(before: str, after: str) -> list[str]:
    """Candidate style patterns from one edit (deterministic, explainable)."""
    pats: list[str] = []
    b_s, a_s = split_sentences(before), split_sentences(after)
    if b_s and a_s and b_s[0] != a_s[0] and b_s[0] not in after:
        pats.append("cut_first_sentence")
    if len(after.split()) < 0.8 * len(before.split()):
        pats.append("shorter")
    if before.count("!") > after.count("!") and after.count("!") == 0:
        pats.append("no_exclamations")
    if re.match(r"(?i)\s*(hi|hello|hey)\b", before) and not re.match(r"(?i)\s*(hi|hello|hey)\b", after):
        pats.append("no_greeting_name")
    for w in WATCH_WORDS:
        if re.search(rf"(?i)\b{re.escape(w)}\b", before) and not re.search(rf"(?i)\b{re.escape(w)}\b", after):
            pats.append(f"ban:{w}")
    return pats


def rule_text(pattern: str) -> str:
    if pattern.startswith("ban:"):
        return BANNED_WORD_RULE.format(w=pattern[4:])
    return PATTERN_RULES.get(pattern, pattern)
