# Evals

Every task has one script in `evals/` that writes `evals/<task>/results.csv`. All three were run
on 2026-10-23 against the same two models, `claude-haiku-4-5` and `claude-sonnet-4-5`, through
Amazon Bedrock (ap-southeast-2). Cost per case is computed from the real token usage of each call
at Anthropic list prices (Haiku $1/$5, Sonnet $3/$15 per million input/output tokens).

## Summary

| Task | Model | Cases | Accuracy | Median latency (ms) | Cost / case |
|---|---|---|---|---|---|
| Task 1 knowledge brain | claude-haiku-4-5 | 20 | 19/20 (95%) | 3,430 | $0.0016 |
| Task 1 knowledge brain | claude-sonnet-4-5 | 20 | 20/20 (100%) | 5,301 | $0.0047 |
| Task 2 inbox agent | claude-haiku-4-5 | 40 | 39/40 (98%) | 1,481 | $0.0007 |
| Task 2 inbox agent | claude-sonnet-4-5 | 40 | 37/40 (92%) | 3,522 | $0.0022 |
| Task 3 meeting-to-scope | claude-haiku-4-5 | 20 | 19/20 (95%) | 165,245 | $0.0155 |
| Task 3 meeting-to-scope | claude-sonnet-4-5 | 20 | 19/20 (95%) | 181,837 | $0.0227 |

Task 1 index at eval time: 450 pages done, 2,935 chunks (text sections plus 40 screenshot
captions), 1,090 article pages still pending.

Task 3 latency is per pipeline run (five agents, one Task 1 query per requirement), divided
evenly across the checks of that run; it is not a per-question latency.

## Failures (7 of 160 cases)

- Task 1 / Haiku, T02 (two-article): "How do I import categories via a CSV file, and how do
  members then select their categories?" returned `insufficient_evidence`. Retrieval found both
  articles; Haiku judged the combined context insufficient. Sonnet answered it.
- Task 2 / Haiku, email 33: expected `complaint`, predicted `follow_up`. The email is a complaint
  about a promised call-back that never came, so both readings are defensible.
- Task 2 / Sonnet, email 17: expected `troubleshooting`, predicted `how_to`. Duplicate listings
  after an import; the customer asks how to remove them.
- Task 2 / Sonnet, email 25: expected `refund_cancel`, predicted `troubleshooting`. A double
  charge with a refund demand; Sonnet focused on the billing error rather than the refund.
- Task 2 / Sonnet, email 33: same as Haiku, `complaint` predicted as `follow_up`.
- Task 3 / Haiku, check C4: the follow-up meeting's logo redesign request was not flagged as
  out of scope in the change report.
- Task 3 / Sonnet, check A7: the location filter requirement was classified neither
  `existing_setting` nor `partial`, although the BD docs describe location search.

## Task 1: knowledge brain (`evals/eval_task1.py`)

20 fixed questions sent to `POST /query`, graded by rule:

| Kind | Count | Pass rule |
|---|---|---|
| direct | 10 | `answered` and the reply contains an expected keyword |
| two_article | 3 | `answered`, keyword present, and at least two distinct source URLs |
| caption_only | 2 | `answered` with a fact that exists only in a screenshot caption (e.g. "yellow" lightbulb, "ten" social fields) |
| abstain | 3 | `insufficient_evidence` with `needs_human: true` for off-topic questions |
| malformed | 2 | empty question must return HTTP 422; gibberish must abstain; never a 5xx |

The model is whatever the running server reports in `/health`, so the script is run once per
`ANSWER_MODEL`; rows for that model replace earlier rows in the CSV. Both models abstained on all
three off-topic questions (two of them without any model call, because retrieval scored below the
0.35 threshold), rejected the empty question, and answered both caption-only questions, which
shows the screenshot captions are retrievable.

Columns: `case_id, kind, question, model, http_status, status, n_sources, top_score, pass,
latency_ms, input_tokens, output_tokens, cost_usd, answer`.

## Task 2: inbox agent (`evals/eval_task2.py`)

The 40 non-holdout emails from `task2-inbox-agent/data/emails.json` are classified with each
model and compared with `expected_category`. The 10 holdout emails are never used. Accuracy is
exact match on the category. Haiku, the cheaper model and the one used in production for this
step, was more accurate than Sonnet on this set and three times cheaper.

Columns: `email_id, model, expected, predicted, correct, latency_ms, cost_usd`.

## Task 3: meeting to scope (`evals/eval_task3.py`)

Runs the full pipeline on `meeting_a.txt` (discovery call) and then `meeting_c.txt` (follow-up
for the same client) in a throwaway SQLite database, with the analyst model set to Sonnet and
then Haiku. 15 checks (A1 to A15) cover the initial run: requirement extraction, constraints such
as the six-week deadline, feasibility classes, scope exclusions and acceptance criteria, estimate
sanity (low <= likely <= high, configuration-only items at most one hour, custom work split into
at least two tasks), and a proposal with no unverified promises. Five checks (C1 to C5) cover the
change report: an added saved-search alert, a removed AI search, the deadline change from six to
four weeks, an out-of-scope logo redesign, and unchanged items keeping their baseline estimate.

Columns: `check, model, pass, latency_ms, cost_usd`.

## Reproducing

```bash
make run                         # all three services must be up for Task 1 and Task 2 evals
make eval                        # Task 1 with the current ANSWER_MODEL; restart with another model and rerun to compare
make eval-task2
make eval-task3
```

Then print the combined table with a short script over the three CSVs (per model: count,
accuracy, median `latency_ms`, mean `cost_usd`).

## Observations

- Abstaining is cheap: two of three off-topic questions never reached the model because the
  retrieval threshold caught them, and the responses took under 100 ms.
- Haiku is the better classifier here and Sonnet the better grounded answerer; the production
  split (Haiku for classify and captions, Sonnet for answers and drafts) matches the numbers.
- The remaining Task 1 miss is a judgement call by the model, not a retrieval failure, so the
  next lever is the answer prompt or a reranker, not the index.
