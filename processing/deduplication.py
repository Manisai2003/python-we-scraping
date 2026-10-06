"""Fingerprint-based duplicate detection.

Identity rule (documented in README):
  Books  : source + title
  Quotes : source + author + first 50 characters of the (normalised) quote text
Each part is lowercased, stripped of punctuation and whitespace-collapsed before hashing.
"""
from __future__ import annotations

import hashlib
import re

from .validation import BOOKS


def _norm(value: str | None) -> str:
    text = re.sub(r"[^\w\s]", "", str(value or "").casefold())
    return " ".join(text.split())


def make_fingerprint(rec: dict) -> str:
    if rec.get("source") == BOOKS:
        parts = [_norm(rec.get("source")), _norm(rec.get("name_or_title"))]
    else:  # quotes
        parts = [_norm(rec.get("source")), _norm(rec.get("author")),
                 _norm(rec.get("name_or_title"))[:50]]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def find_duplicates(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (unique, duplicates). The first occurrence is kept."""
    seen: set[str] = set()
    unique: list[dict] = []
    dupes: list[dict] = []
    for rec in records:
        fp = make_fingerprint(rec)
        if fp in seen:
            dupes.append(rec)
        else:
            seen.add(fp)
            unique.append(rec)
    return unique, dupes
