"""Record validation. Returns the list of problems; an empty list means valid."""
from __future__ import annotations

import math

BOOKS = "Books to Scrape"
QUOTES = "Quotes to Scrape"
VALID_SOURCES = {BOOKS, QUOTES}


def validate_record(rec: dict) -> list[str]:
    problems: list[str] = []
    if rec.get("source") not in VALID_SOURCES:
        problems.append("unknown_source")
    if not rec.get("name_or_title"):
        problems.append("missing_name")
    if not str(rec.get("source_url") or "").startswith(("http://", "https://")):
        problems.append("invalid_url")

    price = rec.get("price")
    if price is not None:
        if isinstance(price, bool) or not isinstance(price, (int, float)) \
                or not math.isfinite(price) or price < 0:
            problems.append("invalid_price")

    rating = rec.get("rating")
    if rating is not None:
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            problems.append("invalid_rating")

    # Source-specific requirement: a quote without an author is not a usable quote.
    if rec.get("source") == QUOTES and not rec.get("author"):
        problems.append("missing_author")
    return problems
