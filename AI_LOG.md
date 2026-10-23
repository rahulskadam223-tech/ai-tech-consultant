# AI log

How AI was used to build this project, what it got wrong, and what a human had to decide.
The code was written with Claude Code (Claude Fable 5.1) from written specifications, one task at
a time, with the human setting the scope, reviewing results and deciding on credentials, models
and infrastructure. This log is reconstructed from the sessions and the git history.

## Timeline

| When (IST) | What | Commit |
|---|---|---|
| 2026-10-22 evening | Task 1 specified and built: crawler, parser, chunker, Chroma store, FastAPI API, prompts, 12 tests, eval script. First crawl of 150 pages. | `9436d35` |
| 2026-10-23 morning | Task 2 specified and built: 50-email dataset, classify/draft pipeline, learning rule, Streamlit UI, 15 tests, eval. Both tasks switched to Amazon Bedrock. | `cc5f8f1` |
| 2026-10-23 midday | Task 3 built: five agents, change reports for follow-ups, Streamlit UI, 16 tests, eval on two transcripts. | `3c790e9` |
| 2026-10-23 afternoon | Datasets un-ignored and committed; eval results committed; Task 1 eval expanded to 20 cases and run on two models; docs. | `f200e5b` to `0321d1d` |

## What the AI did well

- Produced the whole repository structure, three working services and 43 passing tests from
  the specifications with no manual code edits, and kept to the requested constraints
  (HTTP-only coupling, prompts as files, type hints, async network calls).
- Checked the real sitemap and article HTML before writing the parser, so the selectors
  (`article.article-body`, `h1.post-title`, the "Link:" line) were right first time.
- Chose a retrieval threshold from observed scores rather than a guess, and verified the
  abstain path with a real off-topic query before reporting Task 1 as working.
- Wrote evals that grade by rule (status, keywords, source counts, HTTP codes) so they run
  without a second model as judge, and used real token usage for cost.

## Mistakes and how they were caught

1. **Duplicate chunk IDs.** The first chunker hashed `url|heading|index`, so six articles that
   repeat a heading failed to upsert into Chroma. Caught by the first crawl's failure log; fixed
   by using the chunk's running position, with a new test. The resumable crawl then picked up
   exactly those six pages.
2. **Unhelpful 500 when no API key is configured.** The Anthropic SDK raises a plain `TypeError`
   in that case, not an `APIError`. Caught by smoke-testing `/query` on a machine without
   credentials; the API now returns a 502 that names the missing variable.
3. **Datasets silently excluded from git.** A blanket `data/` rule in `.gitignore` ignored the
   50-email dataset and the three meeting transcripts, so two commits shipped without their
   inputs. Found while reviewing the tree before the final submission; the rule now ignores only
   generated files (Task 1 crawl output and SQLite databases).
4. **Two sessions working on the same checkout.** A Task 2 build session paused mid-task; a later
   session finished Task 2 with Bedrock support and built Task 3. When the first session resumed
   it overwrote two committed files with older versions. Git made this visible (`git status`
   showed unexpected modifications), the files were restored from the commit and duplicate tests
   removed. Lesson: one session per checkout, or branch per session.
5. **Model behaviour at the edges.** The evals surfaced one Haiku abstain on a two-article
   question and a handful of category confusions where the email genuinely straddles two
   categories (a complaint about a missed call-back vs a follow-up). These are recorded in
   EVALS.md rather than tuned away with special cases.

## Human decisions

- Scope and ordering: one task per session, stop after each, no building ahead.
- Models: `claude-haiku-4-5` for classification and captions, `claude-sonnet-4-5` for grounded
  answers and drafts, both taken from `.env` so evals can swap them. The AI noted that newer
  Haiku 5.5 and Sonnet 5.5 exist; the chosen models were kept for the submission.
- Infrastructure: switching inference to Amazon Bedrock with a bearer token, and the crawl
  budget (150 pages on the first night, 450 by submission).
- The learning rule's thresholds (20 clean sends, two edits to disable) and the never-auto list.
- Credentials were never shared with the AI; it worked from `.env.example` and the running
  services.

## Where AI output should still be checked

- Generated drafts in Task 2 are always reviewed by a person before sending; auto-send
  eligibility is a flag the UI shows, not an action it takes.
- Task 3 proposals carry an `unverified_promises` list; anything in it must be edited by the
  consultant before the proposal goes to a client.
- Task 1 answers cite sources, and `insufficient_evidence` responses create the chance for an
  expert to add the missing knowledge via `/escalations`.
