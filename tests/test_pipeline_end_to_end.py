"""End-to-end test against a tiny local HTTP server (no internet needed).

The fake sites reproduce the structure of the real ones and include: a duplicate
book (different case/spacing), a book with an unparseable price, a 404 detail page,
a '£' served without a charset header, and (second test) a 500 on a quotes page.
"""
import csv
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from main import Config, run

POUND = "\u00a3"


def book(title, slug, price=f"{POUND}51.77", rating="Three"):
    price_html = f'<p class="price_color">{price}</p>' if price is not None else ""
    return (f'<article class="product_pod"><p class="star-rating {rating}"></p>'
            f'<h3><a href="{slug}/index.html" title="{title}">{title[:10]}...</a></h3>'
            f'<div class="product_price">{price_html}</div></article>')


def books_page(items, next_href=None):
    nxt = f'<li class="next"><a href="{next_href}">next</a></li>' if next_href else ""
    return f"<html><body>{''.join(items)}<ul class='pager'>{nxt}</ul></body></html>"


def detail(category, description):
    return ('<html><body><ul class="breadcrumb"><li><a>Home</a></li><li><a>Books</a></li>'
            f'<li><a>{category}</a></li><li class="active">x</li></ul>'
            f'<div id="product_description" class="sub-header"><h2>Product Description</h2></div>'
            f'<p>{description}</p></body></html>')


def quote(text, author, tags):
    tag_html = "".join(f'<a class="tag" href="/tag/{t}/">{t}</a>' for t in tags)
    return (f'<div class="quote"><span class="text">\u201c{text}\u201d</span>'
            f'<span>by <small class="author">{author}</small></span>'
            f'<div class="tags">Tags: {tag_html}</div></div>')


def quotes_page(items, next_href=None):
    nxt = f'<li class="next"><a href="{next_href}">Next</a></li>' if next_href else ""
    return f"<html><body>{''.join(items)}<ul class='pager'>{nxt}</ul></body></html>"


def make_routes(quotes_page2_status=200):
    return {
        "/books/": (200, books_page([book("A Light in the Attic", "item-a"),
                                      book("Tipping the Velvet", "item-b", rating="One")],
                                     "page-2.html")),
        "/books/page-2.html": (200, books_page([book("  A LIGHT IN THE ATTIC ", "item-a2"),
                                                 book("Bad Price Book", "item-c", price=f"{POUND}abc"),
                                                 book("No Price Book", "item-d", price=None)])),
        "/books/item-a/index.html": (200, detail("Poetry", "It&#39;s hard to imagine.")),
        "/books/item-b/index.html": (404, "gone"),  # detail failure: record kept, fields empty
        "/quotes/": (200, quotes_page([quote("Be yourself.", "Oscar Wilde", ["Life", "inspirational"]),
                                        quote("Silence is golden.", "Anon", [])], "/quotes/page/2/")),
        "/quotes/page/2/": (quotes_page2_status,
                            quotes_page([quote("Be yourself.", "oscar wilde", ["dup"]),
                                         quote("Another one.", "Jane Roe", ["x"])])),
    }


@contextmanager
def serve(routes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, body = routes.get(self.path, (404, "not found"))
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html")  # deliberately no charset
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def config(base, tmp_path, **kw):
    return Config(books_url=f"{base}/books/", quotes_url=f"{base}/quotes/",
                  output_dir=tmp_path / "output", log_dir=tmp_path / "logs",
                  delay=0, retries=0, backoff=0, timeout=5, **kw)


def read_csv(tmp_path):
    with open(tmp_path / "output" / "final_dataset.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_full_pipeline(tmp_path):
    with serve(make_routes()) as base:
        summary = run(config(base, tmp_path))

    rows = read_csv(tmp_path)
    assert summary["collected_per_source"] == {"Books to Scrape": 5, "Quotes to Scrape": 4}
    assert summary["rejected_by_reason"] == {"unparseable_price": 1}
    assert summary["duplicates_detected"] == 2          # one book + one quote
    assert summary["final_record_count"] == len(rows) == 6
    assert summary["reconciliation"]["holds"] is True
    assert all(v["status"] == "ok" for v in summary["scrape_details"].values())
    assert summary["scrape_details"]["Books to Scrape"]["detail_pages_failed"] == 4  # b, a2, c, d have no detail page

    books = [r for r in rows if r["source"] == "Books to Scrape"]
    quotes = [r for r in rows if r["source"] == "Quotes to Scrape"]
    assert len(books) == 3 and len(quotes) == 3
    first = books[0]
    assert first["name_or_title"] == "A Light in the Attic"
    assert first["price"] == "51.77"                    # '\u00a3' decoded correctly, numeric
    assert first["rating"] == "3" and first["category"] == "Poetry"
    assert first["description"] == "It's hard to imagine."
    assert first["author"] == "" and first["tags"] == ""
    assert books[1]["category"] == "" and books[1]["rating"] == "1"   # 404 detail page -> empty
    assert quotes[0]["name_or_title"] == "Be yourself." and quotes[0]["tags"] == "inspirational;life"
    assert quotes[0]["price"] == "" and quotes[0]["source_url"].endswith("/quotes/")
    assert (tmp_path / "logs" / "scraper.log").read_text(encoding="utf-8").count("page ") >= 4


def test_failed_page_does_not_stop_the_run(tmp_path):
    with serve(make_routes(quotes_page2_status=500)) as base:
        summary = run(config(base, tmp_path))

    quotes_info = summary["scrape_details"]["Quotes to Scrape"]
    assert quotes_info["status"] == "partial" and quotes_info["pages_failed"] == 1
    assert summary["scrape_details"]["Books to Scrape"]["status"] == "ok"
    assert summary["collected_per_source"]["Quotes to Scrape"] == 2   # page 1 only
    assert summary["final_per_source"]["Books to Scrape"] == 3        # books unaffected
    assert summary["final_record_count"] == len(read_csv(tmp_path)) == 5


def test_no_details_and_max_pages(tmp_path):
    with serve(make_routes()) as base:
        summary = run(config(base, tmp_path, fetch_details=False, max_pages=1))
    assert summary["collected_per_source"] == {"Books to Scrape": 2, "Quotes to Scrape": 2}
    assert all(r["category"] == "" for r in read_csv(tmp_path) if r["source"] == "Books to Scrape")


def test_unreachable_sites_still_write_outputs(tmp_path):
    summary = run(Config(books_url="http://127.0.0.1:9/", quotes_url="http://127.0.0.1:9/",
                         output_dir=tmp_path / "output", log_dir=tmp_path / "logs",
                         delay=0, retries=0, backoff=0, timeout=2))
    assert summary["final_record_count"] == 0
    assert summary["scrape_details"]["Books to Scrape"]["status"] == "failed"
    assert (tmp_path / "output" / "summary_report.json").exists()
    json.loads((tmp_path / "output" / "summary_report.json").read_text(encoding="utf-8"))
