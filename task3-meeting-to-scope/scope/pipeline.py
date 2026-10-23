"""Orchestrates the five agents for an initial meeting and for follow-ups."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `agents` imports work from anywhere

from agents import estimator, feasibility, proposal, scope as scope_agent, transcript_analyst  # noqa: E402

from .config import Settings  # noqa: E402
from .db import ProjectDB  # noqa: E402
from .kb_client import KnowledgeBrain  # noqa: E402
from .llm import LLM  # noqa: E402
from .matching import build_change_report, merged_requirements  # noqa: E402
from .models import Analysis, ChangeReport, Constraints, Estimate, EstimateTask, FeasibilityItem, Requirement  # noqa: E402


@dataclass
class Pipeline:
    settings: Settings
    db: ProjectDB
    llm: LLM
    kb: KnowledgeBrain

    def models_label(self) -> str:
        s = self.settings
        return f"analyst={s.analyst_model} writer={s.writer_model} feasibility={s.feasibility_model}"

    async def _scope_estimate_proposal(
        self, client: str, project: str, analysis: Analysis, feas: list[FeasibilityItem],
        only_ids: set[str] | None = None, carry_tasks: list[EstimateTask] | None = None,
    ) -> dict[str, Any]:
        s = self.settings
        sc = await scope_agent.run(scope_agent.ScopeInput(client=client, project=project, analysis=analysis,
                                                          feasibility=feas, model=s.writer_model), self.llm)
        est_out = await estimator.run(estimator.EstimatorInput(requirements=analysis.requirements, feasibility=feas,
                                                               scope=sc, model=s.writer_model, only_ids=only_ids), self.llm)
        tasks = list(carry_tasks or []) + est_out.estimate.tasks
        est = Estimate(tasks=tasks)
        prop = await proposal.run(proposal.ProposalInput(client=client, project=project, scope=sc, estimate=est,
                                                         feasibility=feas, hourly_rate=s.hourly_rate,
                                                         currency=s.currency, model=s.writer_model), self.llm)
        return {"scope": sc.model_dump(), "estimate": est.model_dump(), "proposal": prop.model_dump(),
                "estimated_ids": est_out.estimated_ids}

    async def run_initial(self, project_id: int, filename: str, transcript: str) -> int:
        """First meeting: analyst -> feasibility -> scope -> estimate -> proposal. Returns the draft version id."""
        p = self.db.get_project(project_id)
        assert p is not None
        meeting_id = self.db.add_meeting(project_id, filename, transcript, "initial")
        a = await transcript_analyst.run(transcript_analyst.AnalystInput(transcript=transcript, model=self.settings.analyst_model), self.llm)
        f = await feasibility.run(feasibility.FeasibilityInput(requirements=a.analysis.requirements, model=self.settings.feasibility_model), self.llm, self.kb)
        rest = await self._scope_estimate_proposal(p["client"], p["name"], a.analysis, f.items)
        payload = {"analysis": a.analysis.model_dump(), "feasibility": [i.model_dump() for i in f.items], **rest, "change_report": None}
        return self.db.save_version(project_id, meeting_id, payload, self.models_label())

    async def run_followup(self, project_id: int, filename: str, transcript: str) -> int:
        """New transcript on a project with an approved baseline -> change report + revised draft version."""
        p = self.db.get_project(project_id)
        base = self.db.baseline(project_id)
        if p is None or base is None:
            raise ValueError("Project has no approved baseline; approve the initial version first.")
        base_analysis = Analysis.model_validate(base["analysis"])
        base_feas = [FeasibilityItem.model_validate(x) for x in base["feasibility"]]
        base_est = Estimate.model_validate(base["estimate"])

        meeting_id = self.db.add_meeting(project_id, filename, transcript, "followup")
        a = await transcript_analyst.run(transcript_analyst.AnalystInput(
            transcript=transcript, baseline=base_analysis.requirements, model=self.settings.analyst_model), self.llm)
        report = build_change_report(base_analysis.requirements, a.analysis, base_analysis.constraints)

        revised_reqs = merged_requirements(report)
        affected = report.affected_ids()
        # Feasibility only for affected items; carry the rest from the baseline.
        new_feas = await feasibility.run(feasibility.FeasibilityInput(
            requirements=[r for r in revised_reqs if r.id in affected] + report.out_of_scope,
            model=self.settings.feasibility_model), self.llm, self.kb)
        kept_ids = {r.id for r in revised_reqs} - affected
        feas = [f for f in base_feas if f.requirement_id in kept_ids] + new_feas.items

        revised_analysis = a.analysis.model_copy(update={
            "requirements": revised_reqs + report.out_of_scope,
            "decisions": base_analysis.decisions + a.analysis.decisions,
            "open_questions": list(dict.fromkeys(base_analysis.open_questions + a.analysis.open_questions)),
            "constraints": Constraints(
                budget=a.analysis.constraints.budget or base_analysis.constraints.budget,
                deadline=a.analysis.constraints.deadline or base_analysis.constraints.deadline,
                other=list(dict.fromkeys(base_analysis.constraints.other + a.analysis.constraints.other)),
            ),
        })
        carry = [t for t in base_est.tasks if t.requirement_id in kept_ids]
        rest = await self._scope_estimate_proposal(p["client"], p["name"], revised_analysis, feas,
                                                   only_ids=affected, carry_tasks=carry)
        payload = {"analysis": revised_analysis.model_dump(), "feasibility": [i.model_dump() for i in feas],
                   **rest, "change_report": report.model_dump()}
        return self.db.save_version(project_id, meeting_id, payload, self.models_label())


def build_pipeline(settings: Settings) -> Pipeline:
    return Pipeline(settings=settings, db=ProjectDB(settings.task3_db),
                    llm=LLM(settings.prompts_dir, settings.anthropic_api_key), kb=KnowledgeBrain(settings.task1_url))
