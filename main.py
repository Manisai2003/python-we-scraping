"""Entry point:  python main.py

Runs: scrape -> clean -> validate -> deduplicate -> consolidate -> write files.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from processing.pipeline import COLUMNS, run_pipeline
from scrapers.base_scraper import create_session
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

logger = logging.getLogger("main")


@dataclass
class Config:
    books_url: str = "https://books.toscrape.com/"
    quotes_url: str = "https://quotes.toscrape.com/"
    output_dir: Path = Path("output")
    log_dir: Path = Path("logs")
    delay: float = 0.5
    timeout: float = 10
    retries: int = 3
    backoff: float = 1.0
    fetch_details: bool = True
    max_pages: int | None = None


def setup_logging(log_file: Path) -> None:
    """Configure logging once: console + file (overwritten each run)."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(log_file, mode="w", encoding="utf-8")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def write_csv(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)  # None is written as an empty cell


def write_summary(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=4, ensure_ascii=False)


def run(cfg: Config) -> dict:
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    setup_logging(Path(cfg.log_dir) / "scraper.log")
    logger.info("Run started (details=%s, delay=%ss)", cfg.fetch_details, cfg.delay)

    session = create_session(retries=cfg.retries, backoff=cfg.backoff)
    common = dict(session=session, delay=cfg.delay, timeout=cfg.timeout, max_pages=cfg.max_pages)
    scrapers = [
        BooksScraper(cfg.books_url, fetch_details=cfg.fetch_details, **common),
        QuotesScraper(cfg.quotes_url, **common),
    ]

    # --- Extract: each source in its own try/except so one failure cannot stop the other
    raw_by_source: dict[str, list[dict]] = {}
    scrape_details: dict[str, dict] = {}
    for scraper in scrapers:
        error = None
        try:
            scraper.scrape()
        except Exception as exc:
            error = str(exc)
            logger.exception("[%s] unexpected failure; continuing with partial data", scraper.source_name)
        raw_by_source[scraper.source_name] = scraper.records
        if not scraper.records:
            status = "failed"
        elif error or scraper.stats.stopped_early:
            status = "partial"
        else:
            status = "ok"
        scrape_details[scraper.source_name] = {"status": status, **scraper.stats.as_dict(),
                                               **({"error": error} if error else {})}

    # --- Transform: clean -> validate -> deduplicate
    result = run_pipeline(raw_by_source)

    # --- Load
    out = Path(cfg.output_dir)
    write_csv(result.records, out / "final_dataset.csv")

    ps = result.per_source
    total = lambda key: sum(s[key] for s in ps.values())  # noqa: E731
    reasons: dict[str, int] = {}
    for s in ps.values():
        for reason, n in s["rejected_by_reason"].items():
            reasons[reason] = reasons.get(reason, 0) + n
    reconciles = all(s["collected"] - s["rejected"] - s["duplicates"] == s["final"] for s in ps.values())
    if not reconciles or total("final") != len(result.records):
        logger.error("Summary counts do not reconcile!")

    finished = datetime.now(timezone.utc)
    summary = {
        "run": {"start_time": started.isoformat(timespec="seconds"),
                "end_time": finished.isoformat(timespec="seconds"),
                "duration_seconds": round(time.perf_counter() - t0, 1)},
        "collected_per_source": {s: v["collected"] for s, v in ps.items()},
        "cleaned_per_source": {s: v["cleaned"] for s, v in ps.items()},
        "rejected_per_source": {s: v["rejected"] for s, v in ps.items()},
        "rejected_total": total("rejected"),
        "rejected_by_reason": reasons,
        "duplicates_detected": total("duplicates"),
        "duplicates_per_source": {s: v["duplicates"] for s, v in ps.items()},
        "duplicate_examples": result.duplicate_examples,
        "final_per_source": {s: v["final"] for s, v in ps.items()},
        "final_record_count": len(result.records),
        "scrape_details": scrape_details,
        "reconciliation": {
            "rule": "collected - rejected - duplicates = final (per source)",
            "holds": reconciles,
            "csv_rows_written": len(result.records),
        },
        "notes": "A record failing several rules is counted once in rejected_total "
                 "but once per rule in rejected_by_reason.",
    }
    write_summary(summary, out / "summary_report.json")
    logger.info("Run finished: %d final records in %.1fs", len(result.records),
                summary["run"]["duration_seconds"])
    return summary


def parse_args(argv=None) -> Config:
    d = Config()
    p = argparse.ArgumentParser(description="Scrape, clean, validate and consolidate two practice sites.")
    p.add_argument("--output-dir", type=Path, default=d.output_dir)
    p.add_argument("--log-dir", type=Path, default=d.log_dir)
    p.add_argument("--delay", type=float, default=d.delay, help="seconds between requests (default 0.5)")
    p.add_argument("--timeout", type=float, default=d.timeout)
    p.add_argument("--retries", type=int, default=d.retries)
    p.add_argument("--no-details", action="store_true",
                   help="skip book detail pages (faster; category/description stay empty)")
    p.add_argument("--max-pages", type=int, default=None, help="limit pages per source (for quick tests)")
    p.add_argument("--books-url", default=d.books_url)
    p.add_argument("--quotes-url", default=d.quotes_url)
    a = p.parse_args(argv)
    return Config(books_url=a.books_url, quotes_url=a.quotes_url, output_dir=a.output_dir,
                  log_dir=a.log_dir, delay=a.delay, timeout=a.timeout, retries=a.retries,
                  fetch_details=not a.no_details, max_pages=a.max_pages)


if __name__ == "__main__":
    summary = run(parse_args())
    sys.exit(0 if summary["final_record_count"] > 0 else 1)
