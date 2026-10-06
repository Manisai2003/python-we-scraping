# Multi-Source Web Scraping & Data Consolidation

A small ETL pipeline (Extract -> Transform -> Load) that scrapes two practice sites,
**Books to Scrape** (~1,000 books, 50 pages) and **Quotes to Scrape** (100 quotes, 10 pages),
converts them to one common table, cleans / validates / de-duplicates the records and writes
a CSV, a JSON summary and a log file.

```
Scrape (both sites) -> Clean -> Validate -> Deduplicate -> Consolidate -> Save files
```

## Python version and dependencies
- Python 3.10 - 3.12 (developed and tested on 3.12)
- `requests`, `beautifulsoup4`, `lxml` (runtime); `pytest` (tests). Exact versions are in `requirements.txt`.

## Setup
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## How to run
```bash
python main.py                    # full run (see runtime note below)
python main.py --no-details       # faster: skip the ~1,000 book detail pages
python main.py --max-pages 2      # quick smoke test: 2 pages per source
python main.py --help             # all options
python -m pytest                  # unit + end-to-end tests (no internet needed)
```
Options: `--delay` (default 0.5 s between requests), `--timeout`, `--retries`, `--output-dir`,
`--log-dir`, `--no-details`, `--max-pages`, `--books-url`, `--quotes-url`.

**Runtime:** a full run makes about 1,060 requests (50 + 10 listing pages and ~1,000 book detail
pages) with a 0.5 s pause each, so expect roughly 10 minutes. `--no-details` takes about 1 minute.

## Output
| File | Contents |
| --- | --- |
| `output/final_dataset.csv` | One row per unique, valid record; same 10 columns for every row |
| `output/summary_report.json` | Counts per source (collected, cleaned, rejected + reasons, duplicates, final), run time, scrape health, reconciliation check |
| `logs/scraper.log` | Time-stamped log of every page, warning (rejected / duplicate records) and error (failed requests). Overwritten each run |

The summary reconciles per source: `collected - rejected - duplicates = final`, and `final_record_count`
equals the number of CSV rows (the report contains a `reconciliation` block that states this).

## Project structure
```
main.py                     # entry point: connects the stages, writes outputs, CLI
scrapers/base_scraper.py    # session, retries, timeout, rate limit, pagination loop
scrapers/books_scraper.py   # Books selectors + detail-page enrichment
scrapers/quotes_scraper.py  # Quotes selectors
processing/cleaning.py      # pure cleaning functions
processing/validation.py    # returns a list of problems per record
processing/deduplication.py # fingerprints + duplicate detection
processing/pipeline.py      # raw -> common model -> validate -> dedupe (no I/O)
tests/                      # unit tests + end-to-end test against a local fake server
```
Rule of thumb: anything touching the internet lives in `scrapers/`; anything that only transforms data
lives in `processing/`; `main.py` connects the stages.

## Step 1 - Observations about the sources
| Item | Books to Scrape | Quotes to Scrape |
| --- | --- | --- |
| One record | `article.product_pod` | `div.quote` |
| Main text | `h3 > a` - full title is in the `title` attribute (visible text is truncated with `...`) | `span.text` (wrapped in curly quotes) |
| Price | `p.price_color` (`£51.77`) | none |
| Rating | class on `p.star-rating` (`Three`) | none |
| Author | none | `small.author` |
| Tags | none | `div.tags a.tag` (zero or more) |
| Link | `h3 > a[href]` (relative) | page URL (author link exists but is not a quote URL) |
| Category / description | **only on the detail page** (breadcrumb 3rd item; `#product_description` + next `p`) | none |
| Next page | `li.next > a` (relative href) | `li.next > a` (root-relative href) |

Both sites are plain server-rendered HTML, so **Requests + BeautifulSoup (lxml)** is enough; Selenium or
Playwright would only add overhead. The server does not declare a charset, so the code sets
`response.encoding = "utf-8"` (otherwise `£` shows up as `Â£`).

## Data model (common columns)
| Column | Books | Quotes |
| --- | --- | --- |
| `source` | `Books to Scrape` | `Quotes to Scrape` |
| `source_url` | Book detail page URL | URL of the page where the quote appeared |
| `name_or_title` | Book title | Quote text (curly quotes removed) |
| `category` | Detail-page category (empty with `--no-details` or if the detail page failed) | empty |
| `price` | Number, e.g. `51.77` | empty |
| `rating` | Integer 1-5 | empty |
| `author` | empty | Author name |
| `tags` | empty | Lowercase, sorted, `;`-joined |
| `description` | Detail-page description (may be empty) | empty |
| `scraped_at` | UTC ISO timestamp (set when the record was scraped) | same |

