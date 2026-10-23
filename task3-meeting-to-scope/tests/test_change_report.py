from scope.matching import build_change_report, merged_requirements
from scope.models import Analysis, Constraints, Requirement

BASE = [
    Requirement(id="REQ-001", description="Filter search results by city and locality", status="confirmed", priority="must"),
    Requirement(id="REQ-002", description="Price range filter in lakhs and crores", status="confirmed", priority="must"),
    Requirement(id="REQ-003", description="Map view of search results", status="confirmed", priority="should"),
    Requirement(id="REQ-004", description="AI natural language search over listings", status="unclear", priority="could"),
]
BASE_C = Constraints(deadline="6 weeks", budget="4000")


def followup() -> Analysis:
    return Analysis(
        requirements=[
            Requirement(id="REQ-001", description="Filter search results by city and locality, grouping nearby localities", status="confirmed", priority="must", relation="existing"),
            Requirement(id="REQ-003", description="Map view of search results", status="confirmed", priority="could", relation="existing"),
            Requirement(id="REQ-010", description="Saved search alerts with a daily email digest of new matching listings", status="confirmed", priority="must"),
            Requirement(id="REQ-011", description="Redesign the company logo", status="unclear", priority="could", relation="out_of_scope"),
        ],
        removed_requirement_ids=["REQ-004"],
        constraints=Constraints(deadline="4 weeks", budget="4000"),
    )


def test_change_report_buckets() -> None:
    r = build_change_report(BASE, followup(), BASE_C)
    assert [x.id for x in r.added] == ["REQ-005"]            # new id after highest baseline id
    assert "Saved search" in r.added[0].description
    assert [x.id for x in r.removed] == ["REQ-004"]
    assert [x.id for x in r.out_of_scope] == ["REQ-006"]
    assert {m.new.id for m in r.modified} == {"REQ-001", "REQ-003"}
    what = {m.new.id: m.what_changed for m in r.modified}
    assert "description" in what["REQ-001"]
    assert what["REQ-003"] == "priority should -> could"
    assert [x.id for x in r.unchanged] == ["REQ-002"]         # not mentioned -> carried over
    assert r.constraint_changes == ["deadline: 6 weeks -> 4 weeks"]


def test_affected_and_merged() -> None:
    r = build_change_report(BASE, followup(), BASE_C)
    assert r.affected_ids() == {"REQ-001", "REQ-003", "REQ-005"}
    merged = merged_requirements(r)
    assert [m.id for m in merged] == ["REQ-001", "REQ-002", "REQ-003", "REQ-005"]
    assert all(m.relation != "out_of_scope" for m in merged)


def test_removed_item_mentioned_again_is_ignored() -> None:
    f = followup()
    f.requirements.append(Requirement(id="REQ-004", description="AI natural language search over listings", relation="existing"))
    r = build_change_report(BASE, f, BASE_C)
    assert [x.id for x in r.removed] == ["REQ-004"]
    assert all(x.id != "REQ-004" for x in r.unchanged + r.added + [m.new for m in r.modified])


def test_no_changes_means_everything_unchanged() -> None:
    r = build_change_report(BASE, Analysis(), BASE_C)
    assert len(r.unchanged) == 4 and not (r.added or r.modified or r.removed or r.out_of_scope or r.constraint_changes)


def test_two_items_cannot_claim_the_same_baseline_id() -> None:
    f = Analysis(requirements=[
        Requirement(id="REQ-003", description="Map view of search results", relation="existing"),
        Requirement(id="REQ-003", description="Map view of search results with clustering of pins", relation="existing"),
    ])
    r = build_change_report(BASE, f, BASE_C)
    ids = [x.id for x in r.unchanged] + [m.new.id for m in r.modified] + [x.id for x in r.added]
    assert len(ids) == len(set(ids))
    assert len(r.added) == 1 and r.added[0].id == "REQ-005"
