---
name: project-conversation-archive
description: "Discover and merge accessible conversations across configured AI assistants and exports into evidence-backed project retrospectives, branched topic maps, source statistics, asset indexes, and incremental Obsidian updates. Keeps low-depth conversations out of full project folders. Use for multi-task or substantial project retrospectives, not ordinary single-chat summaries."
---

# Project Conversation Archive

Maintain a traceable Obsidian knowledge base from accessible AI-assistant conversations and project assets. Users see only named **projects** and their **topics**; provider containers, repository anchors, and semantic assignment methods are internal evidence, not user-facing project types.

## Invariants

- Without a filter, discover all projects and conversations exposed by configured Codex/AI-assistant tools, supported local indexes, and the existing archive. Do not ask the user to enumerate project names or paths.
- Provider support is access-based, not a brand claim: inspect configured connectors, official exports, and documented readable indexes; report inaccessible assistants instead of implying their histories were read.
- Merge conversations across assistants when project evidence supports it. Similar titles or domains alone are insufficient.
- Give every readable source exactly one semantic disposition: named full retrospective, `pending`, `lightweight-nonretrospective`, or `excluded-nonproject`. The last requires the strict one-off gate; uncertainty is `pending`; clear shallow outcomes are lightweight. Preserve currently unreadable sources in a separate access bucket without erasing their last semantic assignment. No source is silently discarded.
- Read a source once, convert it to a compact source card, and aggregate documents from cards. Do not repeatedly reread unchanged transcripts.
- Preserve original conversations and project assets. Do not move, rename, archive, delete, or modify them during retrospective work.
- Write only inside the confirmed Obsidian Vault, except for the minimal Vault registry. Never store credentials or raw transcripts in the registry.
- Separate discussion, decision, implementation, test, release, and current production evidence. Never infer production status from code, a plan, tag, or release document.
- Cleanup discovery never authorizes deletion. Delete only exact candidates the user subsequently approves.

## Route by request

- **Locate a discussion only:** identify the source and stop; do not create or update the archive.
- **Initial retrospective:** inventory sources, create source cards, identify projects/topics, and build the archive.
- **Normal reuse:** default to incremental update. Read state first, process only new or changed sources, and update only affected projects.
- **Full rebuild:** do this only when the user explicitly asks, state is unusable, or source identity rules changed incompatibly.
- **Cleanup execution:** read [references/cleanup.md](references/cleanup.md) and require approval of exact candidate IDs or paths.

## Required workflow

1. **Resolve Vault and mode.** Read [references/vault-and-state.md](references/vault-and-state.md). Reuse a valid remembered Vault silently. If no valid Vault exists, ask for the one folder containing `.obsidian/` and remember it after validation.
2. **Discover metadata before content.** Read [references/providers.md](references/providers.md). List existing archive projects, registered mappings, connected providers, active/archived conversations, registered exports, and known supported local indexes. Record provider coverage. Never scan unrelated filesystem locations to guess assistant stores.
3. **Diff sources.** Compare `<provider>:<stable-id>`, update metadata, and fingerprints against the state index. Skip unchanged sources. Read changed sources only to the last processed turn when the provider supports it.
4. **Count and triage changed sources.** Follow [references/source-processing.md](references/source-processing.md). Apply the one-off non-project exclusion gate during the same read pass. Re-triage changed sources that were previously excluded.
5. **Create one structured source card per retained source.** Write the JSON contract in [references/source-processing.md](references/source-processing.md), including stable `problem_branches`; never substitute a prose Markdown card. Excluded sources keep only counts and an auditable reason in state.
6. **Resolve named projects and retrospective depth.** Follow [references/project-resolution.md](references/project-resolution.md). Project identity alone is insufficient: a named project must cite at least two real source-card branch references plus continuity evidence. Put ambiguous material in `待确认归属`; summarize clear shallow outcomes once in `轻量成果/00-轻量成果索引.md` without creating a project.
7. **Build topics and maps from cited source-card branches.** Follow [references/topic-maps-and-status.md](references/topic-maps-and-status.md). Each source has one primary topic for exclusive raw statistics and optional related topics for cross-links. A one-branch topic is a concise leaf with `map_type: none`; multi-branch topic maps and the project boundary map must contain a real branch or merge.
8. **Write the fixed archive shape only for full retrospectives.** Read [references/archive-layout.md](references/archive-layout.md). Use table-safe links, maintain one authoritative project asset index, and never generate empty ceremony for lightweight material.
9. **Validate, then publish.** Run `scripts/validate_archive.py <archive-root>`. Reconcile errors before writing final files to the Vault. Persist state after each successful batch so interruption can resume.

## Efficient execution

- For a first run, paginate each source once in bounded parallel batches; pagination within one source remains ordered.
- Strip system blocks, ambient UI context, tool payloads, local-command notices, and transient commentary before counting or summarizing.
- For supported Claude Code JSONL files, use `scripts/scan_claude_history.py` with explicit known index paths; do not point it at the home directory.
- Use `scripts/source_state.py diff` before transcript reads and `merge` after source metadata changes.
- After new or changed cards are written, run `scripts/source_state.py candidate-impact` to identify existing pending/lightweight cards that share an exact normalized project candidate or asset path. Re-evaluate only that card set; do not reread unchanged transcripts.
- Revalidate only assets cited by changed source cards or affected topics. Do not rescan an unchanged repository.
- If a provider lacks a stable timestamp/fingerprint, mark it `partially readable` and reread only that source when necessary; never substitute unknown counts with zero.
- If state uses schema 1, source cards are Markdown, or readable cards fail the JSON contract, use the resumable `migrate`, `migration-status`, and `complete-migration` flow in [references/vault-and-state.md](references/vault-and-state.md). Preserve source IDs and old decisions, but reread accessible retained sources once to recover real branches.

## Completion

Before handoff confirm: provider coverage and access methods are explicit; project names are user-recognizable; every named project passes the state-backed promotion gate; unchanged transcripts were skipped except for explicit migration; every disposition reconciles to the visible indexes; table links cannot split Markdown columns; every source card is valid JSON with stable branch references; every topic's sources, raw counts, semantic counts, and branch references reconcile to state/cards; one-branch topics do not manufacture maps and all required project/multi-branch maps contain real branches or merges; incomplete branches and assets are traceable; demoted generated folders are retired non-destructively; cleanup candidate totals exist with no unapproved deletion; state and logs are current; and the archive is inside the validated Vault.
