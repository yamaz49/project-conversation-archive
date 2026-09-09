# Project Conversation Archive

Turn scattered AI-assistant conversations into a traceable, continuously updated project knowledge base in Obsidian.

This Codex skill discovers accessible conversations, groups them into user-recognizable projects, extracts independent problem branches, builds topic maps, records project status and assets, and updates only the material that changed.

## What it produces

Substantial projects receive a consistent Obsidian structure:

```text
项目复盘/
├── 00-项目索引.md
├── 待确认归属/
├── 轻量成果/
└── <Project name>/
    ├── 00-项目对话总览.md
    ├── 01-主题边界图.md
    ├── 02-未完成主题与资产.md
    ├── 03-完成主题清理候选.md
    ├── 99-来源登记与更新日志.md
    ├── assets/
    └── topics/
```

Small but useful outcomes remain searchable in one shared lightweight index. Ambiguous fragments go to a review queue. Strict one-off general questions are counted without being turned into artificial projects.

## Core behavior

- Discovers conversations only through configured tools, official exports, or explicitly supplied readable indexes.
- Merges conversations across assistants only when project evidence supports the match.
- Converts each retained conversation into a compact JSON source card instead of storing raw transcripts.
- Organizes topics by independent problem branches and dependencies, not by chat chronology.
- Separates discussion, planning, implementation, testing, release, and current production evidence.
- Reuses saved state and processes only new or changed sources on later runs.
- Preserves original conversations and project files.
- Never deletes cleanup candidates without explicit approval for exact paths or candidate IDs.

## Install

Clone or copy this repository into your Codex skills directory:

```bash
git clone <repository-url> "${CODEX_HOME:-$HOME/.codex}/skills/project-conversation-archive"
```

Restart Codex after installation if the skill is not discovered immediately.

## Use

Invoke it explicitly:

```text
Use $project-conversation-archive to review all accessible project conversations and update my Obsidian archive.
```

On the first run, the skill asks for the Obsidian Vault only if it cannot reuse a previously confirmed Vault. It does not require the user to enumerate project names or project paths.

## Privacy and safety

The repository contains only reusable instructions, scripts, and tests. It does not contain a conversation archive, Vault state, account identifiers, credentials, personal paths, or user project data.

Runtime privacy rules are built into the skill:

- access is reported honestly per provider;
- credentials and raw transcripts are not written to the Vault registry;
- source cards contain paraphrased project facts rather than transcript copies;
- inaccessible sources are preserved as unknown instead of being invented or silently discarded;
- original conversations and project assets are not modified;
- cleanup discovery is separate from deletion authorization.

Review the generated archive before sharing it: source cards and project notes can still contain information from your own conversations because they are runtime outputs stored in your Vault, not files from this repository.

## Validation

The scripts use the Python standard library. Run the test suite with:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

Validate a generated archive with:

```bash
python3 scripts/validate_archive.py /path/to/your/vault/项目复盘
```

## Repository layout

- `SKILL.md` — entrypoint, routing, and safety invariants.
- `references/` — provider, source, project, topic, Vault, and cleanup contracts.
- `scripts/` — deterministic source-state, Claude Code inventory, and archive validation helpers.
- `tests/` — regression tests for migration, incremental matching, counts, maps, tables, and project promotion.

## License

MIT. See [LICENSE](LICENSE).
