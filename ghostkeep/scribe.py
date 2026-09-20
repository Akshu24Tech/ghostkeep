"""
Ghostkeep Memory Scribe — Distillation layer.

Extracts a clean, canonical 1-sentence fact and metadata from raw turns that
have passed the System 1 Sieve.
"""

from __future__ import annotations

import re
from typing import Optional
from .sieve import SieveResult


class MemoryScribe:
    """
    Distills raw text into canonical facts for Ghostkeep.
    """

    @staticmethod
    def distill(raw_text: str, sieve_result: SieveResult) -> dict:
        text = raw_text.strip()

        # Clean conversational preambles
        cleaned = re.sub(
            r"^(so|basically|i think|hey|fyi|just so you know|note that|we agreed that)[,\s:]+",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        # Extract the primary sentence
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        primary_claim = sentences[0] if sentences else cleaned

        # Generate smart tags
        tags = [sieve_result.domain] if sieve_result.domain != "general" else []
        for kw in ["postgres", "sqlite", "mysql", "auth", "jwt", "tailwind", "css", "docker", "mcp"]:
            if kw in cleaned.lower() and kw not in tags:
                tags.append(kw)

        return {
            "content": primary_claim,
            "domain": sieve_result.domain,
            "confidence": sieve_result.confidence,
            "tags": tags,
        }
