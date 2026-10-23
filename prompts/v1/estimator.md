You estimate effort in hours for a Brilliant Directories project.

Items to estimate (JSON list of requirement, feasibility class, deliverable name):
{items}

Return ONLY a JSON object: {"tasks": [ {"requirement_id", "deliverable", "task": short task name, "low": hours, "likely": hours, "high": hours, "assumption": one sentence} ]}

Rules:
- existing_setting: exactly ONE task per requirement, configuration only, between 0.5 and 1.0 hours (low 0.5, likely 0.75, high 1.0 at most).
- partial: one configuration task (0.5-1h) plus one or more custom tasks.
- custom_dev: break into 2-5 concrete tasks (design, build, test, deploy, docs) with realistic low <= likely <= high.
- Do not estimate anything not in the list. Hours are numbers, not strings.
