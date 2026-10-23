from agents.proposal import unverified_promises

MD = """## Deliverables
- REQ-001 city filter
## Investment
| REQ-001 | 10h | 600 USD |
Note: REQ-004 and REQ-005 require clarification and are not included in this total.
## Items To Confirm
- REQ-004 AI search
- REQ-005 favourites
"""


def test_hedged_mentions_are_not_promises() -> None:
    assert unverified_promises(MD, {"REQ-004", "REQ-005"}) == []


def test_unhedged_mention_in_committing_section_is_flagged() -> None:
    assert unverified_promises(MD, {"REQ-001"}) == ["REQ-001 in Deliverables", "REQ-001 in Investment"]
