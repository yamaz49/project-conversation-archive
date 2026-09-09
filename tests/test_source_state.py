#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "source_state.py"


class SourceStateTests(unittest.TestCase):
    @staticmethod
    def schema_one_state() -> dict:
        return {
            "schema_version": 1,
            "providers": {},
            "projects": {"old": {"name": "Old"}},
            "sources": {
                "codex:one": {
                    "provider": "codex",
                    "source_id": "one",
                    "project_key": "old",
                    "access_status": "readable",
                    "card_path": "legacy/one.md",
                    "task_count": 1,
                    "question_count": 2,
                    "answer_count": 2,
                }
            },
        }

    def test_schema_one_requires_explicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            inventory = root / "inventory.json"
            state.write_text(json.dumps({"schema_version": 1, "sources": {}}), encoding="utf-8")
            inventory.write_text(json.dumps({"sources": {}}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "diff", "--state", str(state), "--inventory", str(inventory)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("requires the documented schema 2 source-card migration", completed.stderr)

    def test_new_state_uses_schema_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "missing-state.json"
            inventory = root / "inventory.json"
            output = root / "output.json"
            inventory.write_text(json.dumps({"provider": "codex", "sources": {}}), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "merge", "--state", str(state),
                    "--inventory", str(inventory), "--output", str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output.read_text())["schema_version"], 2)

    def test_schema_one_migration_is_staged_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "项目复盘"
            archive.mkdir()
            state = root / "state.json"
            staged = root / "staged.json"
            state.write_text(json.dumps(self.schema_one_state()), encoding="utf-8")
            first = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "migrate", "--state", str(state),
                    "--archive-root", str(archive), "--output", str(staged),
                ],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            payload = json.loads(staged.read_text())
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["migration"]["pending_source_keys"], ["codex:one"])
            self.assertEqual(payload["migration"]["legacy_card_paths"], {"codex:one": "legacy/one.md"})
            self.assertTrue(payload["sources"]["codex:one"]["card_path"].endswith("codex-one.json"))
            started_at = payload["migration"]["started_at"]
            second = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "migrate", "--state", str(staged),
                    "--archive-root", str(archive), "--output", str(staged),
                ],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(staged.read_text())["migration"]["started_at"], started_at)

    def test_migration_status_and_completion_require_real_json_card(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "项目复盘"
            card_dir = archive / ".project-conversation-archive" / "source-cards"
            card_dir.mkdir(parents=True)
            old = root / "old.json"
            staged = root / "staged.json"
            completed_state = root / "completed.json"
            old.write_text(json.dumps(self.schema_one_state()), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable, str(SCRIPT), "migrate", "--state", str(old),
                    "--archive-root", str(archive), "--output", str(staged),
                ], check=True,
            )
            blocked = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "complete-migration", "--state", str(staged),
                    "--archive-root", str(archive), "--output", str(completed_state),
                ], check=False, capture_output=True, text=True,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("pending source cards", blocked.stderr)
            (card_dir / "codex-one.json").write_text(
                json.dumps({
                    "source_key": "codex:one",
                    "problem_branches": [{"branch_key": "real-branch"}],
                }),
                encoding="utf-8",
            )
            status = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "migration-status", "--state", str(staged),
                    "--archive-root", str(archive),
                ], check=False, capture_output=True, text=True,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["status"], "ready")
            done = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "complete-migration", "--state", str(staged),
                    "--archive-root", str(archive), "--output", str(completed_state),
                ], check=False, capture_output=True, text=True,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            payload = json.loads(completed_state.read_text())
            self.assertNotIn("migration", payload)
            self.assertEqual(payload["migration_history"]["migrated_source_count"], 1)

    def test_diff_refuses_in_progress_migration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "state.json"
            inventory = root / "inventory.json"
            state.write_text(json.dumps({
                "schema_version": 2,
                "migration": {"status": "in-progress"},
                "sources": {},
            }), encoding="utf-8")
            inventory.write_text(json.dumps({"provider": "codex", "sources": {}}), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "diff", "--state", str(state), "--inventory", str(inventory)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("in-progress migration", completed.stderr)

    def test_candidate_impact_reuses_matching_cards_without_transcript_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "项目复盘"
            cards = archive / ".project-conversation-archive" / "source-cards"
            cards.mkdir(parents=True)
            state_path = root / "state.json"
            state = {
                "schema_version": 2,
                "sources": {
                    "codex:changed": {
                        "project_key": "demo",
                        "card_path": ".project-conversation-archive/source-cards/changed.json",
                    },
                    "codex:light": {
                        "project_key": "lightweight-nonretrospective",
                        "card_path": ".project-conversation-archive/source-cards/light.json",
                    },
                    "codex:unrelated": {
                        "project_key": "pending",
                        "card_path": ".project-conversation-archive/source-cards/unrelated.json",
                    },
                },
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            (cards / "changed.json").write_text(json.dumps({
                "source_key": "codex:changed", "project_candidates": ["Ｄｅｍｏ"], "asset_paths": [],
            }), encoding="utf-8")
            (cards / "light.json").write_text(json.dumps({
                "source_key": "codex:light", "project_candidates": ["demo"], "asset_paths": [],
            }), encoding="utf-8")
            (cards / "unrelated.json").write_text(json.dumps({
                "source_key": "codex:unrelated", "project_candidates": ["Other"], "asset_paths": [],
            }), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "candidate-impact", "--state", str(state_path),
                    "--archive-root", str(archive), "--changed", "codex:changed",
                ], check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["reconsider"], ["codex:light"])


if __name__ == "__main__":
    unittest.main()
