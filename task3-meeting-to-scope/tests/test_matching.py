from scope.matching import match_to_baseline, next_id, similarity
from scope.models import Requirement

BASE = [
    Requirement(id="REQ-001", description="Filter search results by city and locality", status="confirmed", priority="must"),
    Requirement(id="REQ-002", description="Price range filter shown in lakhs and crores", status="confirmed", priority="must"),
    Requirement(id="REQ-005", description="AI natural language search over listings", status="unclear", priority="could"),
]


def test_match_by_id_wins() -> None:
    r = Requirement(id="REQ-002", description="completely different words")
    m, score = match_to_baseline(r, BASE)
    assert m is BASE[1] and score == 1.0


def test_match_by_similar_description() -> None:
    r = Requirement(id="REQ-099", description="Search filter by locality and city, grouping nearby localities")
    m, score = match_to_baseline(r, BASE)
    assert m is BASE[0] and score >= 0.45


def test_unrelated_description_does_not_match() -> None:
    r = Requirement(id="REQ-099", description="Redesign the company logo")
    m, score = match_to_baseline(r, BASE)
    assert m is None and score < 0.45


def test_similarity_is_symmetric_and_bounded() -> None:
    a, b = "Mobile view fixes", "Fix the mobile view"
    assert 0 <= similarity(a, b) <= 1 and similarity(a, b) == similarity(b, a)
    assert similarity(a, a) == 1.0


def test_next_id_after_highest() -> None:
    assert next_id(BASE) == "REQ-006"
    assert next_id([]) == "REQ-001"


def test_wrong_id_on_unrelated_text_falls_back_to_similarity() -> None:
    r = Requirement(id="REQ-001", description="One-hour agent training session on the new filters")
    m, _ = match_to_baseline(r, BASE)
    assert m is None  # id says REQ-001 but the wording has nothing to do with the city filter
