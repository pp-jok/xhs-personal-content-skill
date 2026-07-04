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

    def test_init_workspace_creates_expected_local_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self._run_cli(["init-workspace", "--workspace", temp_dir])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["workspace"], temp_dir)
            self.assertTrue((Path(temp_dir) / "reports").exists())
            self.assertTrue((Path(temp_dir) / "creator-profiles").exists())
            self.assertIn("creator_profile.json", output["result"]["missing_required_files"])

    def test_upsert_profile_writes_single_file_and_collection_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "profile-input.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "creator-main",
                        "name": "测试账号",
                        "platform": "小红书",
                        "positioning": "职场新人表达成长",
                        "target_audience": ["职场新人"],
                        "content_style": ["真实", "具体"],
                        "forbidden_expressions": ["夸张承诺"],
                        "goals": ["提升收藏"],
                        "content_formats": ["图文"],
                        "publish_frequency": "每周 3 篇",
                        "notes": "测试资料。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["upsert-profile", "--workspace", temp_dir, "--file", str(source)])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["id"], "creator-main")
            self.assertTrue((Path(temp_dir) / "creator_profile.json").exists())
            self.assertTrue((Path(temp_dir) / "creator-profiles" / "creator-main.json").exists())

    def test_add_benchmark_account_and_post_merge_root_lists_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            account_file = Path(temp_dir) / "account.json"
            post_file = Path(temp_dir) / "post.json"
            account_file.write_text(
                json.dumps(
                    {
                        "id": "benchmark-account-001",
                        "name": "对标账号",
                        "url": "",
                        "niche": "职场表达",
                        "reason_to_follow": "场景具体。",
                        "learnable_points": ["场景开头"],
                        "non_learnable_points": ["标题略焦虑"],
                        "tags": ["tag-usage-topic"],
                        "summary": "适合学习表达结构。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            post_file.write_text(
                json.dumps(
                    {
                        "id": "benchmark-post-001",
                        "account_id": "benchmark-account-001",
                        "title": "汇报如何说清楚",
                        "url": "",
                        "content_type": "图文",
                        "cover_text": "汇报先讲结论",
                        "raw_content": "先说结论，再说卡点，最后说下一步。",
                        "metrics": {"likes": 10, "comments": 1, "saves": 5},
                        "tags": ["tag-usage-topic"],
                        "ai_analysis": {},
                        "borrowable_points": ["三句结构"],
                        "non_borrowable_points": ["不要制造焦虑"],
                        "rule_card_candidates": [{"name": "三句结构", "type": "structure", "summary": "先结论后过程。"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            account_output = self._run_cli(["add-benchmark-account", "--workspace", temp_dir, "--file", str(account_file)])
            post_output = self._run_cli(["add-benchmark-post", "--workspace", temp_dir, "--file", str(post_file)])
            account_repeat = self._run_cli(["add-benchmark-account", "--workspace", temp_dir, "--file", str(account_file)])

            accounts = json.loads((Path(temp_dir) / "benchmark_account.json").read_text(encoding="utf-8"))
            posts = json.loads((Path(temp_dir) / "benchmark_post.json").read_text(encoding="utf-8"))
            self.assertTrue(account_output["ok"])
            self.assertTrue(post_output["ok"])
            self.assertEqual(account_repeat["result"]["total"], 1)
            self.assertEqual(len(accounts), 1)
            self.assertEqual(len(posts), 1)
            self.assertTrue((Path(temp_dir) / "benchmark-posts" / "benchmark-post-001.json").exists())

    def test_add_feedback_appends_issues_and_validate_workspace_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            feedback_file = Path(temp_dir) / "feedback.json"
            feedback_file.write_text(
                json.dumps(
                    {
                        "reviewer": "测试者",
                        "reviewed_at": "2026-07-04",
                        "overall_notes": "标题太 AI。",
                        "issues": [
                            {
                                "step": "title",
                                "problem": "像模板。",
                                "suggestion": "改成真人经验口吻。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            feedback_output = self._run_cli(["add-feedback", "--workspace", temp_dir, "--file", str(feedback_file)])
            validation_output = self._run_cli(["validate-workspace", "--workspace", temp_dir])

            self.assertTrue(feedback_output["ok"])
            self.assertEqual(feedback_output["result"]["issue_count"], 1)
            self.assertFalse(validation_output["result"]["ready_for_real_sample_validation"])
            self.assertIn("creator_profile.json", validation_output["result"]["missing_required_files"])

    def test_add_custom_tags_merges_root_list_and_collection_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            tag_file = Path(temp_dir) / "tags.json"
            tag_file.write_text(
                json.dumps(
                    [
                        {
                            "id": "tag-usage-topic",
                            "name": "适合选题",
                            "type": "usage",
                            "description": "用于选题。",
                            "scope": ["benchmark_post", "rule_card", "topic_item"],
                            "weight": 4,
                        },
                        {
                            "id": "tag-risk-ai",
                            "name": "避免 AI 感",
                            "type": "risk",
                            "description": "避免模板化表达。",
                            "scope": ["content_draft", "rule_card"],
                            "weight": 5,
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["add-custom-tags", "--workspace", temp_dir, "--file", str(tag_file)])
            repeat = self._run_cli(["add-custom-tags", "--workspace", temp_dir, "--file", str(tag_file)])

            tags = json.loads((Path(temp_dir) / "custom_tags.json").read_text(encoding="utf-8"))
            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["total"], 2)
            self.assertEqual(repeat["result"]["total"], 2)
            self.assertEqual(len(tags), 2)
            self.assertTrue((Path(temp_dir) / "custom-tags" / "tag-risk-ai.json").exists())

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
