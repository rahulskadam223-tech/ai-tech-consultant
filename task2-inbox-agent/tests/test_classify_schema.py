import pytest

from inbox.models import Classification, ParseError, parse_json_object, validate_classification, validate_draft

GOOD = '{"category": "how_to", "urgency": "low", "risk": "low", "summary": "How to change the site logo"}'


def test_valid_classification() -> None:
    c = validate_classification(GOOD)
    assert isinstance(c, Classification)
    assert c.category == "how_to" and c.urgency == "low"


def test_fenced_json_and_prose_are_tolerated() -> None:
    text = "Sure! Here it is:\n```json\n" + GOOD + "\n```"
    assert validate_classification(text).summary == "How to change the site logo"
    assert parse_json_object('noise {"a": 1} trailing')["a"] == 1


@pytest.mark.parametrize(
    "bad",
    [
        '{"category": "spam", "urgency": "low", "risk": "low", "summary": "x"}',  # unknown category
        '{"category": "how_to", "urgency": "urgent", "risk": "low", "summary": "x"}',  # bad urgency
        '{"category": "how_to", "urgency": "low", "risk": "low"}',  # missing summary
        '{"category": "how_to", "urgency": "low", "risk": "low", "summary": ""}',  # empty summary
        "not json at all",
        "[1, 2, 3]",
    ],
)
def test_invalid_classification_rejected(bad: str) -> None:
    with pytest.raises(ParseError):
        validate_classification(bad)


def test_draft_schema() -> None:
    d = validate_draft('{"reply": "Hi", "sources": ["https://x"], "needs_human": false, "next_action": "Send"}')
    assert d.sources == ["https://x"] and d.needs_human is False
    with pytest.raises(ParseError):
        validate_draft('{"reply": "Hi", "needs_human": "maybe", "next_action": "Send"}')
