"""Streamlit review UI for the inbox agent. Run: streamlit run app.py"""
from __future__ import annotations

import asyncio
from typing import Any

import anthropic
import streamlit as st

from inbox.config import get_settings
from inbox.kb_client import KBUnavailable
from inbox.models import NEVER_AUTO, Email
from inbox.pipeline import Pipeline, build_pipeline, load_emails

st.set_page_config(page_title="Inbox Agent", layout="wide")


@st.cache_resource
def get_pipeline() -> Pipeline:
    return build_pipeline(get_settings())


@st.cache_data
def get_emails() -> list[Email]:
    return load_emails(get_settings().emails_file)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


pipe = get_pipeline()
emails = get_emails()
db = pipe.db

# ---- header: Task 1 health + learning state ------------------------------
st.title("Inbox Agent")
try:
    health = run(pipe.kb.health())
    st.caption(f"Task 1 online · {health.get('chunks')} chunks indexed · answers by {health.get('answer_model')}")
    kb_up = True
except KBUnavailable as e:
    st.error(f"Task 1 (knowledge brain) is DOWN. Product questions cannot be answered. {e}")
    kb_up = False

states = db.all_states()
if states:
    cols = st.columns(len(states))
    for col, s in zip(cols, states):
        if s.category in NEVER_AUTO:
            status = "never auto"
        else:
            status = "AUTO-SEND ELIGIBLE" if s.auto_send_eligible else f"{s.consecutive_clean}/{db.threshold} clean"
        col.metric(s.category, status, delta=f"{s.consecutive_edits} edits in a row" if s.consecutive_edits else None)
else:
    st.caption("No decisions yet. Per-category counters appear here after the first send.")
with st.expander("Eligibility change log"):
    log = db.eligibility_log()
    st.table(log) if log else st.write("No changes yet.")

# ---- left: email list ----------------------------------------------------
decided = db.decided_email_ids()
left, right = st.columns([1, 2])
with left:
    st.subheader("Inbox")
    labels = {
        e.id: f"{'✅' if e.id in decided else '✉️'} #{e.id} {e.subject[:40]}" + (" (holdout)" if e.holdout else "")
        for e in emails
    }
    selected_id = st.radio("Emails", list(labels), format_func=labels.__getitem__, label_visibility="collapsed")

email = next(e for e in emails if e.id == selected_id)

# ---- right: email, analysis, draft, actions -------------------------------
with right:
    st.subheader(email.subject)
    st.caption(f"From: {email.from_} · expected: {email.expected_category} · risk: {email.risk}")
    st.text(email.body)

    row = db.latest_draft(email.id)
    if row is None:
        if st.button("Analyze & draft reply", type="primary"):
            try:
                with st.spinner("Classifying, searching docs, drafting..."):
                    run(pipe.process(email))
                st.rerun()
            except KBUnavailable as e:
                st.error(f"Task 1 is down, cannot look up the docs: {e}")
            except anthropic.AuthenticationError:
                st.error("Anthropic rejected the API key. Set a real ANTHROPIC_API_KEY in the repo-root .env and restart.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Pipeline failed: {e}")
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("Category", row["category"])
    c2.metric("Urgency / risk", f"{row['urgency']} / {row['risk']}")
    c3.metric("Needs human", "yes" if row["needs_human"] else "no")
    st.write(f"**Summary:** {row['summary']}")
    st.write(f"**Next action:** {row['next_action']}")

    st.markdown("**Sources from Task 1**" + (f" · status: `{row['kb_status']}`" if row["kb_status"] else ""))
    if row["retrieved_sources"]:
        for s in row["retrieved_sources"]:
            st.markdown(f"- [{s['title']}]({s['url']}) · score {s['score']}")
    elif row["kb_status"] == "insufficient_evidence":
        st.warning("Docs had no answer. Draft promises to follow up; do not send a guess.")
    else:
        st.caption("Not a product question, Task 1 not consulted.")

    if row["outcome"]:
        st.success(f"Decision: {row['outcome']} (edited: {bool(row['was_edited'])}) at {row['decided_at']}")
        st.markdown("**Sent reply**")
        st.text(row["final_reply"])
        st.stop()

    st.markdown("**Draft reply**")
    st.text(row["draft"])

    def decide(outcome: str, final: str) -> None:
        state, reason = db.record_decision(row["id"], outcome, final)  # type: ignore[arg-type]
        print(f"[send simulated] email #{email.id} -> {email.from_} ({outcome})\n{final}\n")
        if reason:
            st.toast(f"{state.category}: auto-send eligible = {state.auto_send_eligible} ({reason})")
        st.rerun()

    b1, b2, b3 = st.columns(3)
    if b1.button("Approve & send", type="primary"):
        decide("approved", row["draft"])
    with b2.popover("Edit then send"):
        edited = st.text_area("Edit the reply", value=row["draft"], height=300, key=f"edit-{row['id']}")
        if st.button("Send edited", key=f"send-edit-{row['id']}"):
            decide("edited", edited)
    with b3.popover("Reject & write my own"):
        own = st.text_area("Your reply", height=300, key=f"own-{row['id']}")
        if st.button("Send my reply", key=f"send-own-{row['id']}", disabled=not own.strip()):
            decide("rejected", own)
