from app.chunker import chunk_article, make_chunk_id
from app.parser import ParsedArticle, Section

URL = "https://example.com/articles/1"


def test_one_chunk_per_section_with_metadata(sample_article: ParsedArticle) -> None:
    chunks = chunk_article(sample_article, URL)
    assert [c.section for c in chunks] == ["Introduction", "Setup"]
    for c in chunks:
        assert c.title == "Sample Article"
        assert c.url == URL
        assert c.metadata == {"title": "Sample Article", "url": URL, "section": c.section, "kind": "text"}
        assert c.embed_text.startswith("Sample Article\n")


def test_long_section_is_split_on_paragraphs() -> None:
    paras = [f"Paragraph {i} " + "x" * 90 for i in range(10)]
    art = ParsedArticle(title="T", sections=[Section("Big", "\n".join(paras))])
    chunks = chunk_article(art, URL, limit=300)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    assert all(c.section == "Big" for c in chunks)
    assert "\n".join(c.text for c in chunks) == "\n".join(paras)  # nothing lost


def test_chunk_ids_are_deterministic_and_unique(sample_article: ParsedArticle) -> None:
    a = chunk_article(sample_article, URL)
    b = chunk_article(sample_article, URL)
    assert [c.id for c in a] == [c.id for c in b]
    assert len({c.id for c in a}) == len(a)
    assert a[0].id == make_chunk_id(URL, "Introduction", 0)


def test_repeated_headings_get_unique_ids() -> None:
    art = ParsedArticle(title="T", sections=[Section("Step", "a"), Section("Step", "b")])
    chunks = chunk_article(art, URL)
    assert len({c.id for c in chunks}) == 2
