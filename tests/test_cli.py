import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.main import main  # noqa: E402
from app.capture.browser import BrowserCaptureResult  # noqa: E402
from app.models.core import (  # noqa: E402
    BenchmarkAccount,
    BenchmarkAnalysis,
    BenchmarkPost,
    CaptureRecord,
    ContentDraft,
    ContentInboxItem,
    ContentQualityReview,
    CreatorProfile,
    CustomTag,
    OwnPost,
    RuleCard,
    RuleEvidence,
)
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

    def test_generation_commands_create_rule_topic_draft_publish_task_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            JsonRepository(data_dir, OwnPost).create(
                OwnPost(
                    id="own-post-001",
                    account_id="creator-main",
                    title="测试已发布内容",
                    content_type="图文",
                    published_at="2026-07-04T20:00:00+08:00",
                    metrics={"likes": 10, "comments": 2, "saves": 5},
                    tags=["tag-usage-topic"],
                    source_topic_id="topic-from-benchmark-post-001-1",
                )
            )

            rules = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "generate-rule-cards",
                    "--workspace",
                    temp_dir,
                    "--creator-id",
                    "creator-main",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                ]
            )
            topics = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--creator-id",
                    "creator-main",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                    "--topic-count",
                    "2",
                ]
            )
            draft = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "generate-draft",
                    "--workspace",
                    temp_dir,
                    "--topic-id",
                    "topic-from-benchmark-post-001-1",
                ]
            )
            publish = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "create-publish-task",
                    "--workspace",
                    temp_dir,
                    "--draft-id",
                    draft["result"]["draft_id"],
                    "--planned-publish-time",
                    "2026-07-05T20:00:00+08:00",
                ]
            )
            review = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "review-own-post",
                    "--workspace",
                    temp_dir,
                    "--own-post-id",
                    "own-post-001",
                ]
            )

            self.assertTrue(rules["ok"])
            self.assertEqual(rules["result"]["rule_card_ids"], ["rule-card-from-benchmark-post-001-1"])
            self.assertEqual(len(topics["result"]["topic_ids"]), 2)
            self.assertEqual(draft["result"]["draft_id"], "draft-from-topic-from-benchmark-post-001-1")
            self.assertEqual(publish["result"]["publish_task_id"], "publish-task-from-draft-from-topic-from-benchmark-post-001-1")
            self.assertEqual(review["result"]["review_record_id"], "review-from-own-post-001")
            self.assertTrue((data_dir / "review-records" / "review-from-own-post-001.json").exists())

    def test_add_feedback_creates_rule_card_for_preference_issue(self) -> None:
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
                                "problem": "标题像模板化夸张承诺。",
                                "suggestion": "后续标题优先使用真人经验口吻。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["add-feedback", "--workspace", temp_dir, "--file", str(feedback_file)])

            self.assertEqual(output["result"]["rule_card_ids"], ["feedback-rule-title-1"])
            rule_path = Path(temp_dir) / "rule-cards" / "feedback-rule-title-1.json"
            self.assertTrue(rule_path.exists())
            rule = json.loads(rule_path.read_text(encoding="utf-8"))
            self.assertEqual(rule["type"], "title")
            self.assertIn("真人经验口吻", rule["adaptation_notes"])

    def test_add_inbox_item_creates_and_deduplicates_by_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            url = "https://www.xiaohongshu.com/explore/test-note"

            first = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    url,
                    "--user-intent",
                    "学习选题和视频结构",
                    "--user-reason",
                    "开头很吸引人",
                    "--focus",
                    "title",
                    "--focus",
                    "structure",
                ]
            )
            second = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    url,
                    "--user-intent",
                    "补充学习封面",
                ]
            )

            self.assertTrue(first["ok"])
            self.assertFalse(first["result"]["deduplicated"])
            self.assertTrue(second["result"]["deduplicated"])
            self.assertEqual(first["result"]["id"], second["result"]["id"])
            items = JsonRepository(Path(temp_dir), ContentInboxItem).list_all()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].capture_status, "pending")
            self.assertEqual(items[0].user_intent, "补充学习封面")

    def test_capture_xhs_link_without_manual_file_records_failed_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inbox = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    "https://www.xiaohongshu.com/explore/test-note",
                    "--user-intent",
                    "学习标题",
                ]
            )

            capture = self._run_cli(
                [
                    "capture-xhs-link",
                    "--workspace",
                    temp_dir,
                    "--inbox-item-id",
                    inbox["result"]["id"],
                ]
            )

            self.assertTrue(capture["ok"])
            self.assertEqual(capture["result"]["capture_status"], "failed")
            self.assertIn("title", capture["result"]["missing_fields"])
            record = JsonRepository(Path(temp_dir), CaptureRecord).read(capture["result"]["capture_id"])
            self.assertEqual(record.capture_status, "failed")
            item = JsonRepository(Path(temp_dir), ContentInboxItem).read(inbox["result"]["id"])
            self.assertEqual(item.capture_status, "failed")

    def test_capture_xhs_link_with_cdp_url_records_browser_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inbox = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    "https://www.xiaohongshu.com/explore/test-note?debug_param=redacted",
                    "--user-intent",
                    "学习标题",
                ]
            )
            browser_result = BrowserCaptureResult(
                source_url="https://www.xiaohongshu.com/explore/test-note?debug_param=redacted",
                canonical_url="https://www.xiaohongshu.com/explore/test-note",
                capture_status="success",
                title="真实浏览器标题",
                body="真实浏览器正文",
                content_type="image",
                author={"name": "浏览器作者"},
                published_at="2026-07-05T12:00:00+08:00",
                metrics={"likes": 12, "collects": 8, "comments": 3, "shares": 1},
                images=[{"remote_url": "https://example.test/image.jpg", "download_status": "not_attempted"}],
                video={},
                comments=[{"content": "可见评论"}],
                available_fields=["title", "body", "author", "images"],
                missing_fields=[],
                warnings=[],
                raw_snapshot_path=str(Path(temp_dir) / "captures" / "capture-from-inbox" / "page.html"),
                diagnostics={"page_reachable": True, "selectors_succeeded": ["title"], "selectors_failed": []},
            )

            with patch("app.cli.main.capture_xhs_link_with_browser", return_value=browser_result) as browser_capture:
                capture = self._run_cli(
                    [
                        "capture-xhs-link",
                        "--workspace",
                        temp_dir,
                        "--inbox-item-id",
                        inbox["result"]["id"],
                        "--cdp-url",
                        "http://127.0.0.1:9222",
                    ]
                )

            self.assertTrue(capture["ok"])
            self.assertEqual(capture["result"]["capture_status"], "success")
            browser_capture.assert_called_once()
            record = JsonRepository(Path(temp_dir), CaptureRecord).read(capture["result"]["capture_id"])
            self.assertEqual(record.capture_method, "browser_authorized")
            self.assertEqual(record.title, "真实浏览器标题")
            self.assertEqual(record.canonical_url, "https://www.xiaohongshu.com/explore/test-note")
            self.assertEqual(record.published_at, "2026-07-05T12:00:00+08:00")
            self.assertTrue(record.diagnostics["page_reachable"])

    def test_capture_xhs_link_with_manual_file_creates_partial_capture_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_file = Path(temp_dir) / "manual-capture.json"
            manual_file.write_text(
                json.dumps(
                    {
                        "title": "64型和16型测试有什么区别？",
                        "body": "新版测试加入两个后缀维度。",
                        "content_type": "image",
                        "author": {"name": "可见账号"},
                        "metrics": {"likes": 2, "collects": 3, "comments": None, "shares": None},
                        "comments": [{"content": "想看更多解释"}],
                        "images": [{"path": "screenshot.png", "alt": "首图截图"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            inbox = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    "https://www.xiaohongshu.com/explore/test-note",
                    "--user-intent",
                    "学习选题",
                ]
            )

            capture = self._run_cli(
                [
                    "capture-xhs-link",
                    "--workspace",
                    temp_dir,
                    "--inbox-item-id",
                    inbox["result"]["id"],
                    "--manual-file",
                    str(manual_file),
                ]
            )
            shown = self._run_cli(
                [
                    "show-capture-result",
                    "--workspace",
                    temp_dir,
                    "--capture-id",
                    capture["result"]["capture_id"],
                ]
            )

            self.assertTrue(capture["ok"])
            self.assertEqual(capture["result"]["capture_status"], "partial")
            self.assertEqual(shown["result"]["title"], "64型和16型测试有什么区别？")
            self.assertIn("metrics.comments", shown["result"]["missing_fields"])
            item = JsonRepository(Path(temp_dir), ContentInboxItem).read(inbox["result"]["id"])
            self.assertEqual(item.status, "captured")
            self.assertEqual(item.content_type, "image")

    def test_analyze_captured_post_uses_image_template_and_separates_facts_from_inferences(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            inbox_item, capture = self._seed_capture(data_dir, content_type="image")

            output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["analysis_id"], f"analysis-from-{capture.id}")
            self.assertEqual(output["result"]["analysis_template"], "image_carousel_tutorial")
            analysis = JsonRepository(data_dir, BenchmarkAnalysis).read(output["result"]["analysis_id"])
            self.assertEqual(analysis.capture_id, capture.id)
            self.assertEqual(analysis.observable_facts["title"], capture.title)
            self.assertIn("inference", analysis.title_analysis)
            self.assertIn("metrics.comments", analysis.uncertainties)
            item = JsonRepository(data_dir, ContentInboxItem).read(inbox_item.id)
            self.assertEqual(item.status, "analyzed")

    def test_analyze_captured_post_uses_video_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            _, capture = self._seed_capture(data_dir, content_type="video")

            output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["analysis_template"], "video_tutorial")

    def test_promote_to_benchmark_creates_account_post_and_links_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            inbox_item, capture = self._seed_capture(data_dir, content_type="image")
            analysis_output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])

            promoted = self._run_cli(["promote-to-benchmark", "--workspace", temp_dir, "--inbox-item-id", inbox_item.id])

            self.assertTrue(promoted["ok"])
            self.assertEqual(promoted["result"]["benchmark_post_id"], f"benchmark-post-from-{inbox_item.id}")
            post = JsonRepository(data_dir, BenchmarkPost).read(promoted["result"]["benchmark_post_id"])
            account = JsonRepository(data_dir, BenchmarkAccount).read(promoted["result"]["benchmark_account_id"])
            analysis = JsonRepository(data_dir, BenchmarkAnalysis).read(analysis_output["result"]["analysis_id"])
            item = JsonRepository(data_dir, ContentInboxItem).read(inbox_item.id)
            self.assertEqual(post.title, capture.title)
            self.assertEqual(post.account_id, account.id)
            self.assertEqual(analysis.benchmark_post_id, post.id)
            self.assertEqual(item.status, "promoted_to_benchmark")

    def test_create_rule_from_analysis_creates_candidate_rule_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            _, capture = self._seed_capture(data_dir, content_type="image")
            analysis_output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])

            output = self._run_cli(
                [
                    "create-rule-from-analysis",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    analysis_output["result"]["analysis_id"],
                    "--candidate-id",
                    f"candidate-rule-from-{capture.id}-1",
                ]
            )

            self.assertTrue(output["ok"])
            rule = JsonRepository(data_dir, RuleCard).read(output["result"]["rule_id"])
            evidence = JsonRepository(data_dir, RuleEvidence).read(output["result"]["evidence_id"])
            self.assertEqual(rule.status, "candidate")
            self.assertEqual(rule.strength, "weak")
            self.assertEqual(evidence.rule_id, rule.id)
            self.assertEqual(evidence.source_type, "benchmark_analysis")
            self.assertIn("新手如何做清晰表达", evidence.observable_fact)

    def test_rule_lifecycle_commands_update_status_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            rule = self._seed_rule(data_dir, rule_id="rule-001")

            approved = self._run_cli(["approve-rule", "--workspace", temp_dir, "--rule-id", rule.id])
            testing = self._run_cli(["mark-rule-testing", "--workspace", temp_dir, "--rule-id", rule.id])
            success = self._run_cli(["record-rule-result", "--workspace", temp_dir, "--rule-id", rule.id, "--result", "success"])
            failure = self._run_cli(["record-rule-result", "--workspace", temp_dir, "--rule-id", rule.id, "--result", "failure"])
            rejected = self._run_cli(["reject-rule", "--workspace", temp_dir, "--rule-id", rule.id, "--reason", "不适合当前账号"])
            deprecated = self._run_cli(
                [
                    "deprecate-rule",
                    "--workspace",
                    temp_dir,
                    "--rule-id",
                    rule.id,
                    "--reason",
                    "被更具体的规则替代",
                    "--superseded-by",
                    "rule-new",
                ]
            )

            final_rule = JsonRepository(data_dir, RuleCard).read(rule.id)
            self.assertEqual(approved["result"]["status"], "approved")
            self.assertEqual(testing["result"]["status"], "testing")
            self.assertEqual(success["result"]["success_count"], 1)
            self.assertEqual(failure["result"]["failure_count"], 1)
            self.assertEqual(rejected["result"]["status"], "rejected")
            self.assertEqual(deprecated["result"]["status"], "deprecated")
            self.assertEqual(final_rule.validation_count, 2)
            self.assertEqual(final_rule.deprecated_reason, "被更具体的规则替代")
            self.assertIn("rule-new", final_rule.supersedes)

    def test_check_rule_relations_marks_duplicates_and_context_differences_without_false_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            first = self._seed_rule(data_dir, "rule-title-a", summary="标题要包含具体对象", scenarios=["图文标题"])
            second = self._seed_rule(data_dir, "rule-title-b", summary="标题要包含具体对象", scenarios=["视频标题"])
            third = self._seed_rule(data_dir, "rule-title-c", summary="标题可以保留悬念", scenarios=["图文标题"])

            output = self._run_cli(["check-rule-relations", "--workspace", temp_dir])

            self.assertTrue(output["ok"])
            self.assertIn([first.id, second.id], output["result"]["duplicates"])
            self.assertIn([first.id, second.id], output["result"]["context_differences"])
            conflict_pairs = output["result"]["conflicts"]
            self.assertIn([first.id, third.id], conflict_pairs)
            self.assertNotIn([first.id, second.id], conflict_pairs)

    def test_add_quality_review_creates_review_and_updates_draft_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_draft_and_rules_for_quality(data_dir)
            review_file = Path(temp_dir) / "quality-review.json"
            review_file.write_text(
                json.dumps(
                    {
                        "id": "quality-review-001",
                        "draft_id": "draft-quality-001",
                        "review_type": "pre_publish",
                        "account_fit_score": 4,
                        "publishability_score": 3,
                        "title_score": 2,
                        "cover_score": 4,
                        "structure_score": 3,
                        "tone_score": 4,
                        "revision_count": 2,
                        "major_rewrite_required": True,
                        "issues": [
                            {"area": "title", "problem": "标题太模板", "action": "重写标题"},
                            {"area": "script", "problem": "脚本不够口语", "action": "重写口播"},
                        ],
                        "accepted_rules": ["rule-validated"],
                        "rejected_rules": ["rule-weak"],
                        "reviewer_notes": "需要大改标题。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["add-quality-review", "--workspace", temp_dir, "--file", str(review_file)])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["id"], "quality-review-001")
            review = JsonRepository(data_dir, ContentQualityReview).read("quality-review-001")
            draft = JsonRepository(data_dir, ContentDraft).read("draft-quality-001")
            self.assertEqual(review.title_score, 2)
            self.assertEqual(draft.quality_review["latest_review_id"], "quality-review-001")

    def test_generate_quality_report_outputs_quality_metrics_not_just_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_draft_and_rules_for_quality(data_dir)
            JsonRepository(data_dir, ContentQualityReview).create(
                ContentQualityReview(
                    id="quality-review-001",
                    draft_id="draft-quality-001",
                    review_type="pre_publish",
                    account_fit_score=5,
                    publishability_score=4,
                    title_score=4,
                    cover_score=4,
                    structure_score=4,
                    tone_score=5,
                    revision_count=0,
                    major_rewrite_required=False,
                    issues=[],
                    accepted_rules=["rule-validated"],
                    rejected_rules=[],
                    reviewer_notes="小改可用。",
                )
            )
            JsonRepository(data_dir, ContentQualityReview).create(
                ContentQualityReview(
                    id="quality-review-002",
                    draft_id="draft-quality-002",
                    review_type="pre_publish",
                    account_fit_score=2,
                    publishability_score=2,
                    title_score=1,
                    cover_score=3,
                    structure_score=2,
                    tone_score=2,
                    revision_count=3,
                    major_rewrite_required=True,
                    issues=[
                        {"area": "title", "problem": "标题重写", "action": "重写标题"},
                        {"area": "script", "problem": "脚本重写", "action": "重写脚本"},
                    ],
                    accepted_rules=[],
                    rejected_rules=["rule-weak"],
                    reviewer_notes="需要大改。",
                )
            )

            output = self._run_cli(["generate-quality-report", "--workspace", temp_dir, "--period", "weekly"])

            self.assertTrue(output["ok"])
            metrics = output["result"]["metrics"]
            self.assertEqual(metrics["review_count"], 2)
            self.assertEqual(metrics["first_pass_rate"], 0.5)
            self.assertEqual(metrics["average_revision_count"], 1.5)
            self.assertEqual(metrics["major_rewrite_rate"], 0.5)
            self.assertEqual(metrics["title_rewrite_rate"], 0.5)
            self.assertEqual(metrics["script_rewrite_rate"], 0.5)
            self.assertEqual(metrics["rule_hit_rate"], 0.5)
            self.assertEqual(metrics["rule_validation_success_rate"], 0.5)
            report = (data_dir / "reports" / "quality_report_weekly.md").read_text(encoding="utf-8")
            self.assertIn("一次通过率", report)
            self.assertIn("平均修改轮次", report)
            self.assertIn("表现差的规则", report)

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

    def _seed_capture(self, data_dir: Path, content_type: str) -> tuple[ContentInboxItem, CaptureRecord]:
        inbox_item = ContentInboxItem(
            id=f"inbox-{content_type}",
            source_url=f"https://www.xiaohongshu.com/explore/{content_type}",
            status="captured",
            capture_status="partial",
            content_type=content_type,
            user_intent="学习选题和结构",
            requested_focus=["title", "structure"],
        )
        capture = CaptureRecord(
            id=f"capture-{content_type}",
            inbox_item_id=inbox_item.id,
            source_url=inbox_item.source_url,
            capture_method="manual",
            capture_status="partial",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题，最后给一个具体做法。",
            content_type=content_type,
            author={"name": "可见账号"},
            metrics={"likes": 12, "collects": 8, "comments": None, "shares": None},
            images=[{"path": "screenshot.png", "alt": "首图"}] if content_type == "image" else [],
            video={"duration_seconds": 35, "has_subtitle": True} if content_type == "video" else {},
            comments=[{"content": "这个方法适合新人"}],
            available_fields=["title", "body", "author", "metrics.likes", "metrics.collects"],
            missing_fields=["metrics.comments", "metrics.shares"],
            warnings=["评论数量不可见。"],
        )
        JsonRepository(data_dir, ContentInboxItem).create(inbox_item)
        JsonRepository(data_dir, CaptureRecord).create(capture)
        return inbox_item, capture

    def _seed_rule(
        self,
        data_dir: Path,
        rule_id: str,
        summary: str = "标题要包含具体对象",
        scenarios: Optional[list[str]] = None,
    ) -> RuleCard:
        rule = RuleCard(
            id=rule_id,
            name=f"规则 {rule_id}",
            type="title",
            source_ids=["benchmark-post-001"],
            applicable_scenarios=scenarios or ["图文标题"],
            rule_summary=summary,
            examples=["给职场新人看的表达模板"],
            risks=["对象过宽会变泛。"],
            adaptation_notes="适合当前账号的新手表达内容。",
        )
        JsonRepository(data_dir, RuleCard).create(rule)
        return rule

    def _seed_draft_and_rules_for_quality(self, data_dir: Path) -> None:
        JsonRepository(data_dir, ContentDraft).create(
            ContentDraft(
                id="draft-quality-001",
                topic_id="topic-quality-001",
                titles=["给新手的表达方法"],
                cover_titles=["新手表达"],
                script="先说问题，再给方法。",
                shot_suggestions=["正面口播"],
                status="draft",
            )
        )
        JsonRepository(data_dir, ContentDraft).create(
            ContentDraft(
                id="draft-quality-002",
                topic_id="topic-quality-002",
                titles=["表达误区"],
                cover_titles=["表达误区"],
                script="列出三个误区。",
                shot_suggestions=["字幕口播"],
                status="draft",
            )
        )
        JsonRepository(data_dir, RuleCard).create(
            RuleCard(
                id="rule-validated",
                name="已验证规则",
                type="title",
                source_ids=["benchmark-post-001"],
                applicable_scenarios=["图文标题"],
                rule_summary="标题包含具体对象。",
                examples=["给职场新人的表达方法"],
                risks=["对象不能太宽。"],
                adaptation_notes="适合当前账号。",
                status="validated",
                strength="strong",
                validation_count=4,
                success_count=3,
                failure_count=1,
            )
        )
        JsonRepository(data_dir, RuleCard).create(
            RuleCard(
                id="rule-weak",
                name="表现差规则",
                type="script",
                source_ids=["benchmark-post-002"],
                applicable_scenarios=["口播脚本"],
                rule_summary="脚本使用强情绪开头。",
                examples=["你一定不知道"],
                risks=["容易像营销号。"],
                adaptation_notes="当前账号不稳定。",
                status="testing",
                strength="weak",
                validation_count=2,
                success_count=0,
                failure_count=2,
            )
        )


if __name__ == "__main__":
    unittest.main()
