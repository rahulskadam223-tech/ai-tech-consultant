Write a client-ready project proposal in Markdown for a Brilliant Directories website project.

Client: {client}
Project: {project}
Hourly rate: {rate} {currency}

Scope of work (JSON):
{scope}

Estimate (JSON, hours per task with low/likely/high):
{estimate}

Feasibility (JSON). Requirement ids classed needs_clarification: {needs_clarification_ids}

Structure, using these exact level-2 headings in this order:
## Objective
## Current Situation
## Proposed Solution
## Deliverables
## Timeline
## Investment
## Exclusions
## Assumptions
## Acceptance Criteria
## Client Responsibilities
## Items To Confirm

Rules:
- Reference requirements by id (REQ-xxx) wherever you mention them.
- Items To Confirm must list every needs_clarification requirement id and say we will confirm feasibility before committing. These ids must NOT appear in Deliverables, Proposed Solution, Timeline, Investment or Acceptance Criteria.
- Investment: a table of deliverables with likely hours and cost at the hourly rate, a total (likely) and a range (low to high) in {currency}. Compute costs from the estimate, do not invent numbers.
- Timeline must respect the client's deadline constraint if there is one and say what is at risk.
- Friendly, confident, no hype. No promises beyond the deliverables. Return the Markdown only, no JSON, no code fences.
