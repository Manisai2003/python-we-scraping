"""Books to Scrape: selectors + pagination specifics. Returns RAW dictionaries."""
from __future__ import annotations

import logging
from urllib.parse import urljoin

from .base_scraper import BaseScraper, text_of, utc_now_iso

logger = logging.getLogger(__name__)


class BooksScraper(BaseScraper):
    source_name = "Books to Scrape"
    record_selector = "article.product_pod"

    def __init__(self, *args, fetch_details: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fetch_details = fetch_details

    def parse_record(self, article, page_url: str) -> dict:
        link = article.select_one("h3 > a")
        price = article.select_one("p.price_color")
        rating = article.select_one("p.star-rating")

        href = link.get("href") if link is not None else None
        # The visible link text is cut off with '...'; the full title is in the attribute.
        title = (link.get("title") or link.get_text()) if link is not None else None

        record = {
            "title": title,
            "href": href,
            "page_url": page_url,
            "price_raw": text_of(price),
            "rating_raw": " ".join(rating.get("class", [])) if rating is not None else None,
            "category_raw": None,
            "description_raw": None,
            "scraped_at": utc_now_iso(),
        }
        if self.fetch_details and href:
            self._add_details(record, urljoin(page_url, href))
        return record

    def _add_details(self, record: dict, detail_url: str) -> None:
        """Category and description only exist on the book's detail page.
        A failure here is logged and the fields stay empty (never guessed)."""
        soup = self.fetch(detail_url)
        if soup is None:
            self.stats.detail_pages_failed += 1
            return
        try:
            record["category_raw"] = text_of(soup.select_one("ul.breadcrumb li:nth-of-type(3) a"))
            heading = soup.select_one("#product_description")
            paragraph = heading.find_next_sibling("p") if heading is not None else None
            record["description_raw"] = text_of(paragraph)
        except Exception as exc:
            self.stats.detail_pages_failed += 1
            logger.warning("[%s] could not parse details at %s: %s", self.source_name, detail_url, exc)
