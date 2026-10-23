import pytest

from scope.chunking import chunk_words


def test_short_text_is_one_chunk() -> None:
    assert chunk_words("one two three", size=10, overlap=2) == ["one two three"]
    assert chunk_words("   ", size=10, overlap=2) == []


def test_chunks_overlap_and_cover_everything() -> None:
    words = [f"w{i}" for i in range(2000)]
    chunks = chunk_words(" ".join(words), size=800, overlap=100)
    assert len(chunks) == 3
    assert chunks[0].split()[0] == "w0" and chunks[-1].split()[-1] == "w1999"
    # consecutive chunks share exactly `overlap` words
    assert chunks[0].split()[-100:] == chunks[1].split()[:100]
    assert all(len(c.split()) <= 800 for c in chunks)
    assert set(" ".join(chunks).split()) == set(words)


def test_bad_params() -> None:
    with pytest.raises(ValueError):
        chunk_words("a b", size=5, overlap=5)
