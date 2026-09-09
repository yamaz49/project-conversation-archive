# Project resolution

Use this reference when assigning sources to projects or revising project boundaries.

## User-facing model

Users see only named projects and topics. Never ask them to understand or choose between “native”, “repository”, or “logical” project types. Those are internal evidence mechanisms.

A project is a sustained effort directed at one recognizable product, research objective, organizational capability, or deliverable system. It may exist entirely across projectless ChatGPT, Codex, Claude, or other supported conversations. A clear name or durable artifact establishes identity evidence, but does not by itself justify a full retrospective.

## Evidence order

Resolve the stable project key using the strongest available evidence:

1. Existing Obsidian project mapping or previously accepted stable key.
2. Native assistant project ID.
3. Repository remote plus canonical root.
4. Canonical project root.
5. Explicit stable product/project name with a coherent objective or durable deliverable; repetition across independent tasks strengthens this evidence.

The first four are hard anchors. The fifth is semantic project evidence. Keep `assignment_basis` internally in state and the source log; do not expose project categories in the global index.

## Full-retrospective promotion gate

First resolve project identity using the evidence order above. Then create or retain a full project retrospective only when both dimensions are satisfied:

1. **Coherent identity:** the name identifies a specific product, initiative, research program, organizational capability, or system; the sources pursue the same primary outcome; and no object of change conflicts with a hard anchor.
2. **Retrospective depth:** source cards expose at least two independent problem branches with distinct answer, decision, evidence, or remaining-work outcomes, and at least one continuity signal exists: multiple root sources, repeated revision within a substantial source, an accepted existing project mapping, active implementation or unresolved delivery work, or an explicit user request to track that effort as a project.

Store the promotion evidence on the project record so the validator can reproduce the decision:

```json
"retrospective_basis": {
  "branch_refs": ["provider:id#branch-a", "provider:id#branch-b"],
  "continuity_signals": [
    {"type": "multiple-root-sources", "evidence": "provider:one, provider:two"}
  ]
}
```

`branch_refs` contains at least two unique canonical references that resolve to cards assigned to this project. Each continuity signal has non-empty evidence and one of: `multiple-root-sources`, `repeated-revision`, `accepted-project-mapping`, `active-implementation`, `unresolved-delivery`, or `user-requested-tracking`. The validator checks the references and, for `multiple-root-sources`, requires at least two cited root sources. This record is the single owner of promotion eligibility; do not restate a competing rule elsewhere.

A single substantial conversation can pass when it contains multiple independent branches and a continuity signal. A few turns that produce one report, note, recommendation, skill, or other artifact remain useful, but do not become a full project merely because the artifact is durable. Generic similarity such as “both discuss banking” or “both mention AI” is insufficient.

Do not use raw turn count as the only gate. One long conversation may still be one narrow branch, while a shorter but iterative product conversation may establish several durable branches. Use the structured source cards, not invented subtopics, to make this decision.

## Lightweight retained material

Assign `project_key: lightweight-nonretrospective` when identity or outcome is clear enough to retain, but the full-retrospective promotion gate is not met. Typical cases are one small deliverable, one narrow research answer, or one topic with no independent sub-branches or ongoing work.

- Keep a structured source card so later turns can promote it without rereading unrelated sources.
- Set `primary_topic: null`, record `lightweight_reason`, and use `triage_confidence: high`.
- Do not create a project folder, topic note, map, or asset index.
- Add one row per lightweight source to the shared `轻量成果/00-轻量成果索引.md`, so useful outcomes and assets remain findable without pretending they are projects.
- Run `scripts/source_state.py candidate-impact` after new/changed cards, then re-evaluate only its matching unchanged pending/lightweight cards. Promote only when the combined cards create both coherent identity and retrospective depth.

This is distinct from `excluded-nonproject`: lightweight material may contain a useful artifact or consequential synthesis, while excluded material is a self-contained general one-off that needs no source card.

Examples of recognizable project names include `Customer Analytics Platform`, `Mobile Release Program`, `Personal Knowledge Base`, and `Enterprise Skill Governance`. Do not prepend storage classifications to these names.

## Pending assignment

Put only genuinely ambiguous project-relevant fragments in `待确认归属`. Cluster them by provisional topic without pretending the cluster is a project. Clear but shallow material belongs in `lightweight-nonretrospective`; obvious one-off non-project questions that pass the strict exclusion gate in `source-processing.md` remain in machine statistics. Do not prompt for project names during normal discovery.

On later runs, automatically move the source assignment when stronger evidence appears. Record the old and new project key in the update log. Preserve the source card and stable source ID.

Recognize `_未归属对话` as the legacy name for `待确认归属`. During an incremental update, create the new index and migrate assignments non-destructively; leave a compatibility note or link in the legacy folder until cleanup is separately approved.

## Merge and split rules

- Merge cross-assistant histories only when their project evidence converges.
- Never merge because titles are similar.
- If one project is renamed, preserve the old name as an alias.
- If one apparent project contains incompatible outcomes or owners, split it and record the correction; do not silently rewrite history.
- If an old repository disappeared, retain the project and mark current asset access `unknown` or `missing`; absence does not prove deletion or supersession.
