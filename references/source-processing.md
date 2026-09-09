# Source processing and counting

Use this reference when reading providers, counting turns, or creating source cards.

## Discovery

Inspect existing archive/state first, then configured conversation tools, active and archived task indexes, and known supported local assistant indexes. Prefer list/search metadata before transcript reads. Do not crawl the home directory or parse undocumented binary databases.

Normalize source keys as `<provider>:<stable-conversation-id>`. A root conversation is one task. Attach subagents/sidechains to their root task and record them as branches; do not count them as additional tasks.

## Canonical counts

- **Task count:** distinct root source keys.
- **User-question count:** one for each user turn containing at least one non-empty request, question, decision, correction, or revision after exclusions. Multiple questions in one user turn still count as one raw question turn.
- **Assistant-answer count:** one for each conversation turn containing at least one substantive final answer, finding, proposal, decision, or delivered result. Multiple assistant chunks in the same turn count once.
- **Semantic-question count:** distinct problem nodes extracted from the content. One raw user turn may contain more than one semantic problem; repeated follow-ups may collapse into one.

Exclude system/developer prompts, ambient UI blocks, tool calls/results, local-command caveats, permission notices, task notifications, empty content, and transient progress commentary. Keep exclusion counts by reason. Unknown or unreadable counts remain `null`/unknown, never `0`.

Provider adapters must normalize their native message/chunk representation to these turn rules before aggregation. Do not count ChatGPT response chunks differently from Codex final answers.

## One-off non-project exclusion gate

Classify a source as `excluded-nonproject` only when **all** of these are supported by the readable content:

1. It is one root task with exactly one eligible user-question turn and one semantic problem.
2. It has no existing project mapping, repository/workspace anchor, named durable initiative, or link to another retained source.
3. It requests a self-contained general fact, definition, translation, conversion, or generic explanation that is reusable without the user's project context.
4. It creates no durable deliverable intended for later iteration, changes no file/code/configuration, records no project decision, and has no unresolved follow-up.
5. Classification confidence is high.

Do not exclude a source merely because it is short. Retain or place in `待确认归属` when it involves project/repository context, diagnosis from user logs or files, planning, research synthesis, consequential personal context, a reusable document or code artifact, an external action, or any ambiguous boundary. Multi-turn and multi-problem sources are never eligible for this shortcut.

For an excluded source, keep its stable ID, provider, fingerprint, task/question/answer counts, `project_key: excluded-nonproject`, `exclusion_reason`, and `triage_confidence: high` in machine state. Do not create a project, topic, source card, or per-source Obsidian note. Show only aggregate excluded counts in the global index. If its fingerprint changes, read and triage it again; exclusion is not permanent.

## One-pass source card

Create or update exactly one **JSON** card per retained changed source at the `.json` path registered in state. A prose Markdown summary is not a source card and must fail validation.

Extract independent problem branches during the transcript read. A branch has its own object of change, answer/decision direction, evidence owner, or unresolved outcome. Put follow-up wording and narrower questions under `refinements`; do not turn transcript chronology into separate branches.

Use this required contract:

```json
{
  "schema_version": 1,
  "source_key": "provider:id",
  "title": "source title",
  "project_candidates": ["name or hard key"],
  "goal": "paraphrased primary objective",
  "problem_branches": [
    {
      "branch_key": "stable-branch-key",
      "problem": "paraphrased problem",
      "refinements": [],
      "answer_direction": "concise answer/decision",
      "outcome": "artifact, decision, or unresolved state"
    }
  ],
  "decisions": [],
  "implementation_evidence": [],
  "verification_evidence": [],
  "release_evidence": [],
  "production_evidence": [],
  "open_items": [],
  "asset_paths": [],
  "task_count": 1,
  "question_count": 0,
  "answer_count": 0,
  "answer_count_method": "provider-normalized",
  "semantic_question_count": 0,
  "excluded_counts": {},
  "last_processed_turn_id": null
}
```

Every retained readable or partial source needs at least one complete `problem_branches` entry. Each branch requires non-empty `branch_key`, `problem`, `answer_direction`, and `outcome`; `refinements` is always an array. Paraphrase; do not copy the transcript question-by-question. Retain disagreements, reversals, and unresolved branches. Asset paths must come from reviewed sources or authorized project inspection, never invention.

`branch_key` is unique within its card. Every refinement is a non-empty paraphrased problem string. The canonical evidence reference is `<source_key>#<branch_key>`; project and topic records must cite this exact value. Set `semantic_question_count` to the number of branch roots plus their refinements:

```text
sum(1 + len(branch.refinements) for branch in problem_branches)
```

This makes the count and graph evidence reproducible without rereading a transcript.

After card extraction, apply the full-retrospective promotion gate in `project-resolution.md`. Do not invent extra branches merely to pass that gate. A clear source with only one narrow branch belongs in `lightweight-nonretrospective` unless it joins an already qualifying project.

## Topic accounting

Assign each root source one `primary_topic` for exclusive dashboard counts. Add zero or more `related_topics` for cross-links and supporting evidence. Project totals sum `task_count` (root `1`, attached sidechain `0`) and deduplicate root source keys; primary-topic totals must reconcile to project totals. Related-topic links never add to raw task/question/answer totals.

If a single source spans multiple branches, choose the primary topic from its dominant outcome/object of change. Record the rest as related topics instead of repeatedly splitting raw turn counts by model judgment.

## Efficient reads

- Paginate one source sequentially; process different sources in bounded parallel batches.
- Use the smallest provider output that still contains user text, final answers, stable turn IDs, file paths, and status evidence.
- Extract the card during the read pass. Do not retain full transcript arrays in working context after the card is complete.
- Persist the card and state after each batch.
- After the batch, run `scripts/source_state.py candidate-impact --state <state> --archive-root <archive-root> --changed <source-key> [...]`. Reapply assignment and promotion only to the returned `reconsider` cards. The command matches NFKC/case-normalized `project_candidates` or exact `asset_paths`; do not add broad semantic matching and do not reread unchanged transcripts.
