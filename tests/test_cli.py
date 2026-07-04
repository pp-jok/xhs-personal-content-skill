import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.main import main  # noqa: E402
from app.models.core import BenchmarkPost, CreatorProfile, CustomTag  # noqa: E402
from app.repositories import JsonRepository  # noqa: E402


class CliTests(unittest.TestCase):
    def test_import_list_and_show_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "import-json",
                    "creator-profiles",
                    str(PROJECT_ROOT / "data" / "examples" / "creator-profile.json"),
                ]
            )
            listed = self._run_cli(["--data-dir", temp_dir, "list", "creator-profiles"])
            shown = self._run_cli(["--data-dir", temp_dir, "show", "creator-profiles", "creator-main"])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["id"], "creator-main")
            self.assertEqual(len(listed["result"]), 1)
            self.assertEqual(shown["result"]["name"], "主账号")

    def test_import_duplicate_returns_error_without_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            args = [
                "--data-dir",
                temp_dir,
                "import-json",
                "custom-tags",
                str(PROJECT_ROOT / "data" / "examples" / "custom-tag.json"),
            ]

            first = self._run_cli(args)
            second = self._run_cli(args, expected_code=1)

            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])
            self.assertIn("already exists", second["error"])

    def test_run_workflow_command_outputs_created_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)

            output = self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "run-workflow",
                    "--creator-id",
                    "creator-main",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                    "--planned-publish-time",
                    "2026-07-05T20:00:00+08:00",
                    "--topic-count",
                    "1",
                ]
            )

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["draft_id"], "draft-from-benchmark-post-001-1")
            self.assertEqual(output["result"]["publish_task_id"], "publish-task-from-benchmark-post-001-1")
            self.assertTrue((data_dir / "publish-tasks" / "publish-task-from-benchmark-post-001-1.json").exists())

    def _run_cli(self, args: list[str], expected_code: int = 0) -> dict:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(args)
        self.assertEqual(code, expected_code)
        return json.loads(buffer.getvalue())

    def _seed_data(self, data_dir: Path) -> None:
        JsonRepository(data_dir, CreatorProfile).create(
            CreatorProfile(
                id="creator-main",
                name="主账号",
                platform="小红书",
                positioning="学习与生活记录",
                target_audience=["需要简单执行方案的人"],
                content_style=["真诚", "具体"],
                forbidden_expressions=["夸大承诺"],
                goals=["增加收藏"],
                content_formats=["图文"],
                publish_frequency="每周 3 篇",
                notes="测试账号档案。",
            )
        )
        JsonRepository(data_dir, BenchmarkPost).create(
            BenchmarkPost(
                id="benchmark-post-001",
                account_id="benchmark-account-001",
                title="新手学习计划",
                url="",
                content_type="图文",
                cover_text="新手计划",
                raw_content="把计划拆到每天都能完成的小步骤。",
                metrics={"likes": 10, "saves": 5},
                tags=["tag-usage-topic"],
                ai_analysis={},
                borrowable_points=[],
                non_borrowable_points=[],
                rule_card_candidates=[],
            )
        )
        JsonRepository(data_dir, CustomTag).create(
            CustomTag(
                id="tag-usage-topic",
                name="适合选题",
                type="usage",
                description="用于选题生成。",
                scope=["benchmark_post", "rule_card", "topic_item", "content_draft", "publish_task"],
                weight=4,
            )
        )


if __name__ == "__main__":
    unittest.main()
