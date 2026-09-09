#!/usr/bin/env python3
"""Validate an archive against its state, source cards, and visible summaries."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


REQUIRED_PROJECT_FILES = (
    "00-项目对话总览.md", "01-主题边界图.md", "02-未完成主题与资产.md",
    "03-完成主题清理候选.md", "99-来源登记与更新日志.md",
)
REQUIRED_TOPIC_KEYS = (
    "topic_key", "topic", "status", "source_task_ids", "primary_source_task_ids",
    "related_source_task_ids", "problem_branch_refs", "task_count", "question_count",
    "answer_count", "semantic_question_count", "map_type", "branch_node_map",
    "first_reviewed", "last_reviewed",
)
REQUIRED_SOURCE_KEYS = (
    "provider", "source_id", "task_count", "question_count", "answer_count",
    "answer_count_method", "semantic_question_count", "excluded_counts", "project_key",
    "primary_topic", "related_topics", "card_path", "access_status", "pending_reason",
    "exclusion_reason", "lightweight_reason", "triage_confidence",
)
REQUIRED_CARD_KEYS = (
    "schema_version", "source_key", "title", "project_candidates", "goal",
    "problem_branches", "decisions", "implementation_evidence", "verification_evidence",
    "release_evidence", "production_evidence", "open_items", "asset_paths", "task_count",
    "question_count", "answer_count", "answer_count_method", "semantic_question_count",
    "excluded_counts", "last_processed_turn_id",
)
ALLOWED_STATUS = {
    "discussed", "planned", "in-progress", "implemented-locally", "tested", "released",
    "production-verified", "blocked", "superseded", "unknown",
}
ALLOWED_MAP_TYPES = {"none", "tree", "network"}
ALLOWED_PROVIDER_COVERAGE = {
    "available", "partially-readable", "not-configured", "permission-denied", "unsupported",
}
ALLOWED_ACCESS_METHOD = {
    "app-tool", "connector", "official-api", "official-export", "local-index",
    "registered-export", "none",
}
ALLOWED_SOURCE_ACCESS = {"readable", "partial", "missing", "deleted-unknown", "permission-denied"}
ALLOWED_CONTINUITY = {
    "multiple-root-sources", "repeated-revision", "accepted-project-mapping",
    "active-implementation", "unresolved-delivery", "user-requested-tracking",
}
ALLOWED_CLEANUP_CONFIRMATION = {"not-required", "awaiting-user", "approved-partial", "approved-all"}
SPECIAL_ROOT_DIRS = {"待确认归属", "_未归属对话", "轻量成果"}
DISPOSITION_LABELS = {
    "archived-projects": "已归档项目",
    "pending": "待确认归属",
    "lightweight-nonretrospective": "轻量成果",
    "excluded-nonproject": "已跳过的一次性非项目问答",
    "unreadable-or-unknown": "不可读取/未知",
}
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(.*?)\n```", re.DOTALL)
NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
EDGE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_-]*)(?:\[[^\]]*\])?\s*"
    r"(?:-->|==>|-\.[^\n]*?\.->)(?:\|[^|\n]*\|)?\s*"
    r"([A-Za-z][A-Za-z0-9_-]*)",
    re.MULTILINE,
)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip().strip("'\"")
    return result


def json_field(data: dict[str, str], key: str, expected: type, errors: list[str], context: str) -> Any:
    raw = data.get(key)
    try:
        value = json.loads(raw) if raw is not None else None
    except json.JSONDecodeError:
        errors.append(f"{context}: frontmatter {key} must be valid inline JSON")
        return expected()
    if not isinstance(value, expected):
        errors.append(f"{context}: frontmatter {key} must be a {expected.__name__}")
        return expected()
    return value


def int_field(data: dict[str, str], key: str, errors: list[str], context: str) -> int | None:
    raw = data.get(key, "")
    if not raw.isdigit():
        errors.append(f"{context}: frontmatter {key} must be a non-negative integer")
        return None
    return int(raw)


def unescaped_pipe_count(line: str) -> int:
    count = 0
    escaped = False
    for char in line:
        if char == "\\" and not escaped:
            escaped = True
            continue
        if char == "|" and not escaped:
            count += 1
        escaped = False
    return count


def split_table_row(line: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.strip()[1:-1]:
        if char == "\\" and not escaped:
            escaped = True
            current.append(char)
            continue
        if char == "|" and not escaped:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        escaped = False
    cells.append("".join(current).strip())
    return cells


def markdown_tables(path: Path) -> list[tuple[list[str], list[list[str]]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index + 1 < len(lines):
        if not (lines[index].strip().startswith("|") and lines[index].strip().endswith("|")):
            index += 1
            continue
        header = split_table_row(lines[index])
        separator = split_table_row(lines[index + 1])
        if len(separator) != len(header) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            index += 1
            continue
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
            rows.append(split_table_row(lines[index]))
            index += 1
        tables.append((header, rows))
    return tables


def find_table(path: Path, header: list[str], errors: list[str]) -> list[list[str]]:
    matches = [rows for found, rows in markdown_tables(path) if found == header]
    if len(matches) != 1:
        errors.append(f"{path.name}: expected exactly one table with header {' / '.join(header)}")
        return []
    return matches[0]


def visible_cell(cell: str) -> str:
    value = re.sub(r"<!--.*?-->", "", cell).strip()
    match = re.fullmatch(r"\[\[(.*?)\]\]", value)
    if match:
        target = match.group(1).replace("\\|", "|")
        return target.split("|", 1)[1] if "|" in target else Path(target).name
    return value


def active_markdown(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root)
        if relative.parts[:2] == (".project-conversation-archive", "retired-project-notes"):
            continue
        result.append(path)
    return result


def validate_markdown_tables(root: Path, errors: list[str]) -> None:
    for path in active_markdown(root):
        expected: int | None = None
        in_fence = False
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                expected = None
                continue
            if in_fence or not (stripped.startswith("|") and stripped.endswith("|")):
                expected = None
                continue
            for match in WIKILINK.finditer(line):
                if re.search(r"(?<!\\)\|", match.group(1)):
                    errors.append(
                        f"{path.relative_to(root)}:{line_number}: unescaped wikilink alias pipe inside Markdown table"
                    )
            columns = unescaped_pipe_count(stripped) - 1
            if expected is None:
                expected = columns
            elif columns != expected:
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: table has {columns} columns; expected {expected}"
                )


def sum_counts(sources: dict[str, dict[str, Any]], keys: list[str], field: str) -> int | None:
    values = [sources.get(key, {}).get(field) for key in keys]
    return sum(values) if all(isinstance(value, int) for value in values) else None


def parse_count(cell: str) -> int | None:
    value = visible_cell(cell)
    return int(value) if value.isdigit() else None


def branch_ref_parts(reference: str) -> tuple[str, str] | None:
    if "#" not in reference:
        return None
    source_key, branch_key = reference.rsplit("#", 1)
    return (source_key, branch_key) if source_key and branch_key else None


def validate_source_card(
    root: Path, source_key: str, source: dict[str, Any], errors: list[str], required: bool,
) -> dict[str, Any] | None:
    card_path = source.get("card_path")
    if not isinstance(card_path, str) or not card_path:
        if required:
            errors.append(f"state source {source_key}: retained readable source needs card_path")
        return None
    path = (root / card_path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        errors.append(f"state source {source_key}: card_path escapes archive root")
        return None
    if path.suffix != ".json":
        errors.append(f"state source {source_key}: source card must be JSON, not {path.suffix or 'extensionless'}")
        return None
    if not path.is_file():
        if required:
            errors.append(f"state source {source_key}: missing card {card_path}")
        return None
    try:
        card = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"state source {source_key}: invalid source card JSON: {exc}")
        return None
    if not isinstance(card, dict):
        errors.append(f"state source {source_key}: source card must be an object")
        return None
    for key in REQUIRED_CARD_KEYS:
        if key not in card:
            errors.append(f"state source {source_key}: source card missing key {key}")
    if card.get("schema_version") != 1:
        errors.append(f"state source {source_key}: source card schema_version must be 1")
    if card.get("source_key") != source_key:
        errors.append(f"state source {source_key}: source card source_key mismatch")
    for field in ("task_count", "question_count", "answer_count", "semantic_question_count"):
        if field in card and card.get(field) != source.get(field):
            errors.append(f"state source {source_key}: source card {field} differs from state")
    for field in (
        "project_candidates", "problem_branches", "decisions", "implementation_evidence",
        "verification_evidence", "release_evidence", "production_evidence", "open_items", "asset_paths",
    ):
        if field in card and not isinstance(card[field], list):
            errors.append(f"state source {source_key}: source card {field} must be an array")
    branches = card.get("problem_branches")
    if not isinstance(branches, list) or not branches:
        errors.append(f"state source {source_key}: source card needs at least one problem branch")
        return card
    branch_keys: set[str] = set()
    semantic_count = 0
    for index, branch in enumerate(branches):
        if not isinstance(branch, dict):
            errors.append(f"state source {source_key}: problem branch {index} must be an object")
            continue
        for field in ("branch_key", "problem", "answer_direction", "outcome"):
            if not isinstance(branch.get(field), str) or not branch[field].strip():
                errors.append(f"state source {source_key}: problem branch {index} needs non-empty {field}")
        branch_key = branch.get("branch_key")
        if isinstance(branch_key, str):
            if branch_key in branch_keys:
                errors.append(f"state source {source_key}: duplicate branch_key {branch_key!r}")
            branch_keys.add(branch_key)
        refinements = branch.get("refinements")
        if not isinstance(refinements, list) or not all(isinstance(value, str) and value.strip() for value in refinements):
            errors.append(f"state source {source_key}: problem branch {index} refinements must be non-empty strings")
            refinements = []
        semantic_count += 1 + len(refinements)
    if card.get("semantic_question_count") != semantic_count:
        errors.append(
            f"state source {source_key}: semantic_question_count {card.get('semantic_question_count')!r} "
            f"does not equal branch/refinement total {semantic_count}"
        )
    return card


def load_state(root: Path, errors: list[str], warnings: list[str]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    path = root / ".project-conversation-archive" / "source-index.json"
    if not path.is_file():
        errors.append("missing .project-conversation-archive/source-index.json")
        return {}, {}
    try:
        state = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid source-index.json: {exc}")
        return {}, {}
    if not isinstance(state, dict):
        errors.append("source-index.json must be an object")
        return {}, {}
    if state.get("schema_version") != 2:
        errors.append("source-index.json schema_version must be 2")
    if isinstance(state.get("migration"), dict):
        errors.append("source-index.json has an incomplete migration; complete it before publication")
    providers = state.get("providers")
    if not isinstance(providers, dict):
        errors.append("source-index.json providers must be an object")
    else:
        for provider, metadata in providers.items():
            if not isinstance(metadata, dict):
                errors.append(f"state provider {provider}: metadata must be an object")
                continue
            if metadata.get("coverage") not in ALLOWED_PROVIDER_COVERAGE:
                errors.append(f"state provider {provider}: invalid coverage {metadata.get('coverage')!r}")
            if metadata.get("access_method") not in ALLOWED_ACCESS_METHOD:
                errors.append(f"state provider {provider}: invalid access_method {metadata.get('access_method')!r}")
            if not isinstance(metadata.get("checked_at"), str) or not metadata["checked_at"]:
                errors.append(f"state provider {provider}: checked_at must be a non-empty string")
            for field in ("discovered_root_count", "readable_root_count"):
                if not isinstance(metadata.get(field), int) or metadata[field] < 0:
                    errors.append(f"state provider {provider}: {field} must be a non-negative integer")
            if isinstance(metadata.get("discovered_root_count"), int) and isinstance(metadata.get("readable_root_count"), int):
                if metadata["readable_root_count"] > metadata["discovered_root_count"]:
                    errors.append(f"state provider {provider}: readable_root_count exceeds discovered_root_count")
    if not isinstance(state.get("projects"), dict):
        errors.append("source-index.json projects must be an object")
        state["projects"] = {}
    sources = state.get("sources")
    if not isinstance(sources, dict):
        errors.append("source-index.json sources must be an object")
        state["sources"] = {}
        return state, {}
    cards: dict[str, dict[str, Any]] = {}
    for source_key, source in sources.items():
        if not isinstance(source, dict):
            errors.append(f"state source {source_key}: must be an object")
            continue
        for field in REQUIRED_SOURCE_KEYS:
            if field not in source:
                errors.append(f"state source {source_key}: missing key {field}")
        if source_key != f"{source.get('provider')}:{source.get('source_id')}":
            errors.append(f"state source {source_key}: provider/source_id do not match key")
        for field in ("task_count", "question_count", "answer_count", "semantic_question_count"):
            value = source.get(field)
            if value is not None and (not isinstance(value, int) or value < 0):
                errors.append(f"state source {source_key}: {field} must be a non-negative integer or null")
        if not isinstance(source.get("excluded_counts"), dict):
            errors.append(f"state source {source_key}: excluded_counts must be an object")
        if not isinstance(source.get("related_topics"), list) or not all(
            isinstance(value, str) and value for value in source.get("related_topics", [])
        ) or len(source.get("related_topics", [])) != len(set(source.get("related_topics", []))):
            errors.append(f"state source {source_key}: related_topics must be an array")
        if source.get("access_status") not in ALLOWED_SOURCE_ACCESS:
            errors.append(f"state source {source_key}: invalid access_status {source.get('access_status')!r}")
        project_key = source.get("project_key")
        if project_key == "excluded-nonproject":
            if source.get("triage_confidence") != "high" or not isinstance(source.get("exclusion_reason"), str) or not source["exclusion_reason"].strip():
                errors.append(f"state source {source_key}: excluded source needs a reason and high confidence")
            if source.get("question_count") != 1 or source.get("semantic_question_count") != 1:
                errors.append(f"state source {source_key}: excluded source must have one question and one semantic problem")
            if source.get("card_path") is not None:
                warnings.append(f"state source {source_key}: excluded source should not keep a source card")
            continue
        if project_key == "lightweight-nonretrospective":
            if source.get("triage_confidence") != "high" or not isinstance(source.get("lightweight_reason"), str) or not source["lightweight_reason"].strip():
                errors.append(f"state source {source_key}: lightweight source needs a reason and high confidence")
            if source.get("primary_topic") is not None:
                errors.append(f"state source {source_key}: lightweight source primary_topic must be null")
        elif project_key == "pending":
            if source.get("primary_topic") not in {None, "pending"}:
                errors.append(f"state source {source_key}: pending source primary_topic must be pending or null")
            if not isinstance(source.get("pending_reason"), str) or not source["pending_reason"].strip():
                errors.append(f"state source {source_key}: pending source needs pending_reason")
        elif project_key not in state["projects"]:
            errors.append(f"state source {source_key}: unknown project_key {project_key!r}")
        elif not isinstance(source.get("primary_topic"), str) or source.get("primary_topic") in {"", "pending"}:
            errors.append(f"state source {source_key}: named-project source needs a stable primary_topic")
        required = source.get("access_status") in {"readable", "partial"}
        if required and (not isinstance(source.get("semantic_question_count"), int) or source["semantic_question_count"] < 1):
            errors.append(f"state source {source_key}: retained readable source needs semantic_question_count >= 1")
        card = validate_source_card(root, source_key, source, errors, required)
        if card is not None:
            cards[source_key] = card
    for provider, metadata in state.get("providers", {}).items():
        if not isinstance(metadata, dict):
            continue
        provider_sources = [
            source for source in sources.values()
            if isinstance(source, dict) and source.get("provider") == provider
        ]
        discovered = sum(
            source.get("task_count", 0) for source in provider_sources if isinstance(source.get("task_count"), int)
        )
        readable = sum(
            source.get("task_count", 0) for source in provider_sources
            if source.get("access_status") == "readable" and isinstance(source.get("task_count"), int)
        )
        if metadata.get("discovered_root_count") != discovered:
            errors.append(f"state provider {provider}: discovered_root_count does not reconcile to sources")
        if metadata.get("readable_root_count") != readable:
            errors.append(f"state provider {provider}: readable_root_count does not reconcile to sources")
    return state, cards


def branch_lookup(cards: dict[str, dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for source_key, card in cards.items():
        for branch in card.get("problem_branches", []):
            if isinstance(branch, dict) and isinstance(branch.get("branch_key"), str):
                result[f"{source_key}#{branch['branch_key']}"] = (source_key, branch)
    return result


def validate_branched_mermaid(text: str, context: str, errors: list[str]) -> str | None:
    match = MERMAID_BLOCK.search(text)
    if not match:
        errors.append(f"{context}: missing Mermaid map")
        return None
    edges = EDGE.findall(match.group(1))
    if len(edges) < 2:
        errors.append(f"{context}: map needs at least two edges")
        return match.group(1)
    out_degree: dict[str, int] = defaultdict(int)
    in_degree: dict[str, int] = defaultdict(int)
    for source, target in edges:
        out_degree[source] += 1
        in_degree[target] += 1
    if max((*out_degree.values(), *in_degree.values()), default=0) < 2:
        errors.append(f"{context}: problem map is linear; needs a real branch or merge")
    return match.group(1)


def validate_project_contracts(
    root: Path, state: dict[str, Any], cards: dict[str, dict[str, Any]], errors: list[str],
) -> dict[str, Path]:
    projects = state.get("projects", {})
    sources = state.get("sources", {})
    branches = branch_lookup(cards)
    paths: dict[str, Path] = {}
    used_paths: set[str] = set()
    for project_key, project in projects.items():
        context = f"state project {project_key}"
        if not isinstance(project, dict):
            errors.append(f"{context}: must be an object")
            continue
        for field in ("name", "archive_relative_path", "status", "summary"):
            if not isinstance(project.get(field), str) or not project[field].strip():
                errors.append(f"{context}: needs non-empty {field}")
        if project.get("status") not in ALLOWED_STATUS:
            errors.append(f"{context}: invalid status {project.get('status')!r}")
        if not isinstance(project.get("assignment_basis"), list) or not project["assignment_basis"]:
            errors.append(f"{context}: assignment_basis must be a non-empty array")
        if not isinstance(project.get("cleanup_candidate_count"), int) or project.get("cleanup_candidate_count", -1) < 0:
            errors.append(f"{context}: cleanup_candidate_count must be a non-negative integer")
        if project.get("cleanup_confirmation") not in ALLOWED_CLEANUP_CONFIRMATION:
            errors.append(f"{context}: invalid cleanup_confirmation {project.get('cleanup_confirmation')!r}")
        if project.get("cleanup_candidate_count") == 0 and project.get("cleanup_confirmation") != "not-required":
            errors.append(f"{context}: zero cleanup candidates require cleanup_confirmation 'not-required'")
        if isinstance(project.get("cleanup_candidate_count"), int) and project.get("cleanup_candidate_count", 0) > 0 and project.get("cleanup_confirmation") == "not-required":
            errors.append(f"{context}: cleanup candidates require user confirmation state")
        relative = project.get("archive_relative_path")
        if isinstance(relative, str):
            rel_path = Path(relative)
            if rel_path.is_absolute() or ".." in rel_path.parts or len(rel_path.parts) != 1 or rel_path.name.startswith("."):
                errors.append(f"{context}: archive_relative_path must name one visible folder under the archive root")
            elif relative in used_paths:
                errors.append(f"{context}: duplicate archive_relative_path {relative!r}")
            else:
                used_paths.add(relative)
                paths[project_key] = root / relative
        basis = project.get("retrospective_basis")
        if not isinstance(basis, dict):
            errors.append(f"{context}: retrospective_basis must be an object")
            continue
        refs = basis.get("branch_refs")
        if not isinstance(refs, list) or len(set(refs)) < 2 or not all(isinstance(ref, str) for ref in refs):
            errors.append(f"{context}: promotion needs at least two unique branch_refs")
            refs = []
        promotion_signatures: set[tuple[str, str, str]] = set()
        for ref in refs:
            if ref not in branches:
                errors.append(f"{context}: unresolved promotion branch_ref {ref!r}")
            else:
                source_key, _ = branches[ref]
                if sources.get(source_key, {}).get("project_key") != project_key:
                    errors.append(f"{context}: branch_ref {ref!r} belongs to another disposition/project")
                branch = branches[ref][1]
                promotion_signatures.add((branch.get("problem", ""), branch.get("answer_direction", ""), branch.get("outcome", "")))
        if refs and len(promotion_signatures) < 2:
            errors.append(f"{context}: promotion branch_refs do not describe two distinct problem/outcome branches")
        signals = basis.get("continuity_signals")
        if not isinstance(signals, list) or not signals:
            errors.append(f"{context}: promotion needs continuity_signals")
            signals = []
        for signal in signals:
            if not isinstance(signal, dict) or signal.get("type") not in ALLOWED_CONTINUITY or not isinstance(signal.get("evidence"), str) or not signal["evidence"].strip():
                errors.append(f"{context}: invalid continuity signal {signal!r}")
            elif signal["type"] == "multiple-root-sources":
                cited_sources = {branch_ref_parts(ref)[0] for ref in refs if branch_ref_parts(ref)}
                if len(cited_sources) < 2:
                    errors.append(f"{context}: multiple-root-sources needs branch_refs from at least two sources")
        if not any(isinstance(source, dict) and source.get("project_key") == project_key for source in sources.values()):
            errors.append(f"{context}: has no assigned sources")
    active_names = {path.name for path in paths.values()}
    actual_names = {
        path.name for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name not in SPECIAL_ROOT_DIRS
    }
    for name in sorted(actual_names - active_names):
        errors.append(f"unexpected active project folder {name!r}; retire generated notes before publication")
    for name in sorted(active_names - actual_names):
        errors.append(f"missing active project folder {name!r}")
    return paths


def validate_topic(
    root: Path, project_key: str, topic_path: Path, sources: dict[str, dict[str, Any]],
    branches: dict[str, tuple[str, dict[str, Any]]], errors: list[str],
) -> dict[str, Any] | None:
    text = topic_path.read_text(encoding="utf-8")
    relative = str(topic_path.relative_to(root))
    data = frontmatter(text)
    if data is None:
        errors.append(f"{relative}: missing valid YAML frontmatter")
        return None
    for key in REQUIRED_TOPIC_KEYS:
        if key not in data:
            errors.append(f"{relative}: missing frontmatter key {key}")
    status = data.get("status")
    if status not in ALLOWED_STATUS:
        errors.append(f"{relative}: invalid status {status!r}")
    topic_key = data.get("topic_key", "")
    topic_name = data.get("topic", "")
    if not topic_key or not topic_name:
        errors.append(f"{relative}: topic_key and topic must be non-empty")
    source_ids = json_field(data, "source_task_ids", list, errors, relative)
    primary_ids = json_field(data, "primary_source_task_ids", list, errors, relative)
    related_ids = json_field(data, "related_source_task_ids", list, errors, relative)
    refs = json_field(data, "problem_branch_refs", list, errors, relative)
    node_map = json_field(data, "branch_node_map", dict, errors, relative)
    for label, values in (("source_task_ids", source_ids), ("primary_source_task_ids", primary_ids), ("related_source_task_ids", related_ids), ("problem_branch_refs", refs)):
        if not all(isinstance(value, str) and value for value in values) or len(values) != len(set(values)):
            errors.append(f"{relative}: {label} must contain unique non-empty strings")
    if set(primary_ids) & set(related_ids) or set(source_ids) != set(primary_ids) | set(related_ids):
        errors.append(f"{relative}: source_task_ids must equal disjoint primary and related source IDs")
    for source_key in source_ids:
        source = sources.get(source_key)
        if not isinstance(source, dict) or source.get("project_key") != project_key:
            errors.append(f"{relative}: source {source_key!r} is not assigned to this project")
    for source_key in primary_ids:
        if sources.get(source_key, {}).get("primary_topic") != topic_key:
            errors.append(f"{relative}: source {source_key!r} primary_topic does not equal {topic_key!r}")
    expected_counts = {
        "task_count": sum_counts(sources, primary_ids, "task_count"),
        "question_count": sum_counts(sources, primary_ids, "question_count"),
        "answer_count": sum_counts(sources, primary_ids, "answer_count"),
    }
    for field, expected in expected_counts.items():
        actual = int_field(data, field, errors, relative)
        if expected is None:
            errors.append(f"{relative}: {field} cannot be numeric while a primary source count is unknown")
        elif actual is not None and actual != expected:
            errors.append(f"{relative}: {field} {actual} does not equal primary-source total {expected}")
    semantic_expected = 0
    for ref in refs:
        resolved = branches.get(ref)
        if resolved is None:
            errors.append(f"{relative}: unresolved problem_branch_ref {ref!r}")
            continue
        source_key, branch = resolved
        if source_key not in source_ids:
            errors.append(f"{relative}: branch_ref {ref!r} source is absent from source_task_ids")
        refinements = branch.get("refinements", [])
        semantic_expected += 1 + (len(refinements) if isinstance(refinements, list) else 0)
    semantic_actual = int_field(data, "semantic_question_count", errors, relative)
    if semantic_actual is not None and semantic_actual != semantic_expected:
        errors.append(
            f"{relative}: semantic_question_count {semantic_actual} does not equal cited branch total {semantic_expected}"
        )
    map_type = data.get("map_type")
    if map_type not in ALLOWED_MAP_TYPES:
        errors.append(f"{relative}: invalid map_type {map_type!r}")
    if map_type == "none":
        if len(refs) != 1 or node_map:
            errors.append(f"{relative}: map_type none requires exactly one branch ref and an empty branch_node_map")
        if MERMAID_BLOCK.search(text):
            errors.append(f"{relative}: one-branch topic must not manufacture a Mermaid problem map")
    elif map_type in {"tree", "network"}:
        if len(refs) < 2:
            errors.append(f"{relative}: mapped topic needs at least two branch refs")
        if set(node_map) != set(refs):
            errors.append(f"{relative}: branch_node_map keys must exactly match problem_branch_refs")
        node_ids = list(node_map.values())
        if not all(isinstance(value, str) and NODE_ID.fullmatch(value) for value in node_ids) or len(node_ids) != len(set(node_ids)):
            errors.append(f"{relative}: branch_node_map values must be unique Mermaid node IDs")
        graph = validate_branched_mermaid(text, relative, errors)
        if graph is not None:
            for node_id in node_ids:
                if not re.search(rf"\b{re.escape(node_id)}\b", graph):
                    errors.append(f"{relative}: mapped Mermaid node {node_id!r} is absent from graph")
    return {
        "topic_key": topic_key, "topic": topic_name, "status": status, "primary_ids": primary_ids,
        "source_ids": source_ids, "refs": refs, "task_count": expected_counts["task_count"],
        "question_count": expected_counts["question_count"], "answer_count": expected_counts["answer_count"],
        "semantic_question_count": semantic_expected,
    }


def validate_project_files(
    root: Path, state: dict[str, Any], cards: dict[str, dict[str, Any]],
    project_paths: dict[str, Path], errors: list[str],
) -> dict[str, list[dict[str, Any]]]:
    sources = state.get("sources", {})
    branches = branch_lookup(cards)
    result: dict[str, list[dict[str, Any]]] = {}
    global_primary: set[str] = set()
    for project_key, project_path in project_paths.items():
        for name in REQUIRED_PROJECT_FILES:
            if not (project_path / name).is_file():
                errors.append(f"{project_path.name}: missing {name}")
        asset_index = project_path / "assets" / "00-资产总索引.md"
        if not asset_index.is_file():
            errors.append(f"{project_path.name}: missing assets/00-资产总索引.md")
        boundary_path = project_path / "01-主题边界图.md"
        boundary_graph: str | None = None
        boundary_data: dict[str, str] | None = None
        if boundary_path.is_file():
            boundary_text = boundary_path.read_text(encoding="utf-8")
            boundary_data = frontmatter(boundary_text)
            if boundary_data is None:
                errors.append(f"{boundary_path.relative_to(root)}: missing topic_node_map frontmatter")
            boundary_graph = validate_branched_mermaid(
                boundary_text, str(boundary_path.relative_to(root)), errors
            )
        topic_dir = project_path / "topics"
        paths = sorted(topic_dir.glob("*.md")) if topic_dir.is_dir() else []
        if not paths:
            errors.append(f"{project_path.name}: needs at least one topics/*.md")
        topics: list[dict[str, Any]] = []
        topic_keys: set[str] = set()
        topic_names: set[str] = set()
        project_primary: set[str] = set()
        topic_refs: set[str] = set()
        related_by_source: dict[str, set[str]] = defaultdict(set)
        for path in paths:
            topic = validate_topic(root, project_key, path, sources, branches, errors)
            if topic is None:
                continue
            if topic["topic_key"] in topic_keys:
                errors.append(f"{project_path.name}: duplicate topic_key {topic['topic_key']!r}")
            if topic["topic"] in topic_names:
                errors.append(f"{project_path.name}: duplicate topic display name {topic['topic']!r}")
            topic_keys.add(topic["topic_key"])
            topic_names.add(topic["topic"])
            for source_key in topic["primary_ids"]:
                if source_key in project_primary or source_key in global_primary:
                    errors.append(f"{project_path.name}: source {source_key!r} is primary in more than one topic")
                project_primary.add(source_key)
                global_primary.add(source_key)
            topic_refs.update(topic["refs"])
            for source_key in set(topic["source_ids"]) - set(topic["primary_ids"]):
                related_by_source[source_key].add(topic["topic_key"])
            topics.append(topic)
        assigned = {
            key for key, source in sources.items()
            if isinstance(source, dict) and source.get("project_key") == project_key
        }
        if project_primary != assigned:
            errors.append(
                f"{project_path.name}: primary topic assignment mismatch; "
                f"missing={sorted(assigned - project_primary)}, extra={sorted(project_primary - assigned)}"
            )
        for source_key in assigned:
            expected_related = set(sources.get(source_key, {}).get("related_topics", []))
            actual_related = related_by_source.get(source_key, set())
            if actual_related != expected_related:
                errors.append(
                    f"{project_path.name}: related topic assignment differs for {source_key!r}; "
                    f"state={sorted(expected_related)}, notes={sorted(actual_related)}"
                )
        required_refs = set(state["projects"][project_key].get("retrospective_basis", {}).get("branch_refs", []))
        if not required_refs.issubset(topic_refs):
            errors.append(f"{project_path.name}: topic notes omit promotion branch refs {sorted(required_refs - topic_refs)}")
        overview = project_path / "00-项目对话总览.md"
        if overview.is_file():
            rows = find_table(overview, ["主题", "task", "问题", "回答", "语义节点", "状态"], errors)
            row_map = {visible_cell(row[0]): row for row in rows if len(row) == 6}
            if set(row_map) != topic_names:
                errors.append(f"{project_path.name}: overview topic rows do not match topic notes")
            for topic in topics:
                row = row_map.get(topic["topic"])
                if row and (
                    [parse_count(cell) for cell in row[1:5]] != [
                        topic["task_count"], topic["question_count"], topic["answer_count"], topic["semantic_question_count"],
                    ] or visible_cell(row[5]) != topic["status"]
                ):
                    errors.append(f"{project_path.name}: overview counts/status differ for topic {topic['topic']!r}")
        if boundary_data is not None:
            node_map = json_field(
                boundary_data, "topic_node_map", dict, errors, str(boundary_path.relative_to(root))
            )
            if set(node_map) != topic_keys:
                errors.append(f"{boundary_path.relative_to(root)}: topic_node_map keys must match topic notes")
            node_ids = list(node_map.values())
            if not all(isinstance(value, str) and NODE_ID.fullmatch(value) for value in node_ids) or len(node_ids) != len(set(node_ids)):
                errors.append(f"{boundary_path.relative_to(root)}: topic_node_map values must be unique Mermaid node IDs")
            if boundary_graph is not None:
                for node_id in node_ids:
                    if not re.search(rf"\b{re.escape(node_id)}\b", boundary_graph):
                        errors.append(f"{boundary_path.relative_to(root)}: mapped topic node {node_id!r} is absent from graph")
        if asset_index.is_file():
            rows = find_table(
                asset_index,
                ["Exact path", "Related topics", "Kind", "Role", "Evidence state", "Version/commit"],
                errors,
            )
            row_paths = [visible_cell(row[0]) for row in rows if len(row) == 6]
            expected_paths = {
                value
                for source_key in assigned
                for value in cards.get(source_key, {}).get("asset_paths", [])
                if isinstance(value, str) and value
            }
            if len(row_paths) != len(set(row_paths)) or set(row_paths) != expected_paths:
                errors.append(f"{project_path.name}: asset index paths do not match assigned source cards")
        cleanup = project_path / "03-完成主题清理候选.md"
        if cleanup.is_file():
            rows = find_table(cleanup, ["状态", "候选文件数"], errors)
            project_state = state["projects"][project_key]
            if (
                len(rows) != 1
                or len(rows[0]) != 2
                or visible_cell(rows[0][0]) != project_state.get("cleanup_confirmation")
                or parse_count(rows[0][1]) != project_state.get("cleanup_candidate_count")
            ):
                errors.append(f"{project_path.name}: cleanup summary does not match project state")
            candidate_count = project_state.get("cleanup_candidate_count")
            if isinstance(candidate_count, int) and candidate_count > 0:
                candidates = find_table(
                    cleanup,
                    [
                        "Candidate ID", "Exact path", "Type", "Obsolescence evidence",
                        "Replacement/recovery", "Risk", "Proposed action",
                    ],
                    errors,
                )
                candidate_ids = [visible_cell(row[0]) for row in candidates if len(row) == 7]
                candidate_paths = [visible_cell(row[1]) for row in candidates if len(row) == 7]
                if (
                    len(candidates) != candidate_count
                    or len(candidate_ids) != len(set(candidate_ids))
                    or len(candidate_paths) != len(set(candidate_paths))
                    or any(not value for value in candidate_ids + candidate_paths)
                ):
                    errors.append(f"{project_path.name}: cleanup candidate details do not match candidate count")
        result[project_key] = topics
    return result


def disposition_totals(state: dict[str, Any]) -> dict[str, dict[str, int]]:
    totals = {key: {"sources": 0, "tasks": 0, "questions": 0, "answers": 0} for key in DISPOSITION_LABELS}
    for source in state.get("sources", {}).values():
        if not isinstance(source, dict):
            continue
        if source.get("access_status") not in {"readable", "partial"}:
            disposition = "unreadable-or-unknown"
        elif source.get("project_key") == "pending":
            disposition = "pending"
        elif source.get("project_key") == "lightweight-nonretrospective":
            disposition = "lightweight-nonretrospective"
        elif source.get("project_key") == "excluded-nonproject":
            disposition = "excluded-nonproject"
        else:
            disposition = "archived-projects"
        totals[disposition]["sources"] += 1
        for field, target in (("task_count", "tasks"), ("question_count", "questions"), ("answer_count", "answers")):
            if isinstance(source.get(field), int):
                totals[disposition][target] += source[field]
    return totals


def project_totals(state: dict[str, Any]) -> dict[str, dict[str, int | None]]:
    totals: dict[str, dict[str, int | None]] = {}
    sources = state.get("sources", {})
    for project_key in state.get("projects", {}):
        keys = [key for key, source in sources.items() if isinstance(source, dict) and source.get("project_key") == project_key]
        totals[project_key] = {
            "tasks": sum_counts(sources, keys, "task_count"),
            "questions": sum_counts(sources, keys, "question_count"),
            "answers": sum_counts(sources, keys, "answer_count"),
        }
    return totals


def validate_global_indexes(
    root: Path, state: dict[str, Any], cards: dict[str, dict[str, Any]],
    topics: dict[str, list[dict[str, Any]]], totals: dict[str, dict[str, int | None]],
    dispositions: dict[str, dict[str, int]], errors: list[str],
) -> None:
    index = root / "00-项目索引.md"
    if not index.is_file():
        errors.append("missing 00-项目索引.md")
        return
    project_rows = find_table(index, ["项目", "task", "问题", "回答", "topic", "状态", "总结"], errors)
    rows_by_name = {visible_cell(row[0]): row for row in project_rows if len(row) == 7}
    expected_names = {project.get("name") for project in state.get("projects", {}).values() if isinstance(project, dict)}
    if set(rows_by_name) != expected_names:
        errors.append("00-项目索引.md: project rows do not match state projects")
    for project_key, project in state.get("projects", {}).items():
        if not isinstance(project, dict):
            continue
        row = rows_by_name.get(project.get("name"))
        expected = totals.get(project_key, {})
        if row and (
            [parse_count(cell) for cell in row[1:5]] != [
                expected.get("tasks"), expected.get("questions"), expected.get("answers"), len(topics.get(project_key, []))
            ] or visible_cell(row[5]) != project.get("status") or not visible_cell(row[6])
        ):
            errors.append(f"00-项目索引.md: counts/status differ for project {project.get('name')!r}")
    disposition_rows = find_table(index, ["处置", "来源数", "task", "问题", "回答"], errors)
    disposition_map = {visible_cell(row[0]): row for row in disposition_rows if len(row) == 5}
    if set(disposition_map) != set(DISPOSITION_LABELS.values()):
        errors.append("00-项目索引.md: disposition rows do not match the four dispositions plus unreadable")
    for key, label in DISPOSITION_LABELS.items():
        row = disposition_map.get(label)
        expected = dispositions[key]
        if row and [parse_count(cell) for cell in row[1:]] != [
            expected["sources"], expected["tasks"], expected["questions"], expected["answers"]
        ]:
            errors.append(f"00-项目索引.md: disposition totals differ for {label!r}")
    lightweight = {
        key: source for key, source in state.get("sources", {}).items()
        if isinstance(source, dict) and source.get("project_key") == "lightweight-nonretrospective"
        and source.get("access_status") in {"readable", "partial"}
    }
    light_index = root / "轻量成果" / "00-轻量成果索引.md"
    if lightweight:
        if not light_index.is_file():
            errors.append("lightweight sources require 轻量成果/00-轻量成果索引.md")
        else:
            rows = find_table(light_index, ["成果", "来源", "task", "问题", "回答", "结果摘要", "资产"], errors)
            row_map = {visible_cell(row[1]): row for row in rows if len(row) == 7}
            if set(row_map) != set(lightweight):
                errors.append("轻量成果索引: source rows do not match lightweight state")
            for source_key, source in lightweight.items():
                row = row_map.get(source_key)
                card = cards.get(source_key, {})
                if row and (
                    [parse_count(cell) for cell in row[2:5]] != [source.get("task_count"), source.get("question_count"), source.get("answer_count")]
                    or visible_cell(row[0]) != card.get("title") or not visible_cell(row[5]) or not visible_cell(row[6])
                ):
                    errors.append(f"轻量成果索引: row differs for {source_key!r}")


def validate_required_shared_structure(root: Path, state: dict[str, Any], errors: list[str]) -> None:
    pending = {
        key: source for key, source in state.get("sources", {}).items()
        if isinstance(source, dict) and source.get("project_key") == "pending"
        and source.get("access_status") in {"readable", "partial"}
    }
    if pending:
        folder = root / "待确认归属"
        for relative in ("00-待确认归属总览.md", "99-来源登记与更新日志.md"):
            if not (folder / relative).is_file():
                errors.append(f"pending sources require 待确认归属/{relative}")
        if not (folder / "topics").is_dir():
            errors.append("pending sources require 待确认归属/topics/")
        overview = folder / "00-待确认归属总览.md"
        if overview.is_file():
            rows = find_table(overview, ["线索", "来源", "task", "问题", "回答", "待确认原因"], errors)
            row_map = {visible_cell(row[1]): row for row in rows if len(row) == 6}
            if set(row_map) != set(pending):
                errors.append("待确认归属总览: source rows do not match pending state")
            for source_key, source in pending.items():
                row = row_map.get(source_key)
                if row and (
                    [parse_count(cell) for cell in row[2:5]]
                    != [source.get("task_count"), source.get("question_count"), source.get("answer_count")]
                    or visible_cell(row[5]) != source.get("pending_reason")
                    or not visible_cell(row[0])
                ):
                    errors.append(f"待确认归属总览: row differs for {source_key!r}")


def resolve_wikilink(root: Path, source: Path, raw: str, stems: dict[str, list[Path]]) -> bool:
    normalized = raw.replace("\\|", "|").split("|", 1)[0].split("#", 1)[0].strip()
    if not normalized or "://" in normalized:
        return True
    target = Path(normalized)
    if target.suffix != ".md":
        target = target.with_suffix(".md")
    if normalized.startswith(("./", "../")):
        candidates = [(source.parent / target).resolve()]
    elif "/" in normalized:
        candidates = [(root / target).resolve(), (source.parent / target).resolve()]
    else:
        candidates = stems.get(target.stem, [])
    return any(candidate.is_file() for candidate in candidates)


def validate_links(root: Path, errors: list[str]) -> None:
    markdown = active_markdown(root)
    stems: dict[str, list[Path]] = defaultdict(list)
    for path in markdown:
        stems[path.stem].append(path.resolve())
    for path in markdown:
        for match in WIKILINK.finditer(path.read_text(encoding="utf-8")):
            if not resolve_wikilink(root, path, match.group(1), stems):
                errors.append(f"{path.relative_to(root)}: broken wikilink [[{match.group(1)}]]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_root", help="Path to the 项目复盘 directory")
    args = parser.parse_args()
    root = Path(args.archive_root).expanduser().resolve()
    if not root.is_dir():
        print(json.dumps({"ok": False, "errors": [f"not a directory: {root}"]}, ensure_ascii=False, indent=2))
        return 2
    errors: list[str] = []
    warnings: list[str] = []
    state, cards = load_state(root, errors, warnings)
    paths = validate_project_contracts(root, state, cards, errors)
    topics = validate_project_files(root, state, cards, paths, errors)
    totals = project_totals(state)
    dispositions = disposition_totals(state)
    validate_global_indexes(root, state, cards, topics, totals, dispositions, errors)
    validate_required_shared_structure(root, state, errors)
    validate_markdown_tables(root, errors)
    validate_links(root, errors)
    result = {
        "ok": not errors,
        "project_count": len(state.get("projects", {})) if isinstance(state.get("projects"), dict) else 0,
        "source_count": len(state.get("sources", {})) if isinstance(state.get("sources"), dict) else 0,
        "computed_project_totals": totals,
        "computed_disposition_totals": dispositions,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
