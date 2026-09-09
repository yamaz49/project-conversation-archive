#!/usr/bin/env python3
"""Inventory explicitly supplied Claude Code JSONL histories without copying text.

The output contains stable IDs, fingerprints, canonical request/answer turn counts,
and exclusion diagnostics. Semantic summaries remain the model's responsibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BLOCK_PATTERNS = (
    re.compile(r"<in-app-browser-context\b[\s\S]*?</in-app-browser-context>", re.I),
    re.compile(r"<local-command-caveat\b[\s\S]*?</local-command-caveat>", re.I),
    re.compile(r"<system-reminder\b[\s\S]*?</system-reminder>", re.I),
)
COMMAND_ONLY = re.compile(r"^\s*<(?:command-name|command-message|command-args)\b", re.I)
FINAL_STOP_REASONS = {"end_turn", "stop_sequence"}


def explicit_jsonl_files(paths: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path.suffix == ".jsonl":
            files.add(path)
        elif path.is_dir():
            files.update(candidate.resolve() for candidate in path.rglob("*.jsonl"))
        else:
            raise FileNotFoundError(f"not a JSONL file or directory: {path}")
    return sorted(files, key=lambda value: str(value))


def message_text(record: dict[str, Any]) -> str:
    message = record.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def clean_text(text: str) -> str:
    result = text
    for pattern in BLOCK_PATTERNS:
        result = pattern.sub(" ", result)
    result = re.sub(r"\s+", " ", result).strip()
    if COMMAND_ONLY.match(result):
        return ""
    return result


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def scan_file(path: Path) -> dict[str, Any]:
    session_id = path.stem
    invalid_json_lines = 0
    excluded_user_tool_turns = 0
    excluded_user_empty_turns = 0
    assistant_text_chunks = 0
    questions_with_text: list[bool] = []
    questions_with_final: list[bool] = []
    cwd_counts: Counter[str] = Counter()
    last_message_id: str | None = None
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    saw_root_user = False
    saw_sidechain_user = False
    saw_stop_reason = False

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_json_lines += 1
                continue

            if isinstance(record.get("sessionId"), str):
                session_id = record["sessionId"]
            if isinstance(record.get("cwd"), str) and record["cwd"]:
                cwd_counts[record["cwd"]] += 1
            if isinstance(record.get("uuid"), str):
                last_message_id = record["uuid"]
            timestamp = record.get("timestamp")
            if isinstance(timestamp, str):
                first_timestamp = first_timestamp or timestamp
                last_timestamp = timestamp

            record_type = record.get("type")
            sidechain = bool(record.get("isSidechain"))
            if record_type == "user":
                content = record.get("message", {}).get("content") if isinstance(record.get("message"), dict) else None
                if isinstance(content, list) and content and all(
                    isinstance(block, dict) and block.get("type") == "tool_result" for block in content
                ):
                    excluded_user_tool_turns += 1
                    continue
                text = clean_text(message_text(record))
                if not text:
                    excluded_user_empty_turns += 1
                    continue
                if sidechain:
                    saw_sidechain_user = True
                    continue
                saw_root_user = True
                questions_with_text.append(False)
                questions_with_final.append(False)
                continue

            if record_type == "assistant" and not sidechain and questions_with_text:
                text = clean_text(message_text(record))
                if text:
                    assistant_text_chunks += 1
                    questions_with_text[-1] = True
                    message = record.get("message") if isinstance(record.get("message"), dict) else {}
                    stop_reason = message.get("stop_reason")
                    if stop_reason is not None:
                        saw_stop_reason = True
                    if stop_reason in FINAL_STOP_REASONS:
                        questions_with_final[-1] = True

    stat = path.stat()
    is_sidechain_file = "subagents" in path.parts or (saw_sidechain_user and not saw_root_user)
    question_count = 0 if is_sidechain_file else len(questions_with_text)
    answer_flags = questions_with_final if saw_stop_reason else questions_with_text
    answer_count = 0 if is_sidechain_file else sum(1 for answered in answer_flags if answered)
    primary_cwd = cwd_counts.most_common(1)[0][0] if cwd_counts else None

    return {
        "source_key": f"claude-code:{session_id}",
        "provider": "claude-code",
        "source_id": session_id,
        "file_path": str(path),
        "source_updated_at": last_timestamp,
        "first_timestamp": first_timestamp,
        "fingerprint": fingerprint(path),
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "cwd": primary_cwd,
        "last_processed_turn_id": last_message_id,
        "is_sidechain": is_sidechain_file,
        "task_count": 0 if is_sidechain_file else 1,
        "question_count": question_count,
        "answer_count": answer_count,
        "answer_count_method": "final-stop-reason" if saw_stop_reason else "text-fallback",
        "unanswered_count": max(question_count - answer_count, 0),
        "excluded_counts": {
            "tool_result_user_turns": excluded_user_tool_turns,
            "empty_or_notice_user_turns": excluded_user_empty_turns,
            "invalid_json_lines": invalid_json_lines,
            "assistant_text_chunks_grouped_into_answers": assistant_text_chunks,
        },
        "access_status": "readable",
    }


def combined_fingerprint(items: list[dict[str, Any]]) -> str:
    if len(items) == 1:
        return str(items[0]["fingerprint"])
    digest = hashlib.sha256()
    for item in sorted(items, key=lambda value: str(value["file_path"])):
        digest.update(str(item["file_path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["fingerprint"]).encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def consolidate_scans(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach sidechain files to their root session without inflating turn totals."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item["source_key"], []).append(item)

    result: list[dict[str, Any]] = []
    for source_key, group in sorted(grouped.items()):
        roots = [item for item in group if not item["is_sidechain"]]
        branches = [item for item in group if item["is_sidechain"]]
        base = dict(sorted(roots or group, key=lambda value: str(value["file_path"]))[0])
        root_missing = not roots
        base["fingerprint"] = combined_fingerprint(group)
        base["size_bytes"] = sum(int(item["size_bytes"]) for item in group)
        base["mtime_ns"] = max(int(item["mtime_ns"]) for item in group)
        timestamps = [item["first_timestamp"] for item in group if item.get("first_timestamp")]
        updates = [item["source_updated_at"] for item in group if item.get("source_updated_at")]
        base["first_timestamp"] = min(timestamps) if timestamps else None
        base["source_updated_at"] = max(updates) if updates else None
        base["root_missing"] = root_missing
        base["is_sidechain"] = root_missing
        base["task_count"] = 0 if root_missing else 1
        base["question_count"] = 0 if root_missing else sum(item["question_count"] for item in roots)
        base["answer_count"] = 0 if root_missing else sum(item["answer_count"] for item in roots)
        base["unanswered_count"] = max(base["question_count"] - base["answer_count"], 0)
        base["branch_file_count"] = len(branches)
        base["branch_file_paths"] = sorted(str(item["file_path"]) for item in branches)
        if root_missing:
            base["access_status"] = "partial"
        result.append(base)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Explicit Claude Code JSONL files or known index directories")
    parser.add_argument("--output", help="Optional JSON output path; stdout is used when omitted")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        files = explicit_jsonl_files(args.paths)
        scans = [scan_file(path) for path in files]
        sources = consolidate_scans(scans)
        checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = {
            "schema_version": 1,
            "provider": "claude-code",
            "providers": {
                "claude-code": {
                    "coverage": "available",
                    "access_method": "local-index",
                    "checked_at": checked_at,
                    "adapter_version": 1,
                    "discovered_root_count": sum(item["task_count"] for item in sources),
                    "readable_root_count": sum(
                        item["task_count"] for item in sources if item["access_status"] == "readable"
                    ),
                }
            },
            "sources": sources,
        }
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
