import pytest

from processing.cleaning import (clean_price, clean_rating, clean_tags, clean_text,
                                 normalize_url, strip_quotes)


def test_clean_text_collapses_whitespace():
    assert clean_text("  Hello \n\t World\xa0! ") == "Hello World !"


@pytest.mark.parametrize("value", [None, "", "   ", "\xa0\n"])
def test_clean_text_empty_becomes_none(value):
    assert clean_text(value) is None


def test_strip_quotes():
    assert strip_quotes("\u201cThe world is round.\u201d") == "The world is round."
    assert strip_quotes('"Straight quotes"') == "Straight quotes"
    assert strip_quotes("\u201c\u201d") is None
    assert strip_quotes(None) is None


@pytest.mark.parametrize("raw,expected", [
    ("\u00a351.77", 51.77), ("\u00c2\u00a351.77", 51.77), ("\u00a31,234.50", 1234.5),
    ("10", 10.0), ("", None), (None, None), ("free", None),
])
def test_clean_price(raw, expected):
    assert clean_price(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("star-rating Three", 3), ("Five", 5), ("one", 1), ("star-rating", None), (None, None), ("Six", None),
])
def test_clean_rating(raw, expected):
    assert clean_rating(raw) == expected


def test_clean_tags():
    assert clean_tags([" Life ", "love", "LOVE", "Books"]) == "books;life;love"
    assert clean_tags([]) is None and clean_tags(None) is None


def test_normalize_url():
    assert normalize_url("page-2.html", base="https://Books.toscrape.com/catalogue/") == \
        "https://books.toscrape.com/catalogue/page-2.html"
    assert normalize_url("/author/x#top", base="http://quotes.toscrape.com/page/2/") == \
        "http://quotes.toscrape.com/author/x"
    assert normalize_url("ftp://x.com/a") is None
    assert normalize_url("relative/path") is None  # no base, not absolute
    assert normalize_url(None) is None
