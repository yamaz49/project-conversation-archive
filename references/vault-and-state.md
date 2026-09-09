# Vault and incremental state

Read this reference for every archive creation or update.

## Vault registry

Store the remembered Vault in `~/.codex/project-conversation-archive/vault-registry.json`. The registry may contain only normalized Vault paths, stable project keys, archive-relative project folder names, aliases, and confirmation timestamps. It must not contain conversation text, credentials, counts, or project content.

Resolution order:

1. Reuse a valid project mapping whose Vault exists and contains `.obsidian/`.
2. Otherwise reuse the valid confirmed default Vault and add the project mapping silently.
3. Prompt only when no valid remembered Vault exists, validation fails, or the user requests a change/forget action.
4. Prompt with one simple request: `请粘贴包含 .obsidian 文件夹的 Obsidian Vault 路径。`
5. If a child path is supplied, inspect only its parent chain, resolve the nearest Vault root, and ask once for confirmation.

Forgetting a mapping removes only that registry entry. It never deletes archive notes.

## Archive state

Keep machine state at:

```text
<vault>/项目复盘/.project-conversation-archive/
├── source-index.json
└── source-cards/
    └── <safe-provider-and-id>.json
```

`source-index.json` schema version 2:

```json
{
  "schema_version": 2,
  "updated_at": "ISO-8601",
  "providers": {
    "codex": {
      "coverage": "available",
      "access_method": "app-tool",
      "checked_at": "ISO-8601",
      "discovered_root_count": 0,
      "readable_root_count": 0
    }
  },
  "projects": {
    "stable-project-key": {
      "name": "User-recognizable project name",
      "aliases": [],
      "archive_relative_path": "Project name",
      "status": "in-progress",
      "summary": "Current evidence-backed outcome",
      "cleanup_candidate_count": 0,
      "cleanup_confirmation": "not-required",
      "assignment_basis": ["internal evidence only"],
      "retrospective_basis": {
        "branch_refs": ["provider:id#branch-a", "provider:id#branch-b"],
        "continuity_signals": [
          {"type": "active-implementation", "evidence": "Reviewed implementation evidence"}
        ]
      }
    }
  },
  "sources": {
    "provider:stable-id": {
      "provider": "provider",
      "source_id": "stable-id",
      "title": "source title",
      "source_updated_at": "ISO-8601 or null",
      "fingerprint": "provider fingerprint or null",
      "last_processed_turn_id": "stable turn id or null",
      "task_count": 1,
      "question_count": 0,
      "answer_count": 0,
      "answer_count_method": "provider-normalized",
      "semantic_question_count": 0,
      "excluded_counts": {},
      "project_key": "stable-project-key, pending, lightweight-nonretrospective, or excluded-nonproject",
      "primary_topic": "stable-topic-key, pending, or null",
      "related_topics": [],
      "card_path": ".project-conversation-archive/source-cards/provider-id.json",
      "access_status": "readable",
      "pending_reason": null,
      "exclusion_reason": null,
      "lightweight_reason": null,
      "triage_confidence": null
    }
  }
}
```

Allowed provider coverage: `available`, `partially-readable`, `not-configured`, `permission-denied`, `unsupported`. Allowed source access: `readable`, `partial`, `missing`, `deleted-unknown`, `permission-denied`.

State contains identifiers, counts, fingerprints, assignments, exclusion decisions, project promotion evidence, cleanup totals, and card locations. Source cards contain paraphrased summaries. Neither stores raw transcript bodies, secrets, payment data, or credentials. `pending_reason` is required for `pending`; `exclusion_reason` and `triage_confidence` are required for `excluded-nonproject`, whose `card_path` is null; `lightweight_reason` and `triage_confidence: high` are required for `lightweight-nonretrospective`, which keeps its JSON card but has `primary_topic: null`.

## Schema 1 migration

Schema 2 makes structured JSON source cards and retrospective-depth decisions authoritative. When schema 1 state, a Markdown card path, or an invalid readable card is found, stage the migration so interruption cannot leave a half-published schema:

```text
scripts/source_state.py migrate --state <old-state> --archive-root <archive-root> --output <staging-state>
scripts/source_state.py migration-status --state <staging-state> --archive-root <archive-root>
scripts/source_state.py complete-migration --state <staging-state> --archive-root <archive-root> --output <candidate-state>
```

`migrate` preserves old facts, assigns deterministic JSON card destinations, records each old card path, and writes `migration.status: in-progress` plus pending source keys. Rerun it safely on the staging state after interruption. For each pending key:

1. Preserve provider/source stable IDs, counts, fingerprints, historical project decisions, and access states.
2. Reread the accessible retained source once and create its required JSON card with real `problem_branches`; never infer branches from a shallow legacy summary.
3. Reapply the full-retrospective promotion gate. Move clear but shallow sources to `lightweight-nonretrospective`; keep ambiguous sources pending.
4. Record project demotions/promotions and count changes in dated logs. Retire generated project notes as specified in `archive-layout.md`; never delete them or move original project assets.
5. Run `migration-status`; it removes nothing and reports which cards remain invalid or absent.
6. Run `complete-migration` only when no pending card remains. It removes the in-progress marker but preserves migration history. Validate the candidate state and archive, then atomically publish it as `source-index.json`.

Normal `diff`/`merge` refuse schema 1 and an in-progress migration. This is a one-time targeted card migration, not permission to rediscover or rewrite unchanged source content repeatedly.

## Incremental algorithm

1. Read state before archive Markdown.
2. List current provider metadata and build an inventory.
3. Run `scripts/source_state.py diff --state <state> --inventory <inventory>`.
4. Skip `unchanged` sources completely.
5. For `changed` sources, read newest turns until `last_processed_turn_id`; if unsupported, reread that source once.
6. Read `new` sources once and create cards.
   During that read, apply the strict one-off exclusion and full-retrospective gates. Re-triage every changed source previously marked `excluded-nonproject` or `lightweight-nonretrospective`.
7. Run `scripts/source_state.py candidate-impact --state <state> --archive-root <archive-root> --changed <source-key> [...]`. Re-evaluate the returned unchanged pending/lightweight cards from their existing cards without rereading transcripts.
8. Mark `missing` sources inaccessible but preserve their last card and historical conclusions.
9. Update only affected projects, topic statistics, asset references, global index rows, and dated update logs.
10. Persist state after each successful bounded batch. Never make the whole run depend on one final write.

Every inventory must declare its covered provider with top-level `provider`, or all covered providers with `providers`. A source can become `missing` only when its provider was covered by that inventory. Refreshing one assistant must never mark another assistant's sources missing.

If state is missing but the Markdown archive exists, reconstruct identifiers and project/topic mappings from `99-来源登记与更新日志.md` and topic frontmatter once, then create state. Do not rebuild all summaries solely because machine state is absent.
