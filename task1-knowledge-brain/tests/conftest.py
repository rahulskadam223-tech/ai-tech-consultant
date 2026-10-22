from __future__ import annotations

import pytest

from app.parser import ParsedArticle, Section

SAMPLE_HTML = """
<html><head><title>Can I Send Mass Email? | BD Support</title></head><body>
<nav><a href="/support/home">Home</a></nav>
<article class="article-body" id="article-body">
  <h1 class="post-title heading"> Can I Send A Mass Email Campaign? </h1>
  <p class="the-article-link"><small>Link: <a href="https://example.com/a/1">https://example.com/a/1</a></small></p>
  <p>The built-in email system is for emailing active members.</p>
  <p><br></p>
  <h2>How To Send</h2>
  <p>Go to <b>Members</b> and click Email.</p>
  <ul><li>Pick a template</li><li>Press send</li></ul>
  <img src="/images/screen1.png" alt="screen">
  <h3>Limits</h3>
  <p>Unsolicited email may be considered spam.</p>
  <img src="https://cdn.example.com/screen2.jpg">
</article>
<div class="article-footer-content"><p>For additional assistance email support.</p>
<img src="https://www.example.com/banner.jpg"></div>
</body></html>
"""


@pytest.fixture
def sample_html() -> str:
    return SAMPLE_HTML


@pytest.fixture
def sample_article() -> ParsedArticle:
    return ParsedArticle(
        title="Sample Article",
        sections=[
            Section("Introduction", "Intro text."),
            Section("Setup", "Step one.\nStep two."),
        ],
        image_urls=["https://example.com/img.png"],
    )
