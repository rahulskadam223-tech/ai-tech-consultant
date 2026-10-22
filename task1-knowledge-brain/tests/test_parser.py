from app.parser import parse_article

URL = "https://support.example.com/support/solutions/articles/1-mass-email"


def test_title_and_sections(sample_html: str) -> None:
    art = parse_article(sample_html, URL)
    assert art.title == "Can I Send A Mass Email Campaign?"
    assert [s.heading for s in art.sections] == ["Introduction", "How To Send", "Limits"]
    assert art.sections[0].text == "The built-in email system is for emailing active members."
    assert "Go to Members and click Email." in art.sections[1].text
    assert "Pick a template" in art.sections[1].text
    assert "Press send" in art.sections[1].text


def test_junk_is_stripped(sample_html: str) -> None:
    art = parse_article(sample_html, URL)
    body = art.body_text
    assert "Link:" not in body
    assert "https://example.com/a/1" not in body
    assert "For additional assistance" not in body  # footer is outside the article
    assert "Home" not in body


def test_image_urls_only_from_article_body(sample_html: str) -> None:
    art = parse_article(sample_html, URL)
    assert art.image_urls == [
        "https://support.example.com/images/screen1.png",
        "https://cdn.example.com/screen2.jpg",
    ]


def test_empty_page() -> None:
    art = parse_article("<html><body></body></html>", URL)
    assert art.title == ""
    assert art.sections == []
