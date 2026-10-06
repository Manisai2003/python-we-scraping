from processing.validation import validate_record


def book(**kw):
    rec = {"source": "Books to Scrape", "source_url": "https://x.com/b", "name_or_title": "T",
           "price": 10.0, "rating": 3, "author": None}
    rec.update(kw)
    return rec


def quote(**kw):
    rec = {"source": "Quotes to Scrape", "source_url": "https://x.com/p", "name_or_title": "Q",
           "price": None, "rating": None, "author": "A"}
    rec.update(kw)
    return rec


def test_valid_records():
    assert validate_record(book()) == []
    assert validate_record(quote()) == []
    assert validate_record(book(price=None, rating=None)) == []  # "if present" rules


def test_each_rule():
    assert validate_record(book(source="Other")) == ["unknown_source"]
    assert validate_record(book(name_or_title=None)) == ["missing_name"]
    assert validate_record(book(source_url="ftp://x")) == ["invalid_url"]
    assert validate_record(book(source_url=None)) == ["invalid_url"]
    assert validate_record(book(price=-1)) == ["invalid_price"]
    assert validate_record(book(price="10")) == ["invalid_price"]
    assert validate_record(book(price=float("nan"))) == ["invalid_price"]
    assert validate_record(book(rating=0)) == ["invalid_rating"]
    assert validate_record(book(rating=6)) == ["invalid_rating"]
    assert validate_record(book(rating=True)) == ["invalid_rating"]
    assert validate_record(quote(author=None)) == ["missing_author"]


def test_multiple_problems_reported():
    assert set(validate_record(book(name_or_title="", source_url="x", rating=9))) == \
        {"missing_name", "invalid_url", "invalid_rating"}
