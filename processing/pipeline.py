"""Glue for the transform stages: raw dicts -> clean -> validate -> deduplicate.

Pure data in, data out (no internet, no files), so it is easy to test.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from .cleaning import (clean_price, clean_rating, clean_tags, clean_text,
                       normalize_url, strip_quotes)
from .deduplication import find_duplicates
from .validation import BOOKS, QUOTES, validate_record

logger = logging.getLogger(__name__)

COLUMNS = ["source", "source_url", "name_or_title", "category", "price", "rating",
           "author", "tags", "description", "scraped_at"]


def normalize_book(raw: dict) -> tuple[dict, list[str]]:
    """Raw book dict -> (record in the common model, parse issues)."""
    issues: list[str] = []
    price = clean_price(raw.get("price_raw"))
    if clean_text(raw.get("price_raw")) and price is None:
        issues.append("unparseable_price")
    rating = clean_rating(raw.get("rating_raw"))
    if clean_text(raw.get("rating_raw")) and rating is None:
        issues.append("unparseable_rating")
    record = {
        "source": BOOKS,
        "source_url": normalize_url(raw.get("href"), base=raw.get("page_url")),
        "name_or_title": clean_text(raw.get("title")),
        "category": clean_text(raw.get("category_raw")),
        "price": price,
        "rating": rating,
        "author": None,
        "tags": None,
        "description": clean_text(raw.get("description_raw")),
        "scraped_at": raw.get("scraped_at"),
    }
    return record, issues


def normalize_quote(raw: dict) -> tuple[dict, list[str]]:
    record = {
        "source": QUOTES,
        "source_url": normalize_url(raw.get("page_url")),  # page where the quote appeared
        "name_or_title": strip_quotes(raw.get("text")),
        "category": None,
        "price": None,
        "rating": None,
        "author": clean_text(raw.get("author")),
        "tags": clean_tags(raw.get("tags")),
        "description": None,
        "scraped_at": raw.get("scraped_at"),
    }
    return record, []


NORMALIZERS = {BOOKS: normalize_book, QUOTES: normalize_quote}


@dataclass
class PipelineResult:
    records: list[dict]
    per_source: dict[str, dict]
    duplicate_examples: list[dict] = field(default_factory=list)


def run_pipeline(raw_by_source: dict[str, list[dict]]) -> PipelineResult:
    per_source: dict[str, dict] = {}
    candidates: list[dict] = []

    for source, raws in raw_by_source.items():
        normalize = NORMALIZERS[source]
        reasons: Counter = Counter()
        stats = {"collected": len(raws), "cleaned": 0, "rejected": 0,
                 "duplicates": 0, "final": 0}
        for raw in raws:
            try:
                record, issues = normalize(raw)
            except Exception as exc:
                stats["rejected"] += 1
                reasons["cleaning_error"] += 1
                logger.warning("Rejected [%s] cleaning error: %s", source, exc)
                continue
            stats["cleaned"] += 1
            problems = issues + validate_record(record)
            if problems:
                stats["rejected"] += 1
                reasons.update(problems)
                logger.warning("Rejected [%s] %r: %s", source,
                               (record.get("name_or_title") or "")[:60], ", ".join(problems))
            else:
                candidates.append(record)
        # A record can fail several rules, so reason counts may exceed 'rejected'.
        stats["rejected_by_reason"] = dict(reasons)
        per_source[source] = stats

    unique, dupes = find_duplicates(candidates)
    examples = []
    for rec in dupes:
        per_source[rec["source"]]["duplicates"] += 1
        logger.warning("Duplicate removed [%s] %r", rec["source"], (rec["name_or_title"] or "")[:60])
        if len(examples) < 10:
            examples.append({"source": rec["source"],
                             "name_or_title": (rec["name_or_title"] or "")[:80],
                             "source_url": rec["source_url"]})
    for rec in unique:
        per_source[rec["source"]]["final"] += 1

    return PipelineResult(unique, per_source, examples)
