"""Small pure cleaning functions: value in, cleaned value out. No internet, no files."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

RATING_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_QUOTE_CHARS = "\u201c\u201d\""  # curly open/close and straight double quote


def clean_text(value: str | None) -> str | None:
    """Collapse spaces, tabs, newlines and non-breaking spaces. Empty -> None."""
    if value is None:
        return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    return text or None


def strip_quotes(value: str | None) -> str | None:
    """Remove the quotation marks wrapped around a quote's text."""
    text = clean_text(value)
    if text is None:
        return None
    return clean_text(text.strip(_QUOTE_CHARS))


def clean_price(raw: str | None) -> float | None:
    """'£51.77' -> 51.77 ; 'Â£1,234.50' -> 1234.5 ; anything unparseable -> None."""
    if not raw:
        return None
    match = re.search(r"\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(match.group()) if match else None


def clean_rating(raw: str | None) -> int | None:
    """'star-rating Three' or 'Three' -> 3 ; unknown -> None."""
    for word in str(raw or "").lower().split():
        if word in RATING_MAP:
            return RATING_MAP[word]
    return None


def clean_tags(tags: list[str] | None) -> str | None:
    """Lowercase, de-duplicate, sort and join with ';'. No tags -> None."""
    cleaned = {t.lower() for t in (clean_text(tag) for tag in (tags or [])) if t}
    return ";".join(sorted(cleaned)) or None


def normalize_url(url: str | None, base: str | None = None) -> str | None:
    """Return an absolute http(s) URL (no fragment, lowercase host) or None."""
    text = clean_text(url)
    if not text:
        return None
    if base:
        text = urljoin(base, text)
    parts = urlparse(text)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return parts._replace(scheme=parts.scheme.lower(), netloc=parts.netloc.lower(), fragment="").geturl()
