# AI Usage

> **Candidate: review and edit this file before submitting.** Everything marked `TODO` must be replaced with
> what you personally did, ran and found. The brief requires that you can explain every line.

## Tool used
**Claude (Anthropic), via the claude.ai chat interface.**

## What it was used for
- Generating the initial full implementation: scrapers, cleaning/validation/deduplication modules, `main.py`,
  unit tests, an end-to-end test against a local fake server, `README.md` and this file's first draft.
- Choosing the design (ETL layers, common data model, fingerprint-based deduplication, pagination via the `next` link).

## Representative prompts
1. "Build the full project" (given the assignment brief and a reference guide with stage-by-stage instructions).
2. TODO: add the prompts you actually wrote when you iterated on the code.

## Which parts were AI-assisted
All of the initial code and documentation. TODO: list the parts you rewrote or extended yourself.

## Issues found in AI output during development
- `clean_tags` de-duplicated tags *before* lowercasing, so `love` and `LOVE` both survived. Caught by a unit test; fixed by lowercasing first.
- Two expectations in the first draft of the end-to-end test were wrong (final quote count; number of failed detail pages). Caught when the test ran; the tests were corrected, not the code.
- TODO: add anything you notice yourself (selectors that differ on the real site, edge cases, wording in the README that does not match your run).

## How the result was tested and verified
- 38 automated tests (`python -m pytest`) passed in the AI's sandbox: cleaning, validation, deduplication,
  parsers on HTML snippets, and an end-to-end run against a local HTTP server that includes a duplicate book,
  an unparseable price, a 404 detail page, a 500 listing page, an unreachable site and a missing charset header.
- **The AI's sandbox could not reach books.toscrape.com or quotes.toscrape.com, so the pipeline was NOT run against the real sites by the AI.**
  - TODO: run `python main.py` yourself from a fresh virtual environment and record: runtime, final row count, rejected count, duplicates found (expected 0).
  - TODO: open `output/final_dataset.csv` and check that both sources appear, prices are numbers and ratings are 1-5; confirm `final_record_count` in the JSON equals the CSV row count.
  - TODO: spot-check a few records against the websites in your browser.
