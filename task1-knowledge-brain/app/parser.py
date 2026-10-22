"""Turn a support-article HTML page into title, sections and image urls."""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

HEADING_TAGS = ("h2", "h3", "h4")
INTRO_SECTION = "Introduction"


@dataclass
class Section:
    heading: str
    text: str


@dataclass
class ParsedArticle:
    title: str
    sections: list[Section]
    image_urls: list[str] = field(default_factory=list)

    @property
    def body_text(self) -> str:
        return "\n\n".join(s.text for s in self.sections if s.text)


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_article(html: str, url: str) -> ParsedArticle:
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one("article.article-body") or soup.select_one("article") or soup.body
    if body is None:
        return ParsedArticle(title="", sections=[])

    title_tag = body.select_one("h1") or soup.select_one("h1") or soup.title
    title = _clean(title_tag.get_text()) if title_tag else ""

    # Strip bits that are not article content.
    for junk in body.select("h1, p.the-article-link, script, style, nav"):
        junk.decompose()

    image_urls: list[str] = []
    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            full = urljoin(url, src)
            if full not in image_urls:
                image_urls.append(full)

    sections: list[Section] = []
    heading = INTRO_SECTION
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(t for t in buffer if t)
        if text.strip():
            sections.append(Section(heading=heading, text=text.strip()))
        buffer.clear()

    for node in body.descendants:
        if not isinstance(node, Tag):
            continue
        if node.name in HEADING_TAGS:
            flush()
            heading = _clean(node.get_text()) or heading
        elif node.name in ("p", "li", "pre", "td", "th") and not node.find(HEADING_TAGS):
            text = _clean(node.get_text(" "))
            if text:
                buffer.append(text)
    flush()
    return ParsedArticle(title=title, sections=sections, image_urls=image_urls)
