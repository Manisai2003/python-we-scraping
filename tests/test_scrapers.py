"""Parser tests on small HTML snippets that mimic the real sites (no internet)."""
from bs4 import BeautifulSoup

from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

BOOKS_HTML = """
<ul>
<li><article class="product_pod">
  <p class="star-rating Three"><i class="icon-star"></i></p>
  <h3><a href="catalogue/a-light_1000/index.html" title="A Light in the Attic">A Light in the ...</a></h3>
  <div class="product_price"><p class="price_color">\u00a351.77</p></div>
</article></li>
<li><article class="product_pod">
  <h3><a href="catalogue/no-price_1/index.html" title="No Price Book">No Price</a></h3>
</article></li>
<li><article class="product_pod"><div>completely broken</div></article></li>
</ul>
<ul class="pager"><li class="next"><a href="catalogue/page-2.html">next</a></li></ul>
"""

QUOTES_HTML = """
<div class="quote"><span class="text">\u201cBe yourself.\u201d</span>
  <span>by <small class="author">Oscar Wilde</small></span>
  <div class="tags">Tags: <meta class="keywords" content="x"/>
    <a class="tag" href="/tag/Inspirational/">Inspirational</a><a class="tag" href="/tag/life/">life</a></div></div>
<div class="quote"><span class="text">\u201cNo tags here.\u201d</span><small class="author">Anon</small>
  <div class="tags">Tags:</div></div>
<ul class="pager"><li class="next"><a href="/page/2/">Next</a></li></ul>
"""


def soup(html):
    return BeautifulSoup(html, "lxml")


def test_books_parse_page_handles_missing_elements():
    scraper = BooksScraper("https://books.toscrape.com/", fetch_details=False, delay=0)
    records = scraper.parse_page(soup(BOOKS_HTML), "https://books.toscrape.com/")
    assert len(records) == 3  # the broken article still yields a (mostly empty) raw record
    first, second, broken = records
    assert first["title"] == "A Light in the Attic"
    assert first["price_raw"] == "\u00a351.77"
    assert first["rating_raw"] == "star-rating Three"
    assert second["price_raw"] is None and second["rating_raw"] is None
    assert broken["title"] is None and broken["href"] is None


def test_books_next_url_is_resolved_against_current_page():
    scraper = BooksScraper("https://books.toscrape.com/", delay=0)
    assert scraper.find_next_url(soup(BOOKS_HTML), "https://books.toscrape.com/") == \
        "https://books.toscrape.com/catalogue/page-2.html"
    assert scraper.find_next_url(soup("<p>last page</p>"), "https://books.toscrape.com/x") is None


def test_quotes_parse_page():
    scraper = QuotesScraper("https://quotes.toscrape.com/", delay=0)
    records = scraper.parse_page(soup(QUOTES_HTML), "https://quotes.toscrape.com/")
    assert [r["author"] for r in records] == ["Oscar Wilde", "Anon"]
    assert records[0]["tags"] == ["Inspirational", "life"]
    assert records[1]["tags"] == []
    assert scraper.find_next_url(soup(QUOTES_HTML), "https://quotes.toscrape.com/") == \
        "https://quotes.toscrape.com/page/2/"


def test_record_that_raises_is_skipped_and_counted():
    class Boom(QuotesScraper):
        def parse_record(self, quote, page_url):
            raise ValueError("boom")

    scraper = Boom("https://quotes.toscrape.com/", delay=0)
    assert scraper.parse_page(soup(QUOTES_HTML), "https://quotes.toscrape.com/") == []
    assert scraper.stats.record_errors == 2
