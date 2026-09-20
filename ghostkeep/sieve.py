"""
Ghostkeep Memory Sieve — System 1 micro-decision filter.

Evaluates raw conversation turns, terminal commands, and tool outputs in sub-100ms.
Discards 90% ephemeral noise and passes only durable facts, constraints, and decisions.

Supports TypeSafe Jev (via typesafe-sdk) when TYPESAFE_API_KEY is available,
with a robust local heuristic engine as an offline/development fallback.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SieveResult:
    is_durable: bool
    confidence: float          # 0.0 to 1.0
    domain: str                # database, auth, ui, devops, architecture, preferences, general
    reason: str
    engine: str                # "typesafe_jev" | "local_heuristic"


# High-signal decision patterns
DECISION_PATTERNS = [
    (r"\b(we decided|decided to|switching to|switched from|migrate to|migrated to)\b", 0.90, "decision"),
    (r"\b(always use|never use|do not use|constraint:|enforce|must use)\b", 0.92, "constraint"),
    (r"\b(root cause:|fixed bug caused by|bug fix:|resolved by changing)\b", 0.88, "bug_lesson"),
    (r"\b(prefer|preferences?|convention:|standard:|architecture:)\b", 0.85, "preference"),
    (r"\b(primary database|auth provider|deployment target|backend framework)\b", 0.85, "architecture"),
]

# Ephemeral noise patterns
NOISE_PATTERNS = [
    r"^npm (test|run|install|start)",
    r"^[0-9]+ (tests? (passed|failed)|passing|failing)",
    r"\b(progress:|downloading|extracting|cached|fetching)\b",
    r"\b(hello|hi|thanks|okay|sounds good|cool|done|got it)\b",
    r"^\s*git (status|diff|log|add)\s*$",
    r"^\s*ls\s*|dir\s*$",
    r"warning: in the working copy of",
]

DOMAIN_KEYWORDS = {
    "database": ["postgres", "mysql", "sqlite", "mongodb", "database", "orm", "sql", "aurora", "dynamodb"],
    "auth": ["jwt", "oauth", "auth", "token", "password", "login", "session", "keycloak", "cognito"],
    "ui": ["css", "tailwind", "html", "frontend", "component", "react", "vue", "button", "layout", "styling"],
    "devops": ["docker", "kubernetes", "ecs", "ci/cd", "github actions", "deploy", "aws", "gcp", "azure"],
    "preferences": ["prefer", "convention", "style guide", "format", "rule", "standard"],
}


class MemorySieve:
    """
    Evaluates raw text to determine if it contains durable memory.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        self._jev_client = None
        if self.api_key:
            try:
                from typesafe_sdk import TypeSafeClient
                self._jev_client = TypeSafeClient(api_key=self.api_key)
            except (ImportError, Exception):
                self._jev_client = None

    def evaluate(self, raw_text: str) -> SieveResult:
        text = raw_text.strip()
        if not text or len(text) < 10:
            return SieveResult(
                is_durable=False,
                confidence=0.0,
                domain="general",
                reason="Text is empty or too short (<10 chars)",
                engine="local_heuristic",
            )

        # Try Jev System 1 if client is available
        if self._jev_client:
            try:
                return self._evaluate_with_jev(text)
            except Exception:
                pass  # Fall back gracefully to local heuristic

        return self._evaluate_heuristic(text)

    def _evaluate_with_jev(self, text: str) -> SieveResult:
        from typesafe_sdk import Choice, Noul, Score

        response = self._jev_client.system_one(
            state={"text": text},
            questions={
                "is_durable": Noul(
                    instructions="Does this text declare an explicit architectural decision, durable constraint, user preference, or bug root-cause lesson? Answer false for raw terminal outputs, test runs, and casual chatter."
                ),
                "domain": Choice(
                    instructions="Which technical domain does this belong to?",
                    criteria={
                        "database": None,
                        "auth": None,
                        "ui": None,
                        "devops": None,
                        "architecture": None,
                        "preferences": None,
                        "general": None,
                    },
                ),
                "permanence": Score(
                    instructions="Rate the durability of this statement",
                    criteria=["ephemeral", "session_temp", "durable", "immutable"],
                ),
            },
        )
        conf = response.nouls["is_durable"].noul
        is_durable = conf >= 0.75
        domain = response.choices["domain"].choice or "general"
        reason = f"Jev RLCD decision (confidence={conf:.2f}, permanence={response.scores['permanence'].score})"

        return SieveResult(
            is_durable=is_durable,
            confidence=conf,
            domain=domain,
            reason=reason,
            engine="typesafe_jev",
        )

    def _evaluate_heuristic(self, text: str) -> SieveResult:
        text_lower = text.lower()

        # Check noise patterns first
        for noise_pat in NOISE_PATTERNS:
            if re.search(noise_pat, text_lower, re.MULTILINE):
                return SieveResult(
                    is_durable=False,
                    confidence=0.1,
                    domain="general",
                    reason=f"Matched ephemeral noise pattern: {noise_pat}",
                    engine="local_heuristic",
                )

        # Check decision patterns
        best_score = 0.0
        match_reason = ""
        for pat, score, reason_tag in DECISION_PATTERNS:
            if re.search(pat, text_lower):
                if score > best_score:
                    best_score = score
                    match_reason = f"Matched {reason_tag} trigger"

        # Determine domain
        matched_domain = "general"
        for domain, kws in DOMAIN_KEYWORDS.items():
            if any(kw in text_lower for kw in kws):
                matched_domain = domain
                break

        is_durable = best_score >= 0.75
        if not is_durable:
            match_reason = "No durable decision or constraint indicators detected"

        return SieveResult(
            is_durable=is_durable,
            confidence=best_score if is_durable else 0.2,
            domain=matched_domain,
            reason=match_reason,
            engine="local_heuristic",
        )
