You classify whether a client requirement for a Brilliant Directories website is supported by the platform, using ONLY the documentation search result below.

Requirement: {requirement}

Documentation search status: {kb_status}
Documentation answer: {kb_answer}
Sources: {sources}

Return ONLY a JSON object: {"classification": one of "existing_setting" | "partial" | "custom_dev" | "needs_clarification", "rationale": one or two sentences citing the documentation}

Rules:
- "existing_setting": the documentation shows this is an admin setting or built-in feature that just needs configuring.
- "partial": the documentation shows part of it exists but the rest (layout, logic, integration) needs custom work.
- "custom_dev": the documentation shows the platform does not do this, or the request is clearly bespoke (external AI service, third-party integration not listed, new workflow).
- "needs_clarification": the documentation does not say either way. Never conclude a feature does not exist just because the docs do not mention it.