Fields that do not apply are left **empty** (never invented, e.g. quotes do not get `price = 0`).
Availability is available on the site but is not part of the suggested schema, so it is not exported.

## How pagination works
`BaseScraper.scrape()` starts at the home page, parses it, looks for `li.next > a`, joins the relative
link to the current URL with `urljoin` and repeats until there is no next link. Page counts are never
hard-coded, so the scraper adapts if a site gains or loses pages. Safety nets: a visited-URL set stops
accidental loops, and `--max-pages` caps a run.

## Cleaning approach (`processing/cleaning.py`)
- `clean_text`: collapses spaces/tabs/newlines/non-breaking spaces; empty -> `None`.
- `strip_quotes`: removes the quotation marks around quote text.
- `clean_price`: extracts the number (`£51.77` -> `51.77`, also copes with `Â£` and thousands commas).
- `clean_rating`: `Three` -> `3`.
- `clean_tags`: lowercase, de-duplicate, sort, join with `;`.
- `normalize_url`: makes URLs absolute, lowercases scheme/host, removes fragments, rejects non-http(s).

Scraping and cleaning are separate: scrapers return raw text exactly as found; cleaning is plain
functions that can be tested with strings and no internet.

## Validation approach (`processing/validation.py`)
`validate_record` returns a list of problems (empty = valid): `unknown_source`, `missing_name`,
`invalid_url`, `invalid_price` (must be a finite number >= 0 if present), `invalid_rating` (integer 1-5 if
present) and `missing_author` (quotes only). Two parse-time reasons are added by the pipeline:
`unparseable_price` / `unparseable_rating` (a value was present on the page but could not be converted) and
`cleaning_error` (unexpected exception while cleaning). Rejected records are logged as warnings and counted
by reason in the summary; they never stop the run. A record failing several rules counts once in
`rejected` but once per rule in `rejected_by_reason`.

## Deduplication approach (`processing/deduplication.py`)
A fingerprint (SHA-256 of a normalised key) is built for each valid record; a `set` of seen fingerprints
detects repeats. Normalisation: case-folded, punctuation removed, whitespace collapsed.
- **Books:** source + title
- **Quotes:** source + author + first 50 characters of the (normalised) quote text

So `"Example Book Title"`, `" Example Book Title "` and `"EXAMPLE BOOK TITLE"` are one record.
**Duplicates are removed** (first occurrence kept) rather than flagged, because the brief asks for one tidy
dataset; every removal is logged and the summary lists the count and up to 10 examples.
Deduplication runs across all sources together, but the key includes `source`, so books and quotes never
collide. Both practice sites are expected to contain no duplicates, so the logic is proven by unit tests with
deliberately duplicated records (`tests/test_deduplication.py`, `tests/test_pipeline_end_to_end.py`).

## Error-handling approach
- **Network:** one shared `requests.Session` with a User-Agent, a timeout, and automatic retries with
  exponential backoff (1 s, 2 s, 4 s) for connection errors and HTTP 429/500/502/503/504.
- **Failed listing page:** logged as an error; that source stops (its next link is unknown) but keeps the
  records already collected, and the other source still runs. The summary marks the source `partial`.
- **Failed book detail page:** logged; the record is kept with empty category/description.
- **Missing HTML elements:** `select_one()` results are checked for `None`; a missing field becomes `None`.
- **Bad records:** each record is parsed inside `try/except`; failures are logged and counted.
- **Each source** is wrapped in its own `try/except` in `main.py`.
- **Rate limiting:** at least `--delay` seconds (default 0.5) between any two requests.

## Assumptions
- Book `source_url` is the detail page; quote `source_url` is the listing page it appeared on (the quote has no URL of its own).
- A price/rating that is absent is allowed (the brief says "if present"); one that is present but unparseable is rejected.
- Two different books with the same title would be treated as duplicates (title is the identity key).

## Known limitations
- Sequential scraping (no async/parallelism); a full run takes about 10 minutes because of the polite delay.
- If a listing page fails after retries, the remaining pages of that source are not scraped (no checkpoint/resume).
- Quote identity uses only the first 50 characters, so two different quotes by one author starting identically would collapse.
- Selectors are tied to the current HTML of the practice sites.
- `robots.txt` is not parsed programmatically; the pipeline only requests normal public pages at a low rate.

## What I would change for production
Checkpoint/resume and incremental scraping, async or concurrent fetching with a global rate limit, config file
instead of CLI-only settings, a database (PostgreSQL) instead of CSV, scheduled runs with alerting on
`partial`/`failed` statuses, and schema drift detection (alert when selectors stop matching).

## AI usage summary
See `AI_USAGE.md`.
# python-we-scraping
