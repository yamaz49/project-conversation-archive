# Obsidian archive layout

Read this reference before writing or updating archive files.

## Fixed user-facing structure

Every project that passes the full-retrospective promotion gate uses the same structure, regardless of which assistant or storage mechanism exposed it:

```text
<vault>/项目复盘/
├── 00-项目索引.md
├── 待确认归属/
│   ├── 00-待确认归属总览.md
│   ├── 99-来源登记与更新日志.md
│   └── topics/
├── 轻量成果/
│   └── 00-轻量成果索引.md
├── .project-conversation-archive/
│   ├── source-index.json
│   ├── source-cards/
│   └── retired-project-notes/
└── <项目名称>/
    ├── 00-项目对话总览.md
    ├── 01-主题边界图.md
    ├── 02-未完成主题与资产.md
    ├── 03-完成主题清理候选.md
    ├── 99-来源登记与更新日志.md
    ├── assets/
    │   └── 00-资产总索引.md
    └── topics/
        └── <主题>.md
```

Create the pending and lightweight shared folders only while their buckets are non-empty. Create all five numbered project notes, the asset index, and at least one topic note only after the project passes the gate in `project-resolution.md`. If no verified asset or cleanup candidate exists, state that explicitly instead of omitting the file. `lightweight-nonretrospective` sources appear only in the shared lightweight index and never receive this project structure.

## Global index

Report named project, topic count, task count, user-question count, assistant-answer count, summary, and current evidence-backed project status. Do not show internal project types. Keep `待确认归属` visible as pending material, not as a project category.

Also show a compact coverage summary with discovered root tasks divided into `已归档项目`, `待确认归属`, `轻量成果`, `已跳过的一次性非项目问答`, and `不可读取/未知`. These categories must reconcile to machine state.

Use these exact table headers so counts can be validated:

```markdown
| 项目 | task | 问题 | 回答 | topic | 状态 | 总结 |
| 处置 | 来源数 | task | 问题 | 回答 |
```

Each project overview uses:

```markdown
| 主题 | task | 问题 | 回答 | 语义节点 | 状态 |
```

The project boundary note starts with:

```yaml
---
topic_node_map: {"stable-topic-key": "T1"}
---
```

Every value is the real Mermaid node for that topic. When the project has only one topic, the required branch can run from that topic node to its cited problem branches.

The shared lightweight index uses one row per source:

```markdown
| 成果 | 来源 | task | 问题 | 回答 | 结果摘要 | 资产 |
```

`来源` is the stable source key. This index is not a project or topic collection.

When pending sources exist, `待确认归属/00-待确认归属总览.md` uses one row per source:

```markdown
| 线索 | 来源 | task | 问题 | 回答 | 待确认原因 |
```

The `待确认原因` matches `pending_reason` in state; this folder remains a review queue, not a project.

## Markdown table safety

Inside a Markdown table, never emit an unescaped Wikilink alias separator. Use one of these forms:

```markdown
| [[topics/主题名称\|主题名称]] | in-progress |
| [[topics/主题名称]] | in-progress |
```

The raw form `[[target|label]]` is valid outside a table but splits a Markdown table into extra columns. The validator must reject every unescaped alias pipe inside a table and inconsistent column counts before publication.

## Topic notes

The project `01-主题边界图.md` begins with:

```yaml
---
topic_node_map: {"stable-topic-key": "T1"}
---
```

Every topic key appears exactly once and maps to a real unique node in the project Mermaid graph.

Use YAML frontmatter:

```yaml
---
topic_key: stable-topic-key
topic: stable display name
status: in-progress
source_task_ids: ["provider:id"]
primary_source_task_ids: ["provider:id"]
related_source_task_ids: []
problem_branch_refs: ["provider:id#branch-a", "provider:id#branch-b"]
task_count: 1
question_count: 1
answer_count: 1
semantic_question_count: 3
map_type: tree
branch_node_map: {"provider:id#branch-a": "B1", "provider:id#branch-b": "B2"}
first_reviewed: YYYY-MM-DD
last_reviewed: YYYY-MM-DD
---
```

The body contains boundary, answer/decision summary, evidence, remaining work, and links to `assets/00-资产总索引` and `99-来源登记与更新日志`. Include a genuinely branched tree/network only when two or more branches are cited; use `map_type: none` for a one-branch leaf.

## Source register

Record stable source key, title, provider, access state, primary topic, related topics, raw counts, semantic count, and last processed time. Keep historical sources when they become unavailable. Record corrections, project moves, topic-boundary changes, count changes, and status changes in dated update entries.

## Asset ownership

`assets/00-资产总索引.md` is the single authoritative asset classification per project. Each path appears once with:

| Exact path | Related topics | Kind | Role | Evidence state | Version/commit |
| --- | --- | --- | --- | --- | --- |

Topic notes link to rows or sections; they do not duplicate full inventories. Inspect only paths cited by changed cards or affected topics. Original project files remain authoritative and in place.

The asset-index path rows must exactly match the distinct `asset_paths` in source cards assigned to that project. Use an empty table when there are no cited assets; do not invent or broadly scan paths to fill it.

## Cleanup summary

Each project state record owns `cleanup_candidate_count` and `cleanup_confirmation`, where confirmation is `not-required`, `awaiting-user`, `approved-partial`, or `approved-all`. `03-完成主题清理候选.md` contains exactly one summary row:

```markdown
| 状态 | 候选文件数 |
```

The row must match state. Candidate details follow the contract in `cleanup.md`; approval changes the confirmation field but never substitutes for rechecking exact paths before deletion.

## Updates

- Read machine state first; read only affected Markdown after the diff.
- Update changed sections instead of rebuilding all notes.
- Preserve earlier conclusions using dated correction or `superseded` records.
- When a source moves from `待确认归属` to a project, update indexes and source assignment without deleting its history.
- Recognize legacy `_未归属对话`; preserve a compatibility link until separately approved for cleanup.
- Treat only `archive_relative_path` values in state as active project folders. If a prior generated project no longer passes promotion, move its notes intact to `.project-conversation-archive/retired-project-notes/<date>/<old-project>/`, verify the move, and list that retired copy as a cleanup candidate. This is retirement, not deletion; never move original project assets.
- Validate table syntax, wikilinks, required files, topic frontmatter, map topology, JSON source-card contracts, state keys, unique source IDs, dispositions, and primary-topic totals before publishing.
