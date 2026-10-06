"""Shared networking code: session, retries, timeout, polite delay, pagination loop.

Everything that touches the internet lives in the ``scrapers`` package.
Source-specific scrapers only supply selectors and a ``parse_record`` method.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

USER_AGENT = "ScrapingAssignment/1.0 (learning project)"
RETRY_STATUS = (429, 500, 502, 503, 504)


def create_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    """Session with a User-Agent and automatic retries (exponential backoff)
    for connection problems and temporary HTTP errors."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=RETRY_STATUS,
        allowed_methods=frozenset(["GET", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_of(element) -> str | None:
    """Text of a BeautifulSoup element, or None if the element is missing."""
    return element.get_text() if element is not None else None


@dataclass
class ScrapeStats:
    pages_fetched: int = 0
    pages_failed: int = 0
    record_errors: int = 0
    detail_pages_failed: int = 0
    stopped_early: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class BaseScraper:
    """Generic 'follow the next link' scraper. Subclasses set the class
    attributes and implement ``parse_record``."""

    source_name: str = ""
    record_selector: str = ""
    next_selector: str = "li.next > a"

    def __init__(
        self,
        start_url: str,
        session: requests.Session | None = None,
        delay: float = 0.5,
        timeout: float = 10,
        max_pages: int | None = None,
    ) -> None:
        self.start_url = start_url
        self.session = session or create_session()
        self.delay = delay
        self.timeout = timeout
        self.max_pages = max_pages
        self.stats = ScrapeStats()
        self.records: list[dict] = []
        self._last_request = 0.0

    # ---- networking -------------------------------------------------
    def fetch(self, url: str) -> BeautifulSoup | None:
        """Download and parse one page. Returns None (after logging) on failure."""
        wait = self.delay - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)  # rate limiting: be polite to the server
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("[%s] request failed for %s: %s", self.source_name, url, exc)
            return None
        finally:
            self._last_request = time.monotonic()
        response.encoding = "utf-8"  # otherwise '£' can show up as 'Â£'
        return BeautifulSoup(response.text, "lxml")

    # ---- pagination -------------------------------------------------
    def scrape(self) -> list[dict]:
        """Follow the 'next' link until there is none. Never hard-codes page counts.

        Records are appended to ``self.records`` as we go, so a caller can still
        recover partial results if something unexpected is raised.
        """
        self.records = []
        visited: set[str] = set()
        url: str | None = self.start_url
        page = 0
        while url:
            if url in visited:
                logger.warning("[%s] pagination loop detected at %s; stopping", self.source_name, url)
                break
            if self.max_pages is not None and page >= self.max_pages:
                logger.info("[%s] reached --max-pages=%d; stopping", self.source_name, self.max_pages)
                break
            visited.add(url)
            page += 1
            logger.info("[%s] page %d: %s", self.source_name, page, url)

            soup = self.fetch(url)
            if soup is None:
                # Without the page we cannot know its 'next' link, so this source stops.
                self.stats.pages_failed += 1
                self.stats.stopped_early = True
                logger.error("[%s] giving up after failed page %d; keeping %d records so far",
                             self.source_name, page, len(self.records))
                break
            self.stats.pages_fetched += 1
            self.records.extend(self.parse_page(soup, url))
            url = self.find_next_url(soup, url)
        logger.info("[%s] finished: %d raw records from %d pages",
                    self.source_name, len(self.records), self.stats.pages_fetched)
        return self.records

    def find_next_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        link = soup.select_one(self.next_selector)
        href = link.get("href") if link is not None else None
        return urljoin(current_url, href) if href else None

    # ---- parsing ----------------------------------------------------
    def parse_page(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        items = soup.select(self.record_selector)
        if not items:
            logger.warning("[%s] no records found on %s", self.source_name, page_url)
        records = []
        for index, item in enumerate(items, start=1):
            try:
                record = self.parse_record(item, page_url)
            except Exception as exc:  # one bad record must not stop the page
                self.stats.record_errors += 1
                logger.warning("[%s] could not parse record %d on %s: %s",
                               self.source_name, index, page_url, exc)
                continue
            if record:
                records.append(record)
        return records

    def parse_record(self, item, page_url: str) -> dict | None:  # pragma: no cover
        raise NotImplementedError
