#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[1] / "scripts" / "validate_archive.py"


def source_card(source_key: str, branches: list[tuple[str, list[str]]] | None = None, title: str = "Source") -> dict:
    branches = branches or [("inputs", []), ("delivery", [])]
    return {
        "schema_version": 1,
        "source_key": source_key,
        "title": title,
        "project_candidates": ["Demo"],
        "goal": "Build a useful result",
        "problem_branches": [
            {
                "branch_key": key,
                "problem": f"Resolve {key}",
                "refinements": refinements,
                "answer_direction": f"Answer {key}",
                "outcome": f"Outcome {key}",
            }
            for key, refinements in branches
        ],
        "decisions": [],
        "implementation_evidence": [],
        "verification_evidence": [],
        "release_evidence": [],
        "production_evidence": [],
        "open_items": [],
        "asset_paths": [],
        "task_count": 1,
        "question_count": 2,
        "answer_count": 2,
        "answer_count_method": "provider-normalized",
        "semantic_question_count": sum(1 + len(refinements) for _, refinements in branches),
        "excluded_counts": {},
        "last_processed_turn_id": None,
    }


class ArchiveValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "项目复盘"
        self.project = self.root / "Demo"
        self.topic_dir = self.project / "topics"
        self.card_dir = self.root / ".project-conversation-archive" / "source-cards"
        (self.project / "assets").mkdir(parents=True)
        self.topic_dir.mkdir()
        self.card_dir.mkdir(parents=True)
        self.card = source_card("codex:one")
        self.write_card("codex-one.json", self.card)
        self.state = {
            "schema_version": 2,
            "updated_at": "2026-09-09T00:00:00Z",
            "providers": {
                "codex": {
                    "coverage": "available",
                    "access_method": "app-tool",
                    "checked_at": "2026-09-09T00:00:00Z",
                    "discovered_root_count": 1,
                    "readable_root_count": 1,
                }
            },
            "projects": {
                "demo": {
                    "name": "Demo",
                    "archive_relative_path": "Demo",
                    "status": "in-progress",
                    "summary": "Working result",
                    "cleanup_candidate_count": 0,
                    "cleanup_confirmation": "not-required",
                    "assignment_basis": ["explicit project name"],
                    "retrospective_basis": {
                        "branch_refs": ["codex:one#inputs", "codex:one#delivery"],
                        "continuity_signals": [
                            {"type": "active-implementation", "evidence": "Implementation discussed"}
                        ],
                    },
                }
            },
            "sources": {
                "codex:one": self.state_source("one", "demo", "topic", "codex-one.json", 2),
            },
        }
        self.write_project_shell()
        self.write_topic(
            "Topic.md", topic_key="topic", topic_name="Topic", primary=["codex:one"], related=[],
            refs=["codex:one#inputs", "codex:one#delivery"], counts=(1, 2, 2, 2), map_type="tree",
        )
        self.write_overview([("Topic", 1, 2, 2, 2, "in-progress")])
        self.write_global_index()
        self.write_state()

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def state_source(source_id: str, project_key: str, primary_topic: str | None, card_name: str, semantic: int) -> dict:
        return {
            "provider": "codex", "source_id": source_id, "title": "Source", "task_count": 1,
            "question_count": 2, "answer_count": 2, "answer_count_method": "provider-normalized",
            "semantic_question_count": semantic, "excluded_counts": {}, "project_key": project_key,
            "primary_topic": primary_topic, "related_topics": [],
            "card_path": f".project-conversation-archive/source-cards/{card_name}",
            "access_status": "readable", "pending_reason": None, "exclusion_reason": None,
            "lightweight_reason": None, "triage_confidence": None,
        }

    def write_card(self, name: str, payload: dict) -> None:
        (self.card_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    def write_project_shell(self) -> None:
        self.write_boundary({"topic": "T1"}, "  P[Project] --> T1[Topic]\n  T1 --> B1[Inputs]\n  T1 --> B2[Delivery]")
        for name in ("02-未完成主题与资产.md", "99-来源登记与更新日志.md"):
            (self.project / name).write_text(f"# {name}\n", encoding="utf-8")
        (self.project / "03-完成主题清理候选.md").write_text(
            "# Cleanup\n\n| 状态 | 候选文件数 |\n| --- | --- |\n| not-required | 0 |\n",
            encoding="utf-8",
        )
        (self.project / "assets" / "00-资产总索引.md").write_text(
            "# Assets\n\n| Exact path | Related topics | Kind | Role | Evidence state | Version/commit |\n"
            "| --- | --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )

    def write_boundary(self, node_map: dict[str, str], edges: str) -> None:
        (self.project / "01-主题边界图.md").write_text(
            f"---\ntopic_node_map: {json.dumps(node_map)}\n---\n\n# Boundary\n\n"
            f"```mermaid\nflowchart TD\n{edges}\n```\n",
            encoding="utf-8",
        )

    def write_topic(
        self, filename: str, *, topic_key: str, topic_name: str, primary: list[str], related: list[str],
        refs: list[str], counts: tuple[int, int, int, int], map_type: str,
    ) -> None:
        source_ids = primary + related
        node_map = {ref: f"B{index}" for index, ref in enumerate(refs, 1)} if map_type != "none" else {}
        graph = ""
        if map_type != "none":
            edges = "\n".join(f"  P[Objective] --> B{index}[Branch {index}]" for index in range(1, len(refs) + 1))
            graph = f"\n```mermaid\nflowchart TD\n{edges}\n```\n"
        task_count, question_count, answer_count, semantic_count = counts
        text = f'''---
topic_key: {topic_key}
topic: {topic_name}
status: in-progress
source_task_ids: {json.dumps(source_ids)}
primary_source_task_ids: {json.dumps(primary)}
related_source_task_ids: {json.dumps(related)}
problem_branch_refs: {json.dumps(refs)}
task_count: {task_count}
question_count: {question_count}
answer_count: {answer_count}
semantic_question_count: {semantic_count}
map_type: {map_type}
branch_node_map: {json.dumps(node_map)}
first_reviewed: 2026-09-09
last_reviewed: 2026-09-09
---

# {topic_name}
{graph}
'''
        (self.topic_dir / filename).write_text(text, encoding="utf-8")

    def write_overview(self, rows: list[tuple[str, int, int, int, int, str]]) -> None:
        text = "# Overview\n\n| 主题 | task | 问题 | 回答 | 语义节点 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n"
        for topic, tasks, questions, answers, semantic, status in rows:
            text += f"| [[topics/{topic}\\|{topic}]] | {tasks} | {questions} | {answers} | {semantic} | {status} |\n"
        (self.project / "00-项目对话总览.md").write_text(text, encoding="utf-8")

    def write_global_index(self, lightweight: tuple[str, int, int, int] | None = None) -> None:
        light_sources = 1 if lightweight else 0
        light_tasks, light_questions, light_answers = lightweight[1:] if lightweight else (0, 0, 0)
        text = '''# Index

| 项目 | task | 问题 | 回答 | topic | 状态 | 总结 |
| --- | --- | --- | --- | --- | --- | --- |
| [[Demo/00-项目对话总览\\|Demo]] | 1 | 2 | 2 | TOPIC_COUNT | in-progress | Working result |

| 处置 | 来源数 | task | 问题 | 回答 |
| --- | --- | --- | --- | --- |
| 已归档项目 | 1 | 1 | 2 | 2 |
| 待确认归属 | 0 | 0 | 0 | 0 |
| 轻量成果 | LIGHT_SOURCES | LIGHT_TASKS | LIGHT_QUESTIONS | LIGHT_ANSWERS |
| 已跳过的一次性非项目问答 | 0 | 0 | 0 | 0 |
| 不可读取/未知 | 0 | 0 | 0 | 0 |
'''
        text = text.replace("TOPIC_COUNT", str(len(list(self.topic_dir.glob("*.md")))))
        text = text.replace("LIGHT_SOURCES", str(light_sources)).replace("LIGHT_TASKS", str(light_tasks))
        text = text.replace("LIGHT_QUESTIONS", str(light_questions)).replace("LIGHT_ANSWERS", str(light_answers))
        (self.root / "00-项目索引.md").write_text(text, encoding="utf-8")

    def write_state(self) -> None:
        (self.root / ".project-conversation-archive" / "source-index.json").write_text(json.dumps(self.state), encoding="utf-8")

    def validate(self) -> tuple[int, dict]:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR), str(self.root)], check=False, capture_output=True, text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def test_valid_archive_passes(self) -> None:
        code, payload = self.validate()
        self.assertEqual(code, 0, payload)

    def test_unescaped_wikilink_alias_in_table_fails(self) -> None:
        path = self.project / "00-项目对话总览.md"
        path.write_text(path.read_text().replace("\\|", "|"), encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("unescaped wikilink alias pipe" in value for value in payload["errors"]))

    def test_linear_problem_map_fails(self) -> None:
        path = self.topic_dir / "Topic.md"
        path.write_text(path.read_text().replace("P[Objective] --> B2", "B1[Branch 1] --> B2"), encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("problem map is linear" in value for value in payload["errors"]))

    def test_markdown_source_card_fails(self) -> None:
        self.state["sources"]["codex:one"]["card_path"] = ".project-conversation-archive/source-cards/one.md"
        (self.card_dir / "one.md").write_text("# summary\n", encoding="utf-8")
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("source card must be JSON" in value for value in payload["errors"]))

    def test_full_project_needs_two_real_branches(self) -> None:
        self.state["projects"]["demo"]["retrospective_basis"]["branch_refs"] = ["codex:one#inputs"]
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("promotion needs at least two" in value for value in payload["errors"]))

    def test_fake_branch_reference_fails(self) -> None:
        path = self.topic_dir / "Topic.md"
        path.write_text(path.read_text().replace("codex:one#delivery", "codex:one#invented"), encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("unresolved problem_branch_ref" in value for value in payload["errors"]))

    def test_two_singleton_topics_do_not_require_fake_topic_maps(self) -> None:
        (self.topic_dir / "Topic.md").unlink()
        self.write_topic(
            "Inputs.md", topic_key="topic", topic_name="Inputs", primary=["codex:one"], related=[],
            refs=["codex:one#inputs"], counts=(1, 2, 2, 1), map_type="none",
        )
        self.write_topic(
            "Delivery.md", topic_key="delivery", topic_name="Delivery", primary=[], related=["codex:one"],
            refs=["codex:one#delivery"], counts=(0, 0, 0, 1), map_type="none",
        )
        self.state["sources"]["codex:one"]["related_topics"] = ["delivery"]
        self.write_state()
        self.write_boundary({"topic": "T1", "delivery": "T2"}, "  P[Project] --> T1[Inputs]\n  P --> T2[Delivery]")
        self.write_overview([("Inputs", 1, 2, 2, 1, "in-progress"), ("Delivery", 0, 0, 0, 1, "in-progress")])
        self.write_global_index()
        code, payload = self.validate()
        self.assertEqual(code, 0, payload)

    def test_unregistered_project_folder_must_be_retired(self) -> None:
        (self.root / "Old Generated Project").mkdir()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("unexpected active project folder" in value for value in payload["errors"]))

    def test_visible_project_count_mismatch_fails(self) -> None:
        path = self.root / "00-项目索引.md"
        path.write_text(path.read_text().replace("| 1 | 2 | 2 | 1 | in-progress", "| 9 | 2 | 2 | 1 | in-progress"), encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("counts/status differ for project" in value for value in payload["errors"]))

    def test_project_boundary_map_must_reference_real_topics(self) -> None:
        path = self.project / "01-主题边界图.md"
        path.write_text(path.read_text().replace('"topic": "T1"', '"invented": "T1"'), encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("topic_node_map keys must match" in value for value in payload["errors"]))

    def test_related_topic_membership_must_match_state(self) -> None:
        self.state["sources"]["codex:one"]["related_topics"] = ["invented"]
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("related topic assignment differs" in value for value in payload["errors"]))

    def test_asset_index_must_match_card_paths(self) -> None:
        self.card["asset_paths"] = ["docs/result.md"]
        self.write_card("codex-one.json", self.card)
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("asset index paths do not match" in value for value in payload["errors"]))

    def test_cleanup_summary_must_match_state(self) -> None:
        self.state["projects"]["demo"]["cleanup_candidate_count"] = 1
        self.state["projects"]["demo"]["cleanup_confirmation"] = "awaiting-user"
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("cleanup summary does not match" in value for value in payload["errors"]))

    def test_nonzero_cleanup_count_requires_exact_candidate_rows(self) -> None:
        self.state["projects"]["demo"]["cleanup_candidate_count"] = 1
        self.state["projects"]["demo"]["cleanup_confirmation"] = "awaiting-user"
        self.write_state()
        cleanup = self.project / "03-完成主题清理候选.md"
        cleanup.write_text(
            "# Cleanup\n\n| 状态 | 候选文件数 |\n| --- | --- |\n| awaiting-user | 1 |\n",
            encoding="utf-8",
        )
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("cleanup candidate details" in value for value in payload["errors"]))

    def test_retired_generated_notes_do_not_block_active_validation(self) -> None:
        retired = self.root / ".project-conversation-archive" / "retired-project-notes" / "2026-09-09" / "Old"
        retired.mkdir(parents=True)
        (retired / "broken.md").write_text("| A | B |\n| --- |\n[[missing-link]]\n", encoding="utf-8")
        code, payload = self.validate()
        self.assertEqual(code, 0, payload)

    def test_provider_totals_must_reconcile_to_sources(self) -> None:
        self.state["providers"]["codex"]["discovered_root_count"] = 2
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("discovered_root_count" in value for value in payload["errors"]))

    def test_pending_queue_has_auditable_rows(self) -> None:
        pending_card = source_card("codex:pending", [("clue", [])])
        self.write_card("codex-pending.json", pending_card)
        pending = self.state_source("pending", "pending", "pending", "codex-pending.json", 1)
        pending["pending_reason"] = "Project identity is ambiguous"
        self.state["sources"]["codex:pending"] = pending
        self.state["providers"]["codex"]["discovered_root_count"] = 2
        self.state["providers"]["codex"]["readable_root_count"] = 2
        self.write_state()
        index = self.root / "00-项目索引.md"
        index.write_text(
            index.read_text().replace("| 待确认归属 | 0 | 0 | 0 | 0 |", "| 待确认归属 | 1 | 1 | 2 | 2 |"),
            encoding="utf-8",
        )
        pending_dir = self.root / "待确认归属"
        (pending_dir / "topics").mkdir(parents=True)
        (pending_dir / "99-来源登记与更新日志.md").write_text("# Log\n", encoding="utf-8")
        (pending_dir / "00-待确认归属总览.md").write_text(
            "# Pending\n\n| 线索 | 来源 | task | 问题 | 回答 | 待确认原因 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| Project clue | codex:pending | 1 | 2 | 2 | Project identity is ambiguous |\n",
            encoding="utf-8",
        )
        code, payload = self.validate()
        self.assertEqual(code, 0, payload)

    def test_lightweight_uses_one_shared_index_without_project_folder(self) -> None:
        light = source_card("codex:light", [("answer", [])], title="Small answer")
        light["question_count"] = 1
        light["answer_count"] = 1
        self.write_card("codex-light.json", light)
        self.state["providers"]["codex"]["discovered_root_count"] = 2
        self.state["providers"]["codex"]["readable_root_count"] = 2
        source = self.state_source("light", "lightweight-nonretrospective", None, "codex-light.json", 1)
        source.update({"question_count": 1, "answer_count": 1, "lightweight_reason": "One branch", "triage_confidence": "high"})
        self.state["sources"]["codex:light"] = source
        self.write_state()
        self.write_global_index(("codex:light", 1, 1, 1))
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("lightweight sources require" in value for value in payload["errors"]))
        light_folder = self.root / "轻量成果"
        light_folder.mkdir()
        (light_folder / "00-轻量成果索引.md").write_text(
            "# Light\n\n| 成果 | 来源 | task | 问题 | 回答 | 结果摘要 | 资产 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| Small answer | codex:light | 1 | 1 | 1 | Concise result | 无 |\n", encoding="utf-8",
        )
        code, payload = self.validate()
        self.assertEqual(code, 0, payload)

    def test_semantic_count_must_equal_branches_and_refinements(self) -> None:
        self.card["semantic_question_count"] = 9
        self.write_card("codex-one.json", self.card)
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("branch/refinement total" in value for value in payload["errors"]))

    def test_incomplete_migration_cannot_publish(self) -> None:
        self.state["migration"] = {"status": "in-progress"}
        self.write_state()
        code, payload = self.validate()
        self.assertEqual(code, 1)
        self.assertTrue(any("incomplete migration" in value for value in payload["errors"]))


if __name__ == "__main__":
    unittest.main()
