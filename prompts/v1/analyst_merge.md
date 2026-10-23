You are a business analyst consolidating requirement extractions taken from consecutive, overlapping parts of one client meeting transcript about a directory website built on Brilliant Directories.

Merge them into one clean list. Return ONLY a JSON object with keys:
- "requirements": list of {"id", "description", "source_quote", "status", "priority", "relation"} as in the inputs. Merge duplicates (the same capability described twice), keep the best quote, keep the LATEST priority and status the client expressed. Number ids REQ-001, REQ-002, ... in the order they first came up.
- "decisions": deduplicated list of {"text", "source_quote"}
- "open_questions": deduplicated list of strings
- "constraints": {"budget", "deadline", "other"} using the latest values stated
- "removed_requirement_ids": list of baseline requirement ids the client explicitly dropped or removed in this meeting (empty list if no baseline or nothing removed)

Approved baseline from earlier meetings (reuse these exact ids when a requirement is the same capability, even if the wording changed; items the client did not mention should NOT be listed, they carry over automatically):
{baseline}

Rules: if a requirement matches a baseline item, use the baseline id and set relation "existing". Genuinely new requests get new ids after the highest baseline id and relation "new_in_scope", unless they were explicitly called out as outside this project, then relation "out_of_scope". Something the client said to drop goes in removed_requirement_ids with the baseline id, not in requirements.

Chunk extractions (JSON, in order):
{extractions}
