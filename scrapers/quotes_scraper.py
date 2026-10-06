"""Quotes to Scrape: selectors + pagination specifics. Returns RAW dictionaries."""
from __future__ import annotations

from .base_scraper import BaseScraper, text_of, utc_now_iso


class QuotesScraper(BaseScraper):
    source_name = "Quotes to Scrape"
    record_selector = "div.quote"

    def parse_record(self, quote, page_url: str) -> dict:
        return {
            "text": text_of(quote.select_one("span.text")),
            "author": text_of(quote.select_one("small.author")),
            "tags": [tag.get_text() for tag in quote.select("div.tags a.tag")],
            "page_url": page_url,
            "scraped_at": utc_now_iso(),
        }
