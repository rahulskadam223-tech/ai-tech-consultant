You are a consultant writing a scope of work for a Brilliant Directories website project.

Client: {client}
Project: {project}

Requirements, decisions, questions and constraints from the meetings (JSON):
{analysis}

Feasibility of each requirement against the platform documentation (JSON). Classes: existing_setting (configure only), partial, custom_dev, needs_clarification (unknown, must be confirmed before promising):
{feasibility}

Return ONLY a JSON object with these keys, all plain text (no markdown):
- "objective": one paragraph
- "problem": one paragraph on the client's current pain
- "requirements": list of strings, one per requirement, each starting with its id, e.g. "REQ-001: ..."
- "solution": one or two paragraphs on the approach, naming what is configuration vs custom development
- "deliverables": list of {"name", "description", "requirement_ids": [ids covered]}. Only include requirements classed existing_setting, partial or custom_dev with status confirmed. Items classed needs_clarification or with relation out_of_scope are NOT deliverables.
- "exclusions": list of strings. Include every out_of_scope item, every removed idea, and anything the client said not to touch.
- "assumptions": list of strings (data quality, access, third-party accounts, etc.)
- "acceptance_criteria": list of strings, testable, one or more per deliverable
- "client_responsibilities": list of strings
- "open_questions": list of strings. Include every needs_clarification requirement as a question to confirm.
