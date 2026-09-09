# Cleanup discovery and execution

Read this reference only when building cleanup candidates or executing an approved cleanup.

## Discovery

Completion does not make files disposable. Inspect only authorized project scope and only assets connected to completed topics. If source cards and asset state contain no obsolete, duplicate, generated, expired, or replaced signal, record zero verified candidates and skip a broad cleanup scan.

Each candidate must include:

| Candidate ID | Exact path | Type | Obsolescence evidence | Replacement/recovery | Risk | Proposed action |
| --- | --- | --- | --- | --- | --- | --- |

Use `needs-review` when callers, ownership, migration, or production references are uncertain. Count candidates by risk. Plans, modified working-tree files, old-looking directories, and missing project roots are not deletion evidence.

## Execution

1. Require the user to approve exact candidate IDs or unambiguous paths.
2. Re-resolve and re-check every path immediately before deletion.
3. Skip anything whose identity, state, or risk changed.
4. Delete only approved paths; prefer recoverable operations when available.
5. Record removed and skipped items in the project update log, including recovery information.

Never turn a generic “clean up” request into automatic deletion.
