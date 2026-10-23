"""Streamlit UI: project -> transcript -> pipeline -> review -> approve -> follow-up change report."""
from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
import streamlit as st

from scope.config import get_settings
from scope.kb_client import KBUnavailable
from scope.models import ChangeReport, Estimate
from scope.pipeline import Pipeline, build_pipeline

st.set_page_config(page_title="Meeting to Scope", layout="wide")


@st.cache_resource
def get_pipeline() -> Pipeline:
    return build_pipeline(get_settings())


def run(coro: Any) -> Any:
    return asyncio.run(coro)


pipe = get_pipeline()
db, settings = pipe.db, pipe.settings
st.title("Meeting to Scope")

try:
    h = run(pipe.kb.health())
    st.caption(f"Task 1 online · {h.get('chunks')} chunks · models: {pipe.models_label()} · rate {settings.hourly_rate:g} {settings.currency}/h")
except KBUnavailable as e:
    st.error(f"Task 1 (knowledge brain) is DOWN. Feasibility checks cannot run. {e}")

# ---- sidebar: projects ---------------------------------------------------
with st.sidebar:
    st.subheader("Projects")
    with st.form("new_project", clear_on_submit=True):
        name = st.text_input("Project name")
        client = st.text_input("Client")
        if st.form_submit_button("Create project") and name and client:
            db.create_project(name, client)
            st.rerun()
    projects = db.list_projects()
    if not projects:
        st.info("Create a project to start.")
        st.stop()
    labels = {p["id"]: f"#{p['id']} {p['name']} ({p['client']})" for p in projects}
    project_id = st.radio("Open", list(labels), format_func=labels.__getitem__, label_visibility="collapsed")

project = db.get_project(project_id)
assert project
baseline = db.baseline(project_id)
latest = db.latest_version(project_id)
st.subheader(f"{project['name']} · {project['client']}")

# ---- transcript input ----------------------------------------------------
mode = "follow-up" if baseline else "initial"
files = sorted(p.name for p in settings.transcripts_dir.glob("*.txt"))
c1, c2 = st.columns(2)
picked = c1.selectbox(f"Pick a transcript ({mode} meeting)", ["(none)"] + files)
uploaded = c2.file_uploader("...or upload a .txt transcript", type=["txt"])
transcript, filename = None, None
if uploaded is not None:
    transcript, filename = uploaded.read().decode("utf-8", errors="ignore"), uploaded.name
elif picked != "(none)":
    filename = picked
    transcript = (settings.transcripts_dir / picked).read_text(encoding="utf-8")

if latest and latest["status"] == "draft" and not uploaded and picked == "(none)":
    pass
elif transcript and st.button(f"Run pipeline on {filename}", type="primary"):
    try:
        with st.spinner("Analysing transcript, checking feasibility with Task 1, scoping, estimating, drafting..."):
            if baseline:
                run(pipe.run_followup(project_id, filename or "upload.txt", transcript))
            else:
                run(pipe.run_initial(project_id, filename or "upload.txt", transcript))
        st.rerun()
    except KBUnavailable as e:
        st.error(f"Task 1 is down: {e}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Pipeline failed: {e}")

version = latest
if version is None:
    st.info("No analysis yet. Pick a transcript and run the pipeline.")
    st.stop()

# ---- results -------------------------------------------------------------
badge = {"draft": "🟡 DRAFT (not approved)", "approved": "🟢 APPROVED BASELINE", "superseded": "⚪ superseded"}[version["status"]]
st.markdown(f"**Version {version['version_no']}** · {badge} · {version['models']}")
analysis, feas = version["analysis"], {f["requirement_id"]: f for f in version["feasibility"]}

if version["change_report"]:
    st.markdown("### Change report vs approved baseline")
    cr = ChangeReport.model_validate(version["change_report"])
    tag = {"added": ":green[ADDED]", "modified": ":orange[MODIFIED]", "removed": ":red[REMOVED]", "out_of_scope": ":violet[OUT OF SCOPE]"}
    for r in cr.added:
        st.markdown(f"{tag['added']} **{r.id}** {r.description}")
    for m in cr.modified:
        st.markdown(f"{tag['modified']} **{m.new.id}** {m.new.description}  \n  ↳ was: _{m.old.description}_ ({m.what_changed}, similarity {m.similarity})")
    for r in cr.removed:
        st.markdown(f"{tag['removed']} **{r.id}** {r.description}")
    for r in cr.out_of_scope:
        st.markdown(f"{tag['out_of_scope']} **{r.id}** {r.description}")
    for c in cr.constraint_changes:
        st.markdown(f":orange[CONSTRAINT] {c}")
    st.caption(f"{len(cr.unchanged)} requirement(s) unchanged. Re-estimated only: {', '.join(sorted(cr.affected_ids())) or 'none'}.")

tab_req, tab_est, tab_prop, tab_scope = st.tabs(["Requirements", "Estimate", "Proposal", "Scope"])
with tab_req:
    rows = []
    for r in analysis["requirements"]:
        f = feas.get(r["id"], {})
        rows.append({"id": r["id"], "requirement": r["description"], "priority": r["priority"], "status": r["status"],
                     "relation": r["relation"], "feasibility": f.get("classification", "-"),
                     "sources": " | ".join(f"{s['title']} ({s['score']})" for s in f.get("sources", [])[:3]),
                     "rationale": f.get("rationale", "")})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    with st.expander("Decisions, open questions, constraints"):
        st.write({"decisions": [d["text"] for d in analysis["decisions"]], "open_questions": analysis["open_questions"],
                  "constraints": analysis["constraints"]})
with tab_est:
    est = Estimate.model_validate(version["estimate"])
    if est.tasks:
        st.dataframe(pd.DataFrame([t.model_dump() for t in est.tasks]), width="stretch", hide_index=True)
        lo, li, hi = est.totals()
        st.markdown(f"**Total hours** low {lo:g} · likely {li:g} · high {hi:g} → likely cost **{li * settings.hourly_rate:,.0f} {settings.currency}**")
    else:
        st.write("Nothing estimable yet.")
with tab_prop:
    if version["proposal"]["unverified_promises"]:
        st.warning("Proposal still mentions unconfirmed items: " + "; ".join(version["proposal"]["unverified_promises"]))
    st.markdown(version["proposal"]["markdown"])
with tab_scope:
    st.json(version["scope"], expanded=False)

if version["status"] == "draft":
    st.warning("Nothing can be sent to the client until a human approves this version.")
    if st.button("Approve this version as the baseline", type="primary"):
        db.approve_version(version["id"])
        st.rerun()
