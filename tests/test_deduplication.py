from processing.deduplication import find_duplicates, make_fingerprint

BOOK = {"source": "Books to Scrape", "author": None}
QUOTE = {"source": "Quotes to Scrape"}


def test_duplicates_ignore_case_and_spaces():
    records = [{**BOOK, "name_or_title": "Example Book Title"},
               {**BOOK, "name_or_title": "  Example Book Title "},
               {**BOOK, "name_or_title": "EXAMPLE BOOK TITLE"}]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 1 and len(dupes) == 2
    assert unique[0] is records[0]  # first occurrence is kept


def test_punctuation_is_ignored():
    a = {**BOOK, "name_or_title": "It's a Book: Part 1"}
    b = {**BOOK, "name_or_title": "Its a Book Part 1"}
    assert make_fingerprint(a) == make_fingerprint(b)


def test_different_titles_are_not_duplicates():
    unique, dupes = find_duplicates([{**BOOK, "name_or_title": "A"}, {**BOOK, "name_or_title": "B"}])
    assert len(unique) == 2 and not dupes


def test_quotes_use_author_and_first_50_chars():
    text = "x" * 60
    a = {**QUOTE, "author": "Jane Doe", "name_or_title": text + " ending one"}
    b = {**QUOTE, "author": " jane  DOE", "name_or_title": text + " ending two"}
    c = {**QUOTE, "author": "John Roe", "name_or_title": text + " ending one"}
    unique, dupes = find_duplicates([a, b, c])
    assert unique == [a, c] and dupes == [b]


def test_same_text_in_different_sources_is_not_duplicate():
    a = {**BOOK, "name_or_title": "Same"}
    b = {**QUOTE, "author": None, "name_or_title": "Same"}
    assert make_fingerprint(a) != make_fingerprint(b)


def test_empty_input():
    assert find_duplicates([]) == ([], [])
