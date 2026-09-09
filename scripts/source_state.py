#!/usr/bin/env python3
"""Diff or merge provider inventories with project-conversation archive state."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
RETAINED_ACCESS = {"readable", "partial"}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists() and default is not None:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def inventory_map(payload: Any) -> tuple[dict[str, dict[str, Any]], set[str], dict[str, dict[str, Any]]]:
    covered_providers: set[str] = set()
    provider_metadata: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict):
        if isinstance(payload.get("provider"), str):
            covered_providers.add(payload["provider"])
        declared = payload.get("providers")
        if isinstance(declared, list):
            covered_providers.update(value for value in declared if isinstance(value, str))
        elif isinstance(declared, dict):
            covered_providers.update(value for value in declared if isinstance(value, str))
            provider_metadata.update(
                (key, dict(value)) for key, value in declared.items()
                if isinstance(key, str) and isinstance(value, dict)
            )
    raw = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if isinstance(raw, dict):
        items = []
        for key, value in raw.items():
            if not isinstance(value, dict):
                raise ValueError(f"inventory source {key!r} is not an object")
            item = dict(value)
            item.setdefault("source_key", key)
            items.append(item)
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("inventory must contain a sources object or list")

    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("source_key"), str):
            raise ValueError("every inventory source needs source_key")
        key = item["source_key"]
        if key in result:
            raise ValueError(f"duplicate source_key: {key}")
        result[key] = item
        provider = item.get("provider")
        if isinstance(provider, str):
            covered_providers.add(provider)
        elif ":" in key:
            covered_providers.add(key.split(":", 1)[0])
    return result, covered_providers, provider_metadata


def same_version(old: dict[str, Any], new: dict[str, Any]) -> bool:
    if new.get("fingerprint") is not None and old.get("fingerprint") is not None:
        return new["fingerprint"] == old["fingerprint"]
    if new.get("source_updated_at") is not None and old.get("source_updated_at") is not None:
        return new["source_updated_at"] == old["source_updated_at"]
    return False


def diff_state(
    state: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    covered_providers: set[str],
) -> dict[str, list[str]]:
    known = state.get("sources", {}) if isinstance(state.get("sources", {}), dict) else {}
    result = {"new": [], "changed": [], "unchanged": [], "missing": []}
    for key, item in inventory.items():
        if key not in known:
            result["new"].append(key)
        elif same_version(known[key], item):
            result["unchanged"].append(key)
        else:
            result["changed"].append(key)
    result["missing"] = sorted(
        key
        for key, item in known.items()
        if key not in inventory
        and isinstance(item, dict)
        and item.get("provider", key.split(":", 1)[0]) in covered_providers
    )
    for value in result.values():
        value.sort()
    return result


def base_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "providers": {},
        "projects": {},
        "sources": {},
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_card_path(source_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", source_key).strip("-.") or "source"
    return f".project-conversation-archive/source-cards/{safe}.json"


def valid_migration_card(archive_root: Path, source_key: str, card_path: Any) -> bool:
    if not isinstance(card_path, str) or not card_path.endswith(".json"):
        return False
    try:
        path = (archive_root / card_path).resolve()
        path.relative_to(archive_root)
        card = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(card, dict) or card.get("source_key") != source_key:
        return False
    branches = card.get("problem_branches")
    return isinstance(branches, list) and bool(branches) and all(
        isinstance(branch, dict) and isinstance(branch.get("branch_key"), str) and branch["branch_key"].strip()
        for branch in branches
    )


def migration_pending(state: dict[str, Any], archive_root: Path) -> list[str]:
    sources = state.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("state sources must be an object")
    pending: list[str] = []
    for key, source in sources.items():
        if not isinstance(source, dict):
            continue
        if source.get("access_status") not in RETAINED_ACCESS:
            continue
        if source.get("project_key") == "excluded-nonproject":
            continue
        if not valid_migration_card(archive_root, key, source.get("card_path")):
            pending.append(key)
    return sorted(pending)


def stage_migration(state: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    schema = state.get("schema_version")
    migration = state.get("migration")
    if schema not in {1, SCHEMA_VERSION}:
        raise ValueError(f"unsupported state schema {schema!r}")
    if schema == SCHEMA_VERSION and not (
        isinstance(migration, dict) and migration.get("status") == "in-progress"
    ):
        raise ValueError("migrate accepts schema 1 or an in-progress schema 2 migration")
    staged = json.loads(json.dumps(state))
    staged["schema_version"] = SCHEMA_VERSION
    staged.setdefault("providers", {})
    staged.setdefault("projects", {})
    sources = staged.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("state sources must be an object")
    legacy_paths: dict[str, str] = {}
    if isinstance(migration, dict) and isinstance(migration.get("legacy_card_paths"), dict):
        legacy_paths.update(migration["legacy_card_paths"])
    for key, source in sources.items():
        if not isinstance(source, dict):
            continue
        old_path = source.get("card_path")
        if source.get("access_status") in RETAINED_ACCESS and source.get("project_key") != "excluded-nonproject":
            if not valid_migration_card(archive_root, key, old_path):
                if isinstance(old_path, str) and old_path:
                    legacy_paths.setdefault(key, old_path)
                source["card_path"] = safe_card_path(key)
    staged["migration"] = {
        "from_schema": migration.get("from_schema", schema) if isinstance(migration, dict) else schema,
        "status": "in-progress",
        "started_at": migration.get("started_at", utc_now()) if isinstance(migration, dict) else utc_now(),
        "legacy_card_paths": legacy_paths,
        "pending_source_keys": migration_pending(staged, archive_root),
    }
    staged["updated_at"] = utc_now()
    return staged


def migration_status(state: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    migration = state.get("migration")
    if (
        state.get("schema_version") != SCHEMA_VERSION
        or not isinstance(migration, dict)
        or migration.get("status") != "in-progress"
    ):
        raise ValueError("state is not an in-progress schema 2 migration")
    pending = migration_pending(state, archive_root)
    retained = sum(
        1 for source in state.get("sources", {}).values()
        if isinstance(source, dict)
        and source.get("access_status") in RETAINED_ACCESS
        and source.get("project_key") != "excluded-nonproject"
    )
    return {
        "status": "ready" if not pending else "in-progress",
        "retained_source_count": retained,
        "completed_source_count": retained - len(pending),
        "pending_source_keys": pending,
    }


def complete_migration(state: dict[str, Any], archive_root: Path) -> dict[str, Any]:
    status = migration_status(state, archive_root)
    if status["pending_source_keys"]:
        raise ValueError(
            "migration still has pending source cards: " + ", ".join(status["pending_source_keys"])
        )
    completed = json.loads(json.dumps(state))
    migration = completed.pop("migration")
    completed["migration_history"] = {
        "from_schema": migration.get("from_schema"),
        "started_at": migration.get("started_at"),
        "completed_at": utc_now(),
        "legacy_card_paths": migration.get("legacy_card_paths", {}),
        "migrated_source_count": status["retained_source_count"],
    }
    completed["updated_at"] = utc_now()
    return completed


def normalized_candidate(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def read_registered_card(state: dict[str, Any], archive_root: Path, source_key: str) -> dict[str, Any]:
    source = state.get("sources", {}).get(source_key)
    if not isinstance(source, dict):
        raise ValueError(f"unknown changed source {source_key!r}")
    card_path = source.get("card_path")
    if not isinstance(card_path, str):
        raise ValueError(f"source {source_key!r} has no registered card")
    path = (archive_root / card_path).resolve()
    try:
        path.relative_to(archive_root)
    except ValueError as exc:
        raise ValueError(f"source {source_key!r} card escapes archive root") from exc
    card = read_json(path)
    if not isinstance(card, dict) or card.get("source_key") != source_key:
        raise ValueError(f"source {source_key!r} has an invalid registered card")
    return card


def candidate_impact(
    state: dict[str, Any], archive_root: Path, changed_keys: list[str],
) -> dict[str, list[str]]:
    changed = sorted(set(changed_keys))
    candidate_seeds: set[str] = set()
    asset_seeds: set[str] = set()
    for source_key in changed:
        card = read_registered_card(state, archive_root, source_key)
        candidate_seeds.update(
            normalized_candidate(value)
            for value in card.get("project_candidates", [])
            if isinstance(value, str) and normalized_candidate(value)
        )
        asset_seeds.update(
            value for value in card.get("asset_paths", []) if isinstance(value, str) and value
        )
    reconsider: list[str] = []
    for source_key, source in state.get("sources", {}).items():
        if source_key in changed or not isinstance(source, dict):
            continue
        if source.get("project_key") not in {"pending", "lightweight-nonretrospective"}:
            continue
        card = read_registered_card(state, archive_root, source_key)
        candidates = {
            normalized_candidate(value)
            for value in card.get("project_candidates", [])
            if isinstance(value, str) and normalized_candidate(value)
        }
        assets = {value for value in card.get("asset_paths", []) if isinstance(value, str) and value}
        if candidates & candidate_seeds or assets & asset_seeds:
            reconsider.append(source_key)
    return {"changed": changed, "reconsider": sorted(reconsider)}


def merge_state(
    state: dict[str, Any],
    inventory: dict[str, dict[str, Any]],
    covered_providers: set[str],
    provider_metadata: dict[str, dict[str, Any]],
    mark_missing: bool,
) -> dict[str, Any]:
    merged = dict(base_state())
    merged.update(state)
    merged["schema_version"] = SCHEMA_VERSION
    merged["providers"] = dict(state.get("providers", {}))
    merged["projects"] = dict(state.get("projects", {}))
    merged["sources"] = {key: dict(value) for key, value in state.get("sources", {}).items()}

    merged_at = utc_now()
    for provider in covered_providers:
        target_provider = dict(merged["providers"].get(provider, {}))
        incoming_provider = provider_metadata.get(provider, {})
        target_provider.update(incoming_provider)
        target_provider.setdefault("coverage", "available")
        target_provider.setdefault("access_method", "none")
        if "checked_at" not in incoming_provider:
            target_provider["checked_at"] = merged_at
        provider_items = [item for item in inventory.values() if item.get("provider") == provider]
        if "discovered_root_count" not in incoming_provider:
            target_provider["discovered_root_count"] = sum(
                item.get("task_count", 1) for item in provider_items if isinstance(item.get("task_count", 1), int)
            )
        if "readable_root_count" not in incoming_provider:
            target_provider["readable_root_count"] = sum(
                item.get("task_count", 1)
                for item in provider_items
                if item.get("access_status") == "readable" and isinstance(item.get("task_count", 1), int)
            )
        merged["providers"][provider] = target_provider

    metadata_fields = (
        "provider",
        "source_id",
        "title",
        "source_updated_at",
        "fingerprint",
        "last_processed_turn_id",
        "task_count",
        "question_count",
        "answer_count",
        "answer_count_method",
        "semantic_question_count",
        "excluded_counts",
        "access_status",
        "root_missing",
        "branch_file_count",
        "branch_file_paths",
    )
    for key, item in inventory.items():
        target = merged["sources"].setdefault(key, {})
        if ":" in key:
            provider, source_id = key.split(":", 1)
            target.setdefault("provider", provider)
            target.setdefault("source_id", source_id)
        for field in metadata_fields:
            if field in item:
                target[field] = item[field]
        target.setdefault("project_key", "pending")
        target.setdefault("primary_topic", "pending")
        target.setdefault("related_topics", [])
        target.setdefault("card_path", None)
        target.setdefault("pending_reason", None)
        target.setdefault("exclusion_reason", None)
        target.setdefault("lightweight_reason", None)
        target.setdefault("triage_confidence", None)
        target.setdefault("semantic_question_count", None)
        target.setdefault("excluded_counts", {})
        target.setdefault("access_status", "partial")
        target.setdefault("task_count", 1)

    if mark_missing:
        for key, item in merged["sources"].items():
            provider = item.get("provider", key.split(":", 1)[0]) if isinstance(item, dict) else None
            if key not in inventory and provider in covered_providers:
                item["access_status"] = "missing"

    merged["updated_at"] = merged_at
    return merged


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(rendered)
        temp_name = handle.name
    os.replace(temp_name, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    diff_parser = subparsers.add_parser("diff", help="Report new, changed, unchanged, and missing sources")
    diff_parser.add_argument("--state", required=True)
    diff_parser.add_argument("--inventory", required=True)

    merge_parser = subparsers.add_parser("merge", help="Merge inventory metadata while preserving semantic assignments")
    merge_parser.add_argument("--state", required=True)
    merge_parser.add_argument("--inventory", required=True)
    merge_parser.add_argument("--output", required=True)
    merge_parser.add_argument("--mark-missing", action="store_true")

    migrate_parser = subparsers.add_parser("migrate", help="Stage a resumable schema 1 to 2 migration")
    migrate_parser.add_argument("--state", required=True)
    migrate_parser.add_argument("--archive-root", required=True)
    migrate_parser.add_argument("--output", required=True)

    status_parser = subparsers.add_parser("migration-status", help="Report missing or invalid migration cards")
    status_parser.add_argument("--state", required=True)
    status_parser.add_argument("--archive-root", required=True)

    complete_parser = subparsers.add_parser("complete-migration", help="Complete a ready migration")
    complete_parser.add_argument("--state", required=True)
    complete_parser.add_argument("--archive-root", required=True)
    complete_parser.add_argument("--output", required=True)

    impact_parser = subparsers.add_parser(
        "candidate-impact", help="Find unchanged pending/lightweight cards affected by changed cards"
    )
    impact_parser.add_argument("--state", required=True)
    impact_parser.add_argument("--archive-root", required=True)
    impact_parser.add_argument("--changed", nargs="+", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).expanduser().resolve()
    try:
        state = read_json(state_path, base_state())
        if args.command == "migrate":
            archive_root = Path(args.archive_root).expanduser().resolve()
            atomic_write(Path(args.output).expanduser().resolve(), stage_migration(state, archive_root))
            return 0
        if args.command == "migration-status":
            archive_root = Path(args.archive_root).expanduser().resolve()
            print(json.dumps(migration_status(state, archive_root), ensure_ascii=False, indent=2))
            return 0
        if args.command == "complete-migration":
            archive_root = Path(args.archive_root).expanduser().resolve()
            atomic_write(
                Path(args.output).expanduser().resolve(),
                complete_migration(state, archive_root),
            )
            return 0
        if state.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"state schema {state.get('schema_version')!r} requires the documented "
                f"schema {SCHEMA_VERSION} source-card migration before diff/merge"
            )
        if isinstance(state.get("migration"), dict) and state["migration"].get("status") == "in-progress":
            raise ValueError("state has an in-progress migration; use migration-status or complete-migration")
        if args.command == "candidate-impact":
            archive_root = Path(args.archive_root).expanduser().resolve()
            print(json.dumps(candidate_impact(state, archive_root, args.changed), ensure_ascii=False, indent=2))
            return 0
        inventory_path = Path(args.inventory).expanduser().resolve()
        inventory, covered_providers, provider_metadata = inventory_map(read_json(inventory_path))
        if args.command == "diff":
            print(json.dumps(diff_state(state, inventory, covered_providers), ensure_ascii=False, indent=2))
        else:
            output = Path(args.output).expanduser().resolve()
            atomic_write(output, merge_state(state, inventory, covered_providers, provider_metadata, args.mark_missing))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
