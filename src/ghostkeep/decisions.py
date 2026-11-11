"""Find decisions and preferences in the USER's own words. Rule-based, no LLM.

Patterns ported from the legacy watcher (v2.1), plus the forms seen in the Day 1
baseline ("Go with Option 1", "Option 2 is rejected because ...").
Only user messages are scanned, never the agent's: an agent's suggestion is not a decision.
"""
from __future__ import annotations

import re

DECISION = [
    r"\blet'?s\s+(?:use|go\s+with|keep|drop|stick\s+with)\b",
    r"\bgo\s+with\b",
    r"\bwe\s+(?:will|'ll|should)\s+use\b",
    r"\bdecided\b",
    r"\binstead\s+of\b",
    r"\bdon'?t\s+(?:use|build|add)\b",
    r"\bdo\s+not\s+(?:use|invent|change|add)\b",
    r"\brejected?\b",
    r"\b(?:let'?s|we(?:'ll|\s+will|\s+should)?)\s+switch\s+to\b",  # "switch to the logs tab" is a request, not a choice
    r"\bchose\b|\bchoose\b",
    r"\bsupersedes\b",
]
# A preference is an instruction about how to work, not a description. "Always run the evals" is one;
# "the tests always fail" and "never mind" are not, so always/never only count as a command at the
# start of a sentence, or after I/we with a working verb.
PREFERENCE = [
    r"^(?:please\s+|and\s+)?(?:always|never)\s+(?!mind\b)[a-z]",
    r"\b(?:i|we)\s+(?:always|never)\s+(?:use|want|run|write|commit|push|keep|test|deploy|add|put)\b",
    r"\bi\s+prefer\b|\bwe\s+prefer\b|\bprefer\s+(?:to|using)\b",
    r"\bfrom\s+now\s+on\b",
]
_D = [re.compile(p, re.I) for p in DECISION]
_P = [re.compile(p, re.I) for p in PREFERENCE]
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def find(text: str) -> list[tuple[str, str]]:
    """[(kind, sentence)] with kind 'decision' or 'preference'. Sentences are verbatim."""
    out = []
    for raw in _SPLIT.split(text or ""):
        s = raw.strip(" -*\t")
        if len(s) < 8 or len(s) > 400 or s.endswith("?"):
            continue  # questions are not decisions
        if any(r.search(s) for r in _D):
            out.append(("decision", s))
        elif any(r.search(s) for r in _P):
            out.append(("preference", s))
    return out
