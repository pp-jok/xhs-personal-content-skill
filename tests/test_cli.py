import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.main import main, save_provenance_record, save_rule_cards  # noqa: E402
from app.capture.browser import BrowserCaptureResult  # noqa: E402
from app.generation import asset_reference_snapshot  # noqa: E402
from app.models.core import (  # noqa: E402
    BenchmarkAccount,
    BenchmarkAnalysis,
    BenchmarkPost,
    CaptureRecord,
    ContentAsset,
    ContentAssetEvidence,
    ContentDraft,
    ContentInboxItem,
    ContentMechanism,
    ContentQualityReview,
    CreatorProfile,
    CustomTag,
    DecisionRequest,
    OwnPost,
    PublishTask,
    ProvenanceRecord,
    RuleCard,
    RuleEvidence,
    TopicItem,
)
from app.repositories import JsonRepository  # noqa: E402
from app.rules.selection import select_active_rule_cards  # noqa: E402


class RecordingPromptService:
    def __init__(self) -> None:
        self.payloads: dict[str, list[dict[str, Any]]] = {}

    def run(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.setdefault(contract_id, []).append(payload)
        if contract_id == "generate_topic_pool":
            return {
                "topics": [
                    {
                        "title": "测试选题",
                        "content_goal": "提升收藏",
                        "content_format": "图文",
                        "source_rule_cards": [item["id"] for item in payload["rule_cards"]],
                        "reference_posts": [payload["reference_posts"][0]["id"]],
                        "reason": "测试。",
                        "tags": [],
                    }
                ],
                "warnings": [],
            }
        if contract_id == "generate_content_draft":
            return {
                "draft": {
                    "topic_id": payload["topic"]["id"],
                    "titles": ["测试标题"],
                    "cover_titles": ["测试封面"],
                    "script": "测试脚本。",
                    "shot_suggestions": ["测试镜头"],
                    "quality_review": {},
                    "tags": [],
                },
                "warnings": [],
            }
        if contract_id == "review_own_post":
            return {
                "review_record": {
                    "own_post_id": payload["own_post"]["id"],
                    "performance_summary": "测试复盘。",
                    "lessons": ["测试经验"],
                    "next_actions": ["测试行动"],
                    "rule_updates": [
                        {"rule_card_id": item["id"], "suggestion": "测试更新。"} for item in payload["related_rule_cards"]
                    ],
                },
                "warnings": [],
            }
        raise AssertionError(f"Unexpected contract_id: {contract_id}")


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
            generated_rule = JsonRepository(data_dir, RuleCard).read("rule-card-from-benchmark-post-001-1")
            self.assertEqual(generated_rule.status, "candidate")
            self.assertEqual(generated_rule.created_by, "codex")

    def test_init_workspace_creates_expected_local_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self._run_cli(["init-workspace", "--workspace", temp_dir])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["workspace"], temp_dir)
            self.assertTrue((Path(temp_dir) / "reports").exists())
            self.assertTrue((Path(temp_dir) / "creator-profiles").exists())
            self.assertIn("creator_profile.json", output["result"]["missing_required_files"])

    def test_import_mechanism_success_writes_only_content_mechanism(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "mechanism.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "mechanism-cli-001",
                        "name": "复杂工具结果化表达",
                        "description": "把复杂工具能力先翻译成用户能感知的结果。",
                        "source_refs": [
                            {"source_type": "benchmark_analysis", "source_id": "analysis-001"},
                            {"source_type": "capture_record", "source_id": "capture-001"},
                        ],
                        "evidence_summary": {
                            "observed_facts": ["标题同时出现工具名和可见结果"],
                            "inferences": ["内容把工具组合包装成运营结果"],
                            "missing_information": [],
                            "limitations": [],
                            "source_coverage": {"title": "present", "body": "present"},
                        },
                        "problem": "复杂工具内容容易只剩工具名。",
                        "solution": "先讲结果，再解释工具如何实现。",
                        "pattern": ["工具组合", "结果承诺", "流程证据"],
                        "applicable_scope": ["AI工具内容"],
                        "limitations": ["不能夸大时间承诺"],
                        "confidence_level": "medium",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(["import-mechanism", "--workspace", temp_dir, "--file", str(source)])

            self.assertTrue(output["ok"])
            result = output["result"]
            self.assertEqual(result["mechanism_id"], "mechanism-cli-001")
            self.assertEqual(result["status_category"], "created")
            self.assertEqual(result["mechanism_status"], "candidate")
            self.assertEqual(result["confidence_level"], "medium")
            self.assertIn("不会影响正式生成", result["user_summary"])
            for forbidden in ("ContentMechanism", "candidate", "content-mechanisms", ".json", temp_dir):
                self.assertNotIn(forbidden, result["user_summary"])

            saved = JsonRepository(workspace, ContentMechanism).read("mechanism-cli-001")
            self.assertEqual(saved.status, "candidate")
            after = self._snapshot_workspace(workspace)
            changed = sorted(set(after) - set(before))
            self.assertEqual(changed, ["content-mechanisms/mechanism-cli-001.json"])
            for model in (RuleCard, RuleEvidence, DecisionRequest, TopicItem, ContentDraft, PublishTask):
                self.assertEqual(JsonRepository(workspace, model).list_all(), [])

    def test_import_mechanism_failure_writes_nothing_and_hides_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "bad-mechanism.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "mechanism-cli-bad",
                        "name": "复杂工具结果化表达",
                        "description": "把复杂工具能力先翻译成用户能感知的结果。",
                        "evidence_summary": {
                            "observed_facts": [],
                            "inferences": ["这个内容应该适合学习"],
                            "user_stated_preferences": [],
                        },
                        "problem": "复杂工具内容容易只剩工具名。",
                        "solution": "先讲结果，再解释工具如何实现。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(["import-mechanism", "--workspace", temp_dir, "--file", str(source)], expected_code=1)

            self.assertFalse(output["ok"])
            self.assertIn("至少一条可观察事实", output["error"])
            for forbidden in ("ContentMechanism", "not_enough_evidence", ".json", temp_dir):
                self.assertNotIn(forbidden, output["error"])
            self.assertEqual(self._snapshot_workspace(workspace), before)
            self.assertEqual(JsonRepository(workspace, ContentMechanism).list_all(), [])

    def test_import_mechanism_invalid_input_does_not_create_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "missing-workspace"
            source = Path(temp_dir) / "bad-mechanism.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "mechanism-cli-bad",
                        "name": "复杂工具结果化表达",
                        "description": "把复杂工具能力先翻译成用户能感知的结果。",
                        "evidence_summary": {"observed_facts": ["很好"]},
                        "problem": "用户难以理解复杂内容。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["import-mechanism", "--workspace", str(workspace), "--file", str(source)], expected_code=1)

            self.assertFalse(output["ok"])
            self.assertIn("至少一条可观察事实", output["error"])
            self.assertFalse(workspace.exists())

    def test_import_mechanism_not_enough_evidence_does_not_create_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "missing-workspace"
            source = Path(temp_dir) / "not-enough.json"
            source.write_text(
                json.dumps(
                    {
                        "id": "mechanism-cli-not-enough",
                        "name": "复杂工具结果化表达",
                        "description": "把复杂工具能力先翻译成用户能感知的结果。",
                        "evidence_summary": {
                            "observed_facts": [],
                            "inferences": ["这个内容应该适合学习"],
                        },
                        "problem": "复杂工具内容容易只剩工具名。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["import-mechanism", "--workspace", str(workspace), "--file", str(source)], expected_code=1)

            self.assertFalse(output["ok"])
            self.assertIn("至少一条可观察事实", output["error"])
            self.assertFalse(workspace.exists())

    def test_import_mechanism_bad_file_does_not_create_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "missing-workspace"
            missing_file = Path(temp_dir) / "missing.json"
            malformed_file = Path(temp_dir) / "malformed.json"
            not_object_file = Path(temp_dir) / "list.json"
            malformed_file.write_text("{", encoding="utf-8")
            not_object_file.write_text("[]", encoding="utf-8")

            for source in (missing_file, malformed_file, not_object_file):
                with self.subTest(source=source.name):
                    output = self._run_cli(
                        ["import-mechanism", "--workspace", str(workspace), "--file", str(source)],
                        expected_code=1,
                    )
                    self.assertFalse(output["ok"])
                    self.assertFalse(workspace.exists())

    def test_import_mechanism_duplicate_id_preserves_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "mechanism.json"
            payload = {
                "id": "mechanism-cli-duplicate",
                "name": "复杂工具结果化表达",
                "description": "把复杂工具能力先翻译成用户能感知的结果。",
                "source_refs": [
                    {"source_type": "benchmark_analysis", "source_id": "analysis-001"},
                    {"source_type": "capture_record", "source_id": "capture-001"},
                ],
                "evidence_summary": {"observed_facts": ["标题包含10min"]},
                "problem": "复杂工具内容容易只剩工具名。",
                "solution": "先讲结果，再解释工具如何实现。",
                "pattern": ["结果承诺"],
            }
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            first = self._run_cli(["import-mechanism", "--workspace", str(workspace), "--file", str(source)])
            before = self._snapshot_workspace(workspace)

            second = self._run_cli(["import-mechanism", "--workspace", str(workspace), "--file", str(source)], expected_code=1)

            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])
            self.assertIn("同名候选内容机制已存在", second["error"])
            self.assertEqual(self._snapshot_workspace(workspace), before)

    def test_import_mechanism_limited_summary_keeps_missing_information(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "limited-mechanism.json"
            source.write_text(
                json.dumps(
                    {
                        "name": "封面结果前置",
                        "description": "先让用户看到结果，再解释过程。",
                        "source_refs": [],
                        "evidence_summary": {
                            "observed_facts": ["封面强调 10 分钟完成一个看得见的结果"],
                            "missing_information": ["未获取评论区"],
                            "limitations": ["不能确认用户真实需求"],
                        },
                        "problem": "过程型内容容易显得门槛高。",
                        "solution": "",
                        "pattern": [],
                        "confidence_level": "high",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["import-mechanism", "--workspace", temp_dir, "--file", str(source)])

            self.assertTrue(output["ok"])
            result = output["result"]
            self.assertEqual(result["status_category"], "limited_created")
            self.assertEqual(result["confidence_level"], "low")
            self.assertEqual(result["missing_information"], ["未获取评论区"])
            self.assertIn("未获取评论区", result["user_summary"])
            self.assertEqual(result["machine_summary"]["missing_information"], ["未获取评论区"])

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

    def test_provenance_cli_shows_sources_without_promoting_codex_inference_to_user_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-candidate-001",
                    name="标题真人经验口吻",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="标题要保留真人判断。",
                    examples=["我试过后发现..."],
                    risks=["不要夸张承诺"],
                    adaptation_notes="适合当前账号。",
                    status="candidate",
                    provenance_refs=["prov-001"],
                    created_by="codex",
                )
            )
            JsonRepository(workspace, ProvenanceRecord).upsert(
                ProvenanceRecord(
                    id="prov-001",
                    target_object_type="rule_card",
                    target_object_id="rule-candidate-001",
                    source_object_type="benchmark_analysis",
                    source_object_id="analysis-001",
                    source_version=1,
                    actor="codex",
                    artifact_nature="inference",
                    method="mvp-pr1-manual-review",
                    note="Codex 基于可见事实提出候选规则。",
                )
            )

            output = self._run_cli(
                [
                    "show-provenance",
                    "--workspace",
                    temp_dir,
                    "--target-type",
                    "rule_card",
                    "--target-id",
                    "rule-candidate-001",
                ]
            )

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["target"]["object_id"], "rule-candidate-001")
            self.assertEqual(output["result"]["records"][0]["actor"], "codex")
            self.assertEqual(output["result"]["records"][0]["artifact_nature"], "inference")
            self.assertNotEqual(output["result"]["records"][0]["artifact_nature"], "fact")

    def test_import_provenance_validates_target_and_source_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source_file = workspace / "provenance.json"
            source_file.write_text(
                json.dumps(
                    {
                        "id": "prov-import",
                        "target_object_type": "rule_card",
                        "target_object_id": "missing-rule",
                        "source_object_type": "benchmark_analysis",
                        "source_object_id": "missing-analysis",
                        "actor": "codex",
                        "artifact_nature": "inference",
                        "method": "test",
                        "note": "bad ref",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            failed = self._run_cli(
                ["--data-dir", temp_dir, "import-json", "provenance-records", str(source_file)],
                expected_code=1,
            )
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-provenance-target",
                    name="规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="适合账号。",
                    status="candidate",
                )
            )
            JsonRepository(workspace, BenchmarkAnalysis).upsert(
                BenchmarkAnalysis(
                    id="analysis-provenance-source",
                    capture_id="capture-001",
                    observable_facts={"title": "标题"},
                )
            )
            source_file.write_text(
                json.dumps(
                    {
                        "id": "prov-import",
                        "target_object_type": "rule_card",
                        "target_object_id": "rule-provenance-target",
                        "source_object_type": "benchmark_analysis",
                        "source_object_id": "analysis-provenance-source",
                        "actor": "codex",
                        "artifact_nature": "inference",
                        "method": "test",
                        "note": "valid ref",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            imported = self._run_cli(["--data-dir", temp_dir, "import-json", "provenance-records", str(source_file)])

            self.assertFalse(failed["ok"])
            self.assertIn("not found", failed["error"])
            self.assertTrue(imported["ok"])

    def test_decision_cli_confirm_and_reject_update_candidate_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-needs-decision",
                    name="候选标题规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="标题更像真人经验。",
                    examples=["我自己踩过的坑..."],
                    risks=["不能编造经历"],
                    adaptation_notes="用户确认后用于后续生成。",
                    status="candidate",
                )
            )

            created = self._run_cli(
                [
                    "create-decision",
                    "--workspace",
                    temp_dir,
                    "--target-type",
                    "rule_card",
                    "--target-id",
                    "rule-needs-decision",
                    "--question",
                    "是否确认这条规则？",
                    "--option",
                    "confirm",
                    "--option",
                    "reject",
                    "--recommendation",
                    "confirm",
                    "--recommendation-reason",
                    "证据来自对标拆解。",
                    "--impact",
                    "确认后用于后续标题生成。",
                ]
            )
            listed = self._run_cli(["list-decisions", "--workspace", temp_dir, "--status", "pending"])
            resolved = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "confirm",
                    "--user-note",
                    "这条适合我。",
                ]
            )
            rule = JsonRepository(workspace, RuleCard).read("rule-needs-decision")

            self.assertTrue(created["ok"])
            self.assertEqual(created["result"]["status"], "pending")
            self.assertEqual(len(listed["result"]), 1)
            self.assertEqual(resolved["result"]["status"], "confirmed")
            self.assertEqual(rule.status, "approved")
            self.assertEqual(rule.version, 2)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).read(created["result"]["decision_id"]).resolved_by, "user")

            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-rejected-by-user",
                    name="候选封面规则",
                    type="cover",
                    source_ids=["analysis-002"],
                    applicable_scenarios=["封面"],
                    rule_summary="封面使用夸张结果。",
                    examples=["三天改变..."],
                    risks=["太营销"],
                    adaptation_notes="需要用户决定。",
                    status="candidate",
                )
            )
            reject_decision = self._run_cli(
                [
                    "create-decision",
                    "--workspace",
                    temp_dir,
                    "--target-type",
                    "rule_card",
                    "--target-id",
                    "rule-rejected-by-user",
                    "--question",
                    "是否确认这条规则？",
                    "--option",
                    "confirm",
                    "--option",
                    "reject",
                    "--recommendation",
                    "reject",
                    "--recommendation-reason",
                    "风险过高。",
                    "--impact",
                    "拒绝后不会进入长期规则。",
                ]
            )
            self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    reject_decision["result"]["decision_id"],
                    "--selected-option",
                    "reject",
                    "--user-note",
                    "太营销。",
                ]
            )
            rejected_rule = JsonRepository(workspace, RuleCard).read("rule-rejected-by-user")

            self.assertEqual(rejected_rule.status, "rejected")

    def test_candidate_rule_decision_commands_use_safe_user_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            rule = RuleCard(
                id="rule-safe-decision",
                name="候选标题规则",
                type="title",
                source_ids=["analysis-001"],
                applicable_scenarios=["标题"],
                rule_summary="标题先说明具体对象。",
                examples=["职场新人如何准备工作汇报"],
                risks=["单篇内容形成"],
                adaptation_notes="需要更多样本验证。",
                status="candidate",
                strength="weak",
                created_by="codex",
            )
            JsonRepository(workspace, RuleCard).create(rule)
            JsonRepository(workspace, RuleEvidence).create(
                RuleEvidence(
                    id="evidence-safe-decision",
                    rule_id=rule.id,
                    source_type="benchmark_analysis",
                    source_id="analysis-001",
                    source_fragment="标题",
                    evidence_type="title",
                    observable_fact="职场新人如何准备工作汇报",
                    inference="可见标题支持候选规则。",
                )
            )

            created = self._run_cli(["create-rule-decision", "--workspace", temp_dir, "--rule-id", rule.id])
            listed = self._run_cli(["list-pending-rule-decisions", "--workspace", temp_dir])
            detail = self._run_cli(
                ["show-rule-decision", "--workspace", temp_dir, "--decision-id", created["result"]["decision_id"]]
            )
            resolved = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "确认使用",
                    "--user-note",
                    "适合当前账号。",
                ]
            )

            saved_rule = JsonRepository(workspace, RuleCard).read(rule.id)
            saved_decision = JsonRepository(workspace, DecisionRequest).read(created["result"]["decision_id"])
            self.assertTrue(created["ok"])
            self.assertIn("单篇或有限证据", created["result"]["user_summary"])
            self.assertNotIn(rule.id, created["result"]["user_summary"])
            self.assertEqual(len(listed["result"]["items"]), 1)
            self.assertIn("帖子证据", listed["result"]["items"][0])
            self.assertNotIn(rule.id, listed["result"]["items"][0])
            self.assertIn("确认使用", detail["result"]["user_summary"])
            self.assertNotIn(rule.id, detail["result"]["user_summary"])
            self.assertEqual(saved_rule.status, "approved")
            self.assertEqual(saved_decision.selected_option, "确认使用")
            self.assertEqual(saved_decision.resolved_by, "user")
            self.assertIn("已批准状态", resolved["result"]["user_summary"])

            rejected_rule = RuleCard(
                id="rule-safe-reject",
                name="另一条候选规则",
                type="cover",
                source_ids=["analysis-002"],
                applicable_scenarios=["封面"],
                rule_summary="封面避免绝对承诺。",
                examples=["三天一定见效"],
                risks=["表达过强"],
                adaptation_notes="保留风险提醒。",
                status="candidate",
            )
            JsonRepository(workspace, RuleCard).create(rejected_rule)
            rejected_created = self._run_cli(
                ["create-rule-decision", "--workspace", temp_dir, "--rule-id", rejected_rule.id]
            )
            rejected_result = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    rejected_created["result"]["decision_id"],
                    "--selected-option",
                    "暂不使用",
                ]
            )
            self.assertEqual(JsonRepository(workspace, RuleCard).read(rejected_rule.id).status, "rejected")
            self.assertEqual(select_active_rule_cards([JsonRepository(workspace, RuleCard).read(rejected_rule.id)]), [])
            self.assertIn("已拒绝状态", rejected_result["result"]["user_summary"])

    def test_candidate_rule_decision_rejects_stale_target_after_direct_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            rule = RuleCard(
                id="rule-stale-decision",
                name="候选规则",
                type="title",
                source_ids=["analysis-001"],
                applicable_scenarios=["标题"],
                rule_summary="标题先说明对象。",
                examples=["职场新人如何汇报"],
                risks=["单篇内容形成"],
                adaptation_notes="需要更多样本。",
                status="candidate",
            )
            JsonRepository(workspace, RuleCard).create(rule)
            created = self._run_cli(["create-rule-decision", "--workspace", temp_dir, "--rule-id", rule.id])
            self._run_cli(["approve-rule", "--workspace", temp_dir, "--rule-id", rule.id])
            listed = self._run_cli(["list-pending-rule-decisions", "--workspace", temp_dir])
            resolved = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "确认使用",
                ],
                expected_code=1,
            )

            self.assertEqual(listed["result"]["items"], [])
            self.assertEqual(listed["result"]["stale_count"], 1)
            self.assertIn("状态已发生变化", resolved["error"])
            self.assertEqual(JsonRepository(workspace, DecisionRequest).read(created["result"]["decision_id"]).status, "pending")

    def test_candidate_rule_decision_rejects_multiple_pending_records_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            rule = RuleCard(
                id="rule-conflicting-decisions",
                name="候选规则",
                type="title",
                source_ids=["analysis-001"],
                applicable_scenarios=["标题"],
                rule_summary="标题先说明对象。",
                examples=["职场新人如何汇报"],
                risks=["单篇内容形成"],
                adaptation_notes="需要更多样本。",
                status="candidate",
            )
            JsonRepository(workspace, RuleCard).create(rule)
            decisions = JsonRepository(workspace, DecisionRequest)
            for decision_id, question in (("decision-conflict-first", "第一个决定"), ("decision-conflict-second", "第二个决定")):
                decisions.create(
                    DecisionRequest(
                        id=decision_id,
                        target_object_type="rule_card",
                        target_object_id=rule.id,
                        question=question,
                        options=["确认使用", "暂不使用"],
                        option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
                        recommendation="暂不使用",
                        recommendation_reason="有限证据。",
                        impact="确认或拒绝。",
                        expected_target_version=rule.version,
                        created_by="codex",
                    )
                )

            for decision_id in ("decision-conflict-first", "decision-conflict-second"):
                resolved = self._run_cli(
                    [
                        "resolve-decision",
                        "--workspace",
                        temp_dir,
                        "--decision-id",
                        decision_id,
                        "--selected-option",
                        "确认使用",
                    ],
                    expected_code=1,
                )
                self.assertIn("多个待处理决定", resolved["error"])

            self.assertEqual(JsonRepository(workspace, RuleCard).read(rule.id).status, "candidate")
            for decision in decisions.list_all():
                self.assertEqual(decision.status, "pending")
                self.assertEqual(decision.selected_option, "")
                self.assertIsNone(decision.resolved_by)
                self.assertIsNone(decision.resolved_at)

    def test_decision_cli_uses_explicit_outcome_mapping_for_chinese_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-chinese-decision",
                    name="候选规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="标题更口语。",
                    examples=["我试过..."],
                    risks=["不能编造经历"],
                    adaptation_notes="确认后使用。",
                    status="candidate",
                )
            )
            created = self._run_cli(
                [
                    "create-decision",
                    "--workspace",
                    temp_dir,
                    "--target-type",
                    "rule_card",
                    "--target-id",
                    "rule-chinese-decision",
                    "--question",
                    "是否确认？",
                    "--option",
                    "确认使用",
                    "--option",
                    "暂不使用",
                    "--option-outcome",
                    "确认使用=confirmed",
                    "--option-outcome",
                    "暂不使用=rejected",
                    "--recommendation",
                    "确认使用",
                    "--recommendation-reason",
                    "证据清晰。",
                    "--impact",
                    "确认后进入长期规则。",
                ]
            )
            resolved = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "确认使用",
                    "--user-note",
                    "确认使用。",
                ]
            )
            rule = JsonRepository(workspace, RuleCard).read("rule-chinese-decision")

            self.assertEqual(resolved["result"]["status"], "confirmed")
            self.assertEqual(rule.status, "approved")
            self.assertEqual(JsonRepository(workspace, DecisionRequest).read(created["result"]["decision_id"]).resolved_by, "user")

    def test_decision_cli_rejects_repeated_resolve_and_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-once",
                    name="候选规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="确认后使用。",
                    status="candidate",
                )
            )
            created = self._create_rule_decision(temp_dir, "rule-once", question="是否确认一次？")
            self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "confirm",
                ]
            )
            repeated = self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    created["result"]["decision_id"],
                    "--selected-option",
                    "reject",
                ],
                expected_code=1,
            )

            self.assertFalse(repeated["ok"])
            self.assertIn("已完成", repeated["error"])
            self.assertEqual(JsonRepository(workspace, RuleCard).read("rule-once").status, "approved")

    def test_decision_cli_does_not_overwrite_resolved_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-repeat",
                    name="候选规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="确认后使用。",
                    status="candidate",
                )
            )
            first = self._create_rule_decision(temp_dir, "rule-repeat", question="是否确认重复？")
            duplicate_pending = self._create_rule_decision(temp_dir, "rule-repeat", question="是否确认重复？")
            self._run_cli(
                [
                    "resolve-decision",
                    "--workspace",
                    temp_dir,
                    "--decision-id",
                    first["result"]["decision_id"],
                    "--selected-option",
                    "confirm",
                ]
            )
            second = self._create_rule_decision(temp_dir, "rule-repeat", question="是否确认重复？")
            decisions = JsonRepository(workspace, DecisionRequest).list_all()

            self.assertEqual(first["result"]["decision_id"], duplicate_pending["result"]["decision_id"])
            self.assertNotEqual(first["result"]["decision_id"], second["result"]["decision_id"])
            self.assertEqual(sorted(item.status for item in decisions), ["confirmed", "pending"])

    def test_decision_cli_validates_target_type_and_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_type = self._run_cli(
                [
                    "create-decision",
                    "--workspace",
                    temp_dir,
                    "--target-type",
                    "rule-cards",
                    "--target-id",
                    "missing",
                    "--question",
                    "是否确认？",
                    "--option",
                    "confirm",
                    "--option",
                    "reject",
                    "--recommendation",
                    "confirm",
                    "--recommendation-reason",
                    "原因。",
                    "--impact",
                    "影响。",
                ],
                expected_code=1,
            )
            missing_target = self._create_rule_decision(temp_dir, "missing-rule", expected_code=1)

            self.assertIn("Unsupported target object type", invalid_type["error"])
            self.assertIn("not found", missing_target["error"])

    def test_version_and_user_context_cli_expose_plain_language_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-user-context",
                    name="标题要具体",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="标题要有具体对象和场景。",
                    examples=["给刚入职的人..."],
                    risks=["避免过度承诺"],
                    adaptation_notes="适合当前账号。",
                    status="candidate",
                    created_by="codex",
                    provenance_refs=["prov-context"],
                )
            )
            JsonRepository(workspace, ProvenanceRecord).upsert(
                ProvenanceRecord(
                    id="prov-context",
                    target_object_type="rule_card",
                    target_object_id="rule-user-context",
                    source_object_type="benchmark_analysis",
                    source_object_id="analysis-001",
                    actor="codex",
                    artifact_nature="recommendation",
                    method="mvp-pr1",
                    note="建议用户确认后再使用。",
                )
            )
            JsonRepository(workspace, RuleCard).update("rule-user-context", {"status": "approved"})

            versions = self._run_cli(
                [
                    "show-object-versions",
                    "--workspace",
                    temp_dir,
                    "--collection",
                    "rule-cards",
                    "--record-id",
                    "rule-user-context",
                ]
            )
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                main(
                    [
                        "show-object-versions",
                        "--workspace",
                        temp_dir,
                        "--collection",
                        "decision-requests",
                        "--record-id",
                        "decision-001",
                    ]
                )
            context = self._run_cli(
                [
                    "show-user-context",
                    "--workspace",
                    temp_dir,
                    "--collection",
                    "rule-cards",
                    "--record-id",
                    "rule-user-context",
                ]
            )

            self.assertTrue(versions["ok"])
            self.assertEqual(versions["result"]["versions"][0]["object_version"], 1)
            sections = context["result"]["sections"]
            self.assertIn("【已有资料】", sections)
            self.assertIn("【Codex 判断】", sections)
            self.assertIn("【需要你决定】", sections)
            self.assertIn("【已由你决定】", sections)
            self.assertEqual(sections["【需要你决定】"], [])
            self.assertIn("当前状态：approved", "\n".join(sections["【规则状态】"]))

    def test_user_context_uses_type_and_confirmation_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="shared-id",
                    name="旧规则",
                    type="title",
                    source_ids=["legacy"],
                    applicable_scenarios=["标题"],
                    rule_summary="旧规则已 approved，但没有用户确认。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="旧数据。",
                    status="approved",
                )
            )
            JsonRepository(workspace, ContentDraft).upsert(
                ContentDraft(
                    id="shared-id",
                    topic_id="topic-001",
                    titles=["标题"],
                    cover_titles=["封面"],
                    script="草稿正文",
                    shot_suggestions=["镜头"],
                    created_by="codex",
                )
            )
            JsonRepository(workspace, ProvenanceRecord).upsert(
                ProvenanceRecord(
                    id="prov-rule",
                    target_object_type="rule_card",
                    target_object_id="shared-id",
                    source_object_type="benchmark_analysis",
                    source_object_id="analysis-001",
                    actor="codex",
                    artifact_nature="inference",
                    method="test",
                    note="规则推断。",
                )
            )
            JsonRepository(workspace, ProvenanceRecord).upsert(
                ProvenanceRecord(
                    id="prov-draft",
                    target_object_type="content_draft",
                    target_object_id="shared-id",
                    source_object_type="topic_item",
                    source_object_id="topic-001",
                    actor="codex",
                    artifact_nature="generated",
                    method="test",
                    note="草稿生成。",
                )
            )

            rule_context = self._run_cli(
                ["show-user-context", "--workspace", temp_dir, "--collection", "rule-cards", "--record-id", "shared-id"]
            )
            draft_context = self._run_cli(
                ["show-user-context", "--workspace", temp_dir, "--collection", "content-drafts", "--record-id", "shared-id"]
            )
            rule_sections = rule_context["result"]["sections"]
            draft_sections = draft_context["result"]["sections"]

            self.assertNotIn("规则当前状态：approved", rule_sections["【已由你决定】"])
            self.assertIn("当前状态：approved", "\n".join(rule_sections["【规则状态】"]))
            self.assertIn("规则推断。", "\n".join(rule_sections["【Codex 判断】"]))
            self.assertNotIn("草稿生成。", "\n".join(rule_sections["【Codex 生成】"]))
            self.assertIn("草稿生成。", "\n".join(draft_sections["【Codex 生成】"]))

    def test_user_context_only_treats_user_resolved_decisions_as_user_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            for rule_id in ("rule-user-resolved", "rule-system-resolved"):
                JsonRepository(workspace, RuleCard).upsert(
                    RuleCard(
                        id=rule_id,
                        name=rule_id,
                        type="title",
                        source_ids=["analysis-001"],
                        applicable_scenarios=["标题"],
                        rule_summary="规则。",
                        examples=["例子"],
                        risks=["风险"],
                        adaptation_notes="适合账号。",
                        status="approved",
                    )
                )
            for rule_id, actor in (("rule-user-resolved", "user"), ("rule-system-resolved", "system")):
                JsonRepository(workspace, DecisionRequest).upsert(
                    DecisionRequest(
                        id=f"decision-{rule_id}",
                        target_object_type="rule_card",
                        target_object_id=rule_id,
                        question="是否确认？",
                        options=["confirm", "reject"],
                        option_outcomes={"confirm": "confirmed", "reject": "rejected"},
                        recommendation="confirm",
                        recommendation_reason="测试。",
                        impact="测试。",
                        status="confirmed",
                        selected_option="confirm",
                        resolved_at="2026-07-08T00:00:00Z",
                        resolved_by=actor,
                        created_by="codex",
                    )
                )

            user_context = self._run_cli(
                ["show-user-context", "--workspace", temp_dir, "--collection", "rule-cards", "--record-id", "rule-user-resolved"]
            )
            system_context = self._run_cli(
                ["show-user-context", "--workspace", temp_dir, "--collection", "rule-cards", "--record-id", "rule-system-resolved"]
            )

            self.assertIn("规则当前状态：approved", "\n".join(user_context["result"]["sections"]["【已由你决定】"]))
            self.assertEqual(system_context["result"]["sections"]["【已由你决定】"], [])
            self.assertIn("当前状态：approved", "\n".join(system_context["result"]["sections"]["【规则状态】"]))

    def test_user_context_reports_conflict_when_rule_status_disagrees_with_user_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            for rule_id, status in (("rule-approved-user-rejected", "approved"), ("rule-rejected-user-confirmed", "rejected")):
                JsonRepository(workspace, RuleCard).upsert(
                    RuleCard(
                        id=rule_id,
                        name=rule_id,
                        type="title",
                        source_ids=["analysis-001"],
                        applicable_scenarios=["标题"],
                        rule_summary="规则。",
                        examples=["例子"],
                        risks=["风险"],
                        adaptation_notes="适合账号。",
                        status=status,
                    )
                )
            JsonRepository(workspace, DecisionRequest).upsert(
                DecisionRequest(
                    id="decision-user-rejected-approved-rule",
                    target_object_type="rule_card",
                    target_object_id="rule-approved-user-rejected",
                    question="是否确认？",
                    options=["confirm", "reject"],
                    option_outcomes={"confirm": "confirmed", "reject": "rejected"},
                    recommendation="reject",
                    recommendation_reason="测试。",
                    impact="测试。",
                    status="rejected",
                    selected_option="reject",
                    resolved_at="2026-07-08T00:00:00Z",
                    resolved_by="user",
                    created_by="codex",
                )
            )
            JsonRepository(workspace, DecisionRequest).upsert(
                DecisionRequest(
                    id="decision-user-confirmed-rejected-rule",
                    target_object_type="rule_card",
                    target_object_id="rule-rejected-user-confirmed",
                    question="是否确认？",
                    options=["confirm", "reject"],
                    option_outcomes={"confirm": "confirmed", "reject": "rejected"},
                    recommendation="confirm",
                    recommendation_reason="测试。",
                    impact="测试。",
                    status="confirmed",
                    selected_option="confirm",
                    resolved_at="2026-07-08T00:00:00Z",
                    resolved_by="user",
                    created_by="codex",
                )
            )

            approved_context = self._run_cli(
                [
                    "show-user-context",
                    "--workspace",
                    temp_dir,
                    "--collection",
                    "rule-cards",
                    "--record-id",
                    "rule-approved-user-rejected",
                ]
            )
            rejected_context = self._run_cli(
                [
                    "show-user-context",
                    "--workspace",
                    temp_dir,
                    "--collection",
                    "rule-cards",
                    "--record-id",
                    "rule-rejected-user-confirmed",
                ]
            )

            for context in (approved_context, rejected_context):
                sections = context["result"]["sections"]
                self.assertEqual(sections["【已由你决定】"], [])
                self.assertIn("当前规则状态与用户历史决定不一致。", sections["【信息不足】"])

    def test_add_feedback_uses_structured_feedback_nature_instead_of_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            feedback_file = Path(temp_dir) / "feedback.json"
            feedback_file.write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "step": "title",
                                "problem": "这个标题太 AI",
                                "suggestion": "更像真人经验",
                                "feedback_nature": "inferred_preference",
                            },
                            {
                                "step": "title",
                                "problem": "以后不要再用夸张承诺",
                                "suggestion": "",
                                "feedback_nature": "explicit_user_rule",
                                "user_confirmed": True,
                            },
                            {
                                "step": "title",
                                "problem": "长期看可能要更口语，但我还不确定。",
                                "suggestion": "先观察。",
                                "feedback_nature": "uncertain",
                            },
                            {
                                "step": "title",
                                "problem": "这篇以后不要这样写，但只针对这篇。",
                                "suggestion": "本篇重写。",
                                "feedback_nature": "content_specific_feedback",
                            },
                            {"step": "title", "problem": "缺少语义性质字段。", "suggestion": "默认安全。"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["add-feedback", "--workspace", temp_dir, "--file", str(feedback_file)])
            rules = {item.id: item for item in JsonRepository(Path(temp_dir), RuleCard).list_all()}
            decisions = JsonRepository(Path(temp_dir), DecisionRequest).list_all()

            self.assertTrue(output["ok"])
            self.assertEqual(rules["feedback-rule-title-1"].status, "candidate")
            self.assertEqual(rules["feedback-rule-title-1"].created_by, "codex")
            self.assertEqual(rules["feedback-rule-title-2"].status, "approved")
            self.assertEqual(rules["feedback-rule-title-2"].created_by, "user")
            self.assertEqual(rules["feedback-rule-title-3"].status, "candidate")
            self.assertEqual(rules["feedback-rule-title-4"].status, "candidate")
            self.assertEqual(rules["feedback-rule-title-5"].status, "candidate")
            self.assertEqual(len(decisions), 4)
            self.assertEqual(decisions[0].target_object_id, "feedback-rule-title-1")
            pending_decisions = [item for item in decisions if item.status == "pending"]
            self.assertTrue(all(item.expected_target_version == 1 for item in pending_decisions))
            resolved = [item for item in decisions if item.target_object_id == "feedback-rule-title-2"][0]
            self.assertEqual(resolved.status, "confirmed")
            self.assertEqual(resolved.resolved_by, "user")

    def test_explicit_user_rule_creates_auditable_user_decision_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            feedback_file = Path(temp_dir) / "feedback.json"
            feedback_file.write_text(
                json.dumps(
                    {
                        "issues": [
                            {
                                "step": "title",
                                "problem": "标题不要承诺无法证明的结果。",
                                "suggestion": "长期避开夸张承诺。",
                                "feedback_nature": "explicit_user_rule",
                                "user_confirmed": True,
                            },
                            {
                                "step": "cover",
                                "problem": "封面太 AI。",
                                "suggestion": "更口语。",
                                "feedback_nature": "inferred_preference",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(["add-feedback", "--workspace", temp_dir, "--file", str(feedback_file)])
            provenances = JsonRepository(Path(temp_dir), ProvenanceRecord).list_all()
            explicit_provenance = [
                item
                for item in provenances
                if item.target_object_id == "feedback-rule-title-1"
                and item.actor == "user"
                and item.artifact_nature == "decision"
            ]
            inferred_provenance = [
                item
                for item in provenances
                if item.target_object_id == "feedback-rule-cover-2"
                and item.actor == "user"
                and item.artifact_nature == "decision"
            ]
            context = self._run_cli(
                [
                    "show-user-context",
                    "--workspace",
                    temp_dir,
                    "--collection",
                    "rule-cards",
                    "--record-id",
                    "feedback-rule-title-1",
                ]
            )

            self.assertTrue(output["ok"])
            self.assertEqual(len(explicit_provenance), 1)
            self.assertEqual(explicit_provenance[0].method, "explicit-user-rule-input")
            self.assertIn("标题不要承诺无法证明的结果", explicit_provenance[0].note)
            self.assertEqual(inferred_provenance, [])
            self.assertIn("规则当前状态：approved", "\n".join(context["result"]["sections"]["【已由你决定】"]))

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

    def test_save_rule_cards_forces_codex_generated_rules_to_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            saved = save_rule_cards(
                workspace,
                "benchmark-post-001",
                [
                    {
                        "name": "Prompt 返回正式规则",
                        "type": "title",
                        "source_ids": ["benchmark-post-001"],
                        "applicable_scenarios": ["标题"],
                        "rule_summary": "即使 prompt 返回 approved，也不能直接生效。",
                        "examples": ["例子"],
                        "risks": ["风险"],
                        "adaptation_notes": "需要用户确认。",
                        "status": "approved",
                        "created_by": "codex",
                    }
                ],
            )

            self.assertEqual(saved[0].status, "candidate")
            self.assertEqual(saved[0].created_by, "codex")

    def test_save_provenance_record_validates_business_references(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, RuleCard).upsert(
                RuleCard(
                    id="rule-provenance-helper",
                    name="规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="适合账号。",
                )
            )
            JsonRepository(workspace, BenchmarkAnalysis).upsert(
                BenchmarkAnalysis(id="analysis-provenance-helper", capture_id="capture-001", observable_facts={"title": "标题"})
            )
            valid = ProvenanceRecord(
                id="prov-helper-valid",
                target_object_type="rule_card",
                target_object_id="rule-provenance-helper",
                source_object_type="benchmark_analysis",
                source_object_id="analysis-provenance-helper",
                actor="codex",
                artifact_nature="inference",
                method="helper",
                note="合法来源。",
            )
            missing_target = ProvenanceRecord(
                id="prov-helper-missing-target",
                target_object_type="rule_card",
                target_object_id="missing-rule",
                source_object_type="benchmark_analysis",
                source_object_id="analysis-provenance-helper",
                actor="codex",
                artifact_nature="inference",
                method="helper",
                note="非法来源。",
            )
            bad_version = ProvenanceRecord(
                id="prov-helper-bad-version",
                target_object_type="rule_card",
                target_object_id="rule-provenance-helper",
                source_object_type="benchmark_analysis",
                source_object_id="analysis-provenance-helper",
                source_version=99,
                actor="codex",
                artifact_nature="inference",
                method="helper",
                note="非法版本。",
            )

            saved = save_provenance_record(workspace, valid)
            with self.assertRaises(FileNotFoundError):
                save_provenance_record(workspace, missing_target)
            with self.assertRaises(ValueError):
                save_provenance_record(workspace, bad_version)

            self.assertEqual(saved.id, "prov-helper-valid")

    def test_generate_topics_uses_generation_context_and_writes_audited_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved", summary="标题点名具体对象")
            testing = self._seed_rule(data_dir, "rule-testing", status="testing", summary="正文保留行动步骤", scenarios=["正文结构"])
            candidate = self._seed_rule(data_dir, "rule-candidate", status="candidate")
            rejected = self._seed_rule(data_dir, "rule-rejected", status="rejected")
            deprecated = self._seed_rule(data_dir, "rule-deprecated", status="deprecated")
            self._seed_rule_generation_support(data_dir, approved.id, profile_version=1)
            self._seed_rule_generation_support(data_dir, testing.id, profile_version=99, evidence=False)
            before_rules = self._snapshot_collection(data_dir, RuleCard)
            before_evidence = self._snapshot_collection(data_dir, RuleEvidence)
            before_decisions = self._snapshot_collection(data_dir, DecisionRequest)

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--topic-count",
                    "3",
                    "--intent",
                    "准备后续选题",
                    "--content-type",
                    "图文",
                    "--topic-area",
                    "新人入职",
                    "--target-audience",
                    "刚入职的新人",
                    "--format",
                    "清单",
                    "--tone",
                    "直接、具体",
                    "--do",
                    "给出可执行步骤",
                    "--dont",
                    "夸大效果",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                ]
            )

            topics = JsonRepository(data_dir, TopicItem).list_all()
            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["topic_count"], 3)
            self.assertEqual(output["result"]["context_status"], "limited")
            self.assertIn("user_summary", output["result"])
            self.assertEqual(len(topics), 3)
            for topic in topics:
                self.assertEqual(topic.source_profile_id, "creator-main")
                self.assertEqual(topic.source_profile_version, 1)
                self.assertEqual(topic.generation_context_status, "limited")
                self.assertEqual(topic.task_constraints["topic_area"], "新人入职")
                self.assertEqual(topic.reference_posts, ["benchmark-post-001"])
                self.assertEqual(topic.source_rule_cards, [approved.id, testing.id])
                self.assertNotIn(candidate.id, topic.source_rule_cards)
                self.assertNotIn(rejected.id, topic.source_rule_cards)
                self.assertNotIn(deprecated.id, topic.source_rule_cards)
            self.assertEqual(self._snapshot_collection(data_dir, RuleCard), before_rules)
            self.assertEqual(self._snapshot_collection(data_dir, RuleEvidence), before_evidence)
            self.assertEqual(self._snapshot_collection(data_dir, DecisionRequest), before_decisions)
            self.assertEqual(JsonRepository(data_dir, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(data_dir, PublishTask).list_all(), [])
            json.dumps(output["result"]["machine_summary"], ensure_ascii=False)
            self.assertEqual(set(output["result"]["machine_summary"]["topic_ids"]), {topic.id for topic in topics})

    def test_generate_topics_supports_creator_alias_and_benchmark_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--creator-id",
                    "creator-main",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                    "--reference-id",
                    "benchmark-post-001",
                    "--topic-count",
                    "1",
                ]
            )

            topic = JsonRepository(data_dir, TopicItem).read(output["result"]["topic_ids"][0])
            self.assertTrue(output["ok"])
            self.assertEqual(topic.reference_posts, ["benchmark-post-001"])

    def test_generate_topics_with_explicit_active_asset_writes_asset_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)
            asset = self._seed_content_asset(data_dir, "asset-active-reference", status="active", version=2)
            before_asset = JsonRepository(data_dir, ContentAsset).read(asset.id).to_dict()

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-id",
                    asset.id,
                    "--topic-count",
                    "1",
                ]
            )

            topic = JsonRepository(data_dir, TopicItem).read(output["result"]["topic_ids"][0])
            self.assertEqual(topic.reference_assets[0]["asset_id"], asset.id)
            self.assertEqual(topic.reference_assets[0]["asset_version"], 2)
            self.assertEqual(output["result"]["machine_summary"]["reference_asset_ids"], [asset.id])
            self.assertEqual(JsonRepository(data_dir, ContentAsset).read(asset.id).to_dict(), before_asset)

    def test_generate_topics_rejects_non_active_or_missing_asset_without_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)
            candidate = self._seed_content_asset(data_dir, "asset-candidate-reference", status="candidate")

            non_active = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-id",
                    candidate.id,
                ],
                expected_code=1,
            )
            missing = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-id",
                    "missing-asset",
                ],
                expected_code=1,
            )

            self.assertIn("active", non_active["error"])
            self.assertIn("not found", missing["error"])
            self.assertEqual(JsonRepository(data_dir, TopicItem).list_all(), [])

    def test_generate_topics_rejects_asset_version_mismatch_without_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)
            asset = self._seed_content_asset(data_dir, "asset-versioned-reference", status="active", version=2)

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-id",
                    asset.id,
                    "--asset-version",
                    "1",
                ],
                expected_code=1,
            )

            self.assertIn("版本", output["error"])
            self.assertEqual(JsonRepository(data_dir, TopicItem).list_all(), [])

    def test_generate_topics_rejects_asset_version_without_asset_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-version",
                    "1",
                ],
                expected_code=1,
            )

            self.assertIn("asset-id", output["error"])
            self.assertEqual(JsonRepository(data_dir, TopicItem).list_all(), [])

    def test_generate_topics_rejects_asset_profile_mismatch_without_topics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-approved", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)
            asset = self._seed_content_asset(
                data_dir,
                "asset-other-profile-reference",
                status="active",
                creator_profile_id="creator-other",
            )

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--asset-id",
                    asset.id,
                ],
                expected_code=1,
            )

            self.assertIn("账号", output["error"])
            self.assertEqual(JsonRepository(data_dir, TopicItem).list_all(), [])

    def test_generate_topics_rejects_profile_conflict_missing_profile_and_no_usable_rules_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)

            conflict = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--creator-id",
                    "creator-other",
                ],
                expected_code=1,
            )
            missing = self._run_cli(
                ["generate-topics", "--workspace", temp_dir, "--profile-id", "missing-profile"],
                expected_code=1,
            )
            no_rules = self._run_cli(
                ["generate-topics", "--workspace", temp_dir, "--profile-id", "creator-main"],
                expected_code=1,
            )

            self.assertIn("profile-id 和 creator-id 必须一致", conflict["error"])
            self.assertIn("not found", missing["error"])
            self.assertIn("没有可用规则", no_rules["error"])
            self.assertEqual(JsonRepository(data_dir, TopicItem).list_all(), [])

    def test_generate_topics_user_summary_hides_internal_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            approved = self._seed_rule(data_dir, "rule-secret-topic", status="approved")
            self._seed_rule_generation_support(data_dir, approved.id)

            output = self._run_cli(
                [
                    "generate-topics",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--topic-count",
                    "1",
                ]
            )

            summary = output["result"]["user_summary"]
            for text in (
                "creator-main",
                approved.id,
                output["result"]["topic_ids"][0],
                "TopicItem",
                "RuleCard",
                "GenerationContext",
                "approved",
                "testing",
                "validated",
                "candidate",
                "ready",
                "limited",
                ".py",
                ".json",
                "/Users/",
            ):
                self.assertNotIn(text, summary)

    def test_show_generation_context_returns_safe_read_only_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            JsonRepository(data_dir, CreatorProfile).create(
                CreatorProfile(
                    id="creator-secondary",
                    name="第二账号",
                    platform="小红书",
                    positioning="另一个定位",
                    target_audience=["另一类用户"],
                    content_style=["具体"],
                    forbidden_expressions=["虚假承诺"],
                    goals=["建立信任"],
                    content_formats=["图文"],
                    publish_frequency="每周 1 篇",
                    notes="不应被自动选中。",
                )
            )
            approved = self._seed_rule(data_dir, "rule-approved-context", status="approved", summary="标题点名职场新人")
            candidate = self._seed_rule(data_dir, "rule-candidate-context", status="candidate", summary="候选规则")
            JsonRepository(data_dir, RuleEvidence).create(
                RuleEvidence(
                    id="evidence-approved-context",
                    rule_id=approved.id,
                    source_type="benchmark_analysis",
                    source_id="analysis-001",
                    source_fragment="标题",
                    evidence_type="title",
                    observable_fact="标题点名职场新人。",
                    inference="用于支持规则。",
                )
            )
            JsonRepository(data_dir, ProvenanceRecord).create(
                ProvenanceRecord(
                    id="provenance-approved-context",
                    target_object_type="rule_card",
                    target_object_id=approved.id,
                    source_object_type="creator_profile",
                    source_object_id="creator-main",
                    source_version=1,
                    actor="codex",
                    artifact_nature="recommendation",
                    method="test",
                    note="账号档案来源。",
                )
            )
            JsonRepository(data_dir, DecisionRequest).create(
                DecisionRequest(
                    id="decision-approved-context",
                    target_object_type="rule_card",
                    target_object_id=approved.id,
                    question="是否采用？",
                    options=["确认使用", "暂不使用"],
                    option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
                    recommendation="确认使用",
                    recommendation_reason="测试。",
                    impact="测试。",
                    status="confirmed",
                    selected_option="确认使用",
                    resolved_at="2026-07-11T00:00:00Z",
                    resolved_by="user",
                )
            )
            before = self._snapshot_workspace(data_dir)

            output = self._run_cli(
                [
                    "show-generation-context",
                    "--workspace",
                    temp_dir,
                    "--profile-id",
                    "creator-main",
                    "--intent",
                    " 准备后续选题 ",
                    "--content-type",
                    "图文",
                    "--target-audience",
                    "职场新人",
                    "--target-audience",
                    "职场新人",
                    "--format",
                    "清单",
                    "--tone",
                    "直接",
                    "--do",
                    "给步骤",
                    "--dont",
                    "夸大效果",
                    "--reference-id",
                    "ref-1",
                    "--reference-id",
                    "ref-1",
                ]
            )

            result = output["result"]
            self.assertTrue(output["ok"])
            self.assertEqual(result["profile_id"], "creator-main")
            self.assertEqual(result["usable_rule_count"], 1)
            self.assertEqual(result["excluded_rule_count"], 1)
            self.assertEqual(result["machine_summary"]["usable_rule_ids"], [approved.id])
            self.assertEqual(result["machine_summary"]["excluded_rule_ids"], [candidate.id])
            self.assertEqual(result["machine_summary"]["task_constraints"]["target_audiences"], ["职场新人"])
            self.assertEqual(result["machine_summary"]["task_constraints"]["reference_ids"], ["ref-1"])
            self.assertIn("主账号", result["user_summary"])
            self.assertIn("候选规则：尚未经过用户确认", result["user_summary"])
            self.assertNotIn("creator-main", result["user_summary"])
            self.assertNotIn(approved.id, result["user_summary"])
            self.assertNotIn("approved", result["user_summary"])
            json.dumps(result["machine_summary"], ensure_ascii=False)
            self.assertEqual(self._snapshot_workspace(data_dir), before)

    def test_show_generation_context_missing_profile_fails_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            before = self._snapshot_workspace(data_dir)

            output = self._run_cli(
                ["show-generation-context", "--workspace", temp_dir, "--profile-id", "missing-profile"],
                expected_code=1,
            )

            self.assertFalse(output["ok"])
            self.assertIn("not found", output["error"])
            self.assertEqual(self._snapshot_workspace(data_dir), before)

    def test_generate_draft_uses_topic_audit_chain_and_writes_one_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            topic = self._seed_audited_topic(data_dir)
            for model in (RuleCard, RuleEvidence, DecisionRequest, TopicItem, PublishTask):
                self.assertEqual(len(JsonRepository(data_dir, model).list_all()), 1 if model is TopicItem else 0)
            before_protected = {
                model.collection_name: self._snapshot_collection(data_dir, model)
                for model in (RuleCard, RuleEvidence, DecisionRequest, TopicItem, PublishTask)
            }

            output = self._run_cli(["generate-draft", "--workspace", temp_dir, "--topic-id", topic.id])

            drafts = JsonRepository(data_dir, ContentDraft).list_all()
            self.assertTrue(output["ok"])
            self.assertEqual(len(drafts), 1)
            draft = drafts[0]
            self.assertEqual(draft.topic_id, topic.id)
            self.assertEqual(draft.source_profile_id, topic.source_profile_id)
            self.assertEqual(draft.source_profile_version, topic.source_profile_version)
            self.assertEqual(draft.source_rule_cards, topic.source_rule_cards)
            self.assertEqual(draft.generation_context_status, topic.generation_context_status)
            self.assertEqual(draft.task_constraints, topic.task_constraints)
            self.assertEqual(draft.risk_warnings, topic.risk_warnings)
            self.assertEqual(draft.missing_information, topic.missing_information)
            self.assertIn("diagnosis", output["result"]["machine_summary"])
            self.assertEqual(output["result"]["machine_summary"]["draft_id"], draft.id)
            self.assertEqual(output["result"]["machine_summary"]["topic_id"], topic.id)
            self.assertIn("已生成 1 个草稿", output["result"]["user_summary"])
            for forbidden in ("creator-main", topic.id, draft.id, "rule-a", "ready", "limited", "ContentDraft", ".json", "/Users/"):
                self.assertNotIn(forbidden, output["result"]["user_summary"])
            self.assertEqual(JsonRepository(data_dir, PublishTask).list_all(), [])
            self.assertEqual(
                {
                    model.collection_name: self._snapshot_collection(data_dir, model)
                    for model in (RuleCard, RuleEvidence, DecisionRequest, TopicItem, PublishTask)
                },
                before_protected,
            )

    def test_generate_draft_with_explicit_active_asset_writes_asset_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            topic = self._seed_audited_topic(data_dir)
            asset = self._seed_content_asset(data_dir, "asset-draft-reference", status="active", version=2)
            before_asset = JsonRepository(data_dir, ContentAsset).read(asset.id).to_dict()

            output = self._run_cli(
                [
                    "generate-draft",
                    "--workspace",
                    temp_dir,
                    "--topic-id",
                    topic.id,
                    "--asset-id",
                    asset.id,
                ]
            )

            draft = JsonRepository(data_dir, ContentDraft).read(output["result"]["draft_id"])
            self.assertEqual(draft.reference_assets[0]["asset_id"], asset.id)
            self.assertEqual(draft.reference_assets[0]["asset_version"], 2)
            self.assertEqual(output["result"]["machine_summary"]["reference_asset_ids"], [asset.id])
            self.assertEqual(JsonRepository(data_dir, ContentAsset).read(asset.id).to_dict(), before_asset)

    def test_generate_draft_rejects_conflicting_explicit_and_inherited_asset_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            inherited = self._seed_content_asset(data_dir, "asset-inherited-reference", status="active", version=2)
            explicit = self._seed_content_asset(data_dir, "asset-explicit-reference", status="active", version=2)
            topic = self._seed_audited_topic(data_dir, reference_assets=[asset_reference_snapshot(inherited)])

            output = self._run_cli(
                [
                    "generate-draft",
                    "--workspace",
                    temp_dir,
                    "--topic-id",
                    topic.id,
                    "--asset-id",
                    explicit.id,
                ],
                expected_code=1,
            )

            self.assertIn("资产", output["error"])
            self.assertEqual(JsonRepository(data_dir, ContentDraft).list_all(), [])

    def test_generate_draft_allows_same_explicit_and_inherited_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            asset = self._seed_content_asset(data_dir, "asset-same-reference", status="active", version=2)
            topic = self._seed_audited_topic(data_dir, reference_assets=[asset_reference_snapshot(asset)])

            output = self._run_cli(
                [
                    "generate-draft",
                    "--workspace",
                    temp_dir,
                    "--topic-id",
                    topic.id,
                    "--asset-id",
                    asset.id,
                    "--asset-version",
                    "2",
                ]
            )

            draft = JsonRepository(data_dir, ContentDraft).read(output["result"]["draft_id"])
            self.assertEqual(draft.reference_assets[0]["asset_id"], asset.id)
            self.assertEqual(draft.reference_assets[0]["asset_version"], 2)

    def test_generate_draft_missing_topic_fails_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)

            output = self._run_cli(["generate-draft", "--workspace", temp_dir, "--topic-id", "missing-topic"], expected_code=1)

            self.assertFalse(output["ok"])
            self.assertEqual(JsonRepository(data_dir, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(data_dir, PublishTask).list_all(), [])

    def test_revise_draft_creates_new_draft_without_overwriting_original(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            topic = self._seed_audited_topic(data_dir)
            generated = self._run_cli(["generate-draft", "--workspace", temp_dir, "--topic-id", topic.id])
            original = JsonRepository(data_dir, ContentDraft).read(generated["result"]["draft_id"])
            before_original = original.to_dict()
            before_topic = self._snapshot_collection(data_dir, TopicItem)
            before_rules = self._snapshot_collection(data_dir, RuleCard)

            output = self._run_cli(
                ["revise-draft", "--workspace", temp_dir, "--draft-id", original.id, "--focus", "开头更直接"]
            )

            drafts = JsonRepository(data_dir, ContentDraft).list_all()
            self.assertTrue(output["ok"])
            self.assertEqual(len(drafts), 2)
            revised = JsonRepository(data_dir, ContentDraft).read(output["result"]["draft_id"])
            self.assertEqual(revised.parent_draft_id, original.id)
            self.assertEqual(revised.revision_focus, "开头更直接")
            self.assertEqual(revised.topic_id, original.topic_id)
            self.assertEqual(revised.source_profile_id, original.source_profile_id)
            self.assertEqual(revised.source_rule_cards, original.source_rule_cards)
            self.assertEqual(JsonRepository(data_dir, ContentDraft).read(original.id).to_dict(), before_original)
            self.assertEqual(self._snapshot_collection(data_dir, TopicItem), before_topic)
            self.assertEqual(self._snapshot_collection(data_dir, RuleCard), before_rules)
            self.assertEqual(JsonRepository(data_dir, PublishTask).list_all(), [])
            self.assertIn("已生成 1 个修订草稿", output["result"]["user_summary"])
            self.assertEqual(output["result"]["machine_summary"]["parent_draft_id"], original.id)
            self.assertEqual(output["result"]["machine_summary"]["revision_focus"], "开头更直接")
            for forbidden in (original.id, revised.id, "rule-a", "ContentDraft", "ready", "limited", ".json", "/Users/"):
                self.assertNotIn(forbidden, output["result"]["user_summary"])

    def test_revise_draft_missing_or_empty_focus_fails_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            topic = self._seed_audited_topic(data_dir)
            generated = self._run_cli(["generate-draft", "--workspace", temp_dir, "--topic-id", topic.id])
            before = self._snapshot_collection(data_dir, ContentDraft)

            missing = self._run_cli(
                ["revise-draft", "--workspace", temp_dir, "--draft-id", "missing-draft", "--focus", "开头更直接"],
                expected_code=1,
            )
            empty = self._run_cli(
                ["revise-draft", "--workspace", temp_dir, "--draft-id", generated["result"]["draft_id"], "--focus", "   "],
                expected_code=1,
            )

            self.assertFalse(missing["ok"])
            self.assertFalse(empty["ok"])
            self.assertEqual(self._snapshot_collection(data_dir, ContentDraft), before)
            self.assertEqual(JsonRepository(data_dir, PublishTask).list_all(), [])

    def test_review_own_post_passes_only_active_rules_to_prompt(self) -> None:
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
                    tags=[],
                    source_topic_id="topic-001",
                )
            )
            for status in ("candidate", "approved", "testing", "validated", "rejected", "deprecated"):
                self._seed_rule(data_dir, f"rule-{status}", status=status)
            prompt_service = RecordingPromptService()

            with patch("app.cli.main.build_prompt_service", return_value=prompt_service):
                output = self._run_cli(["review-own-post", "--workspace", temp_dir, "--own-post-id", "own-post-001"])

            payload = prompt_service.payloads["review_own_post"][0]
            self.assertTrue(output["ok"])
            self.assertEqual(
                [rule["id"] for rule in payload["related_rule_cards"]],
                ["rule-approved", "rule-testing", "rule-validated"],
            )

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
            self._run_cli(["approve-rule", "--workspace", temp_dir, "--rule-id", rules["result"]["rule_card_ids"][0]])
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
                    topics["result"]["topic_ids"][0],
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
            saved_draft = JsonRepository(data_dir, ContentDraft).read(draft["result"]["draft_id"])
            self.assertEqual(saved_draft.topic_id, topics["result"]["topic_ids"][0])
            self.assertEqual(publish["result"]["publish_task_id"], f"publish-task-from-{draft['result']['draft_id']}")
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

    def test_capture_xhs_link_returns_reusable_outcome_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_file = Path(temp_dir) / "manual-capture.json"
            manual_file.write_text(
                json.dumps(
                    {
                        "title": "可见标题",
                        "body": "可见正文",
                        "content_type": "image",
                        "metrics": {"likes": None, "collects": None, "comments": None, "shares": None},
                        "images": [{"path": "screenshot.png"}],
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
                    "学习结构",
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

            self.assertIn("capture_status", capture["result"])
            outcome = capture["result"]["outcome"]
            self.assertEqual(outcome["status_category"], "partial")
            self.assertIn("标题", outcome["available_content"])
            self.assertIn("互动数据", outcome["missing_content"])
            self.assertIn("下一步", outcome["user_summary"])

    def test_capture_xhs_link_invalid_manual_file_returns_plain_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_file = Path(temp_dir) / "manual-capture.json"
            manual_file.write_text("[]", encoding="utf-8")
            inbox = self._run_cli(
                [
                    "add-inbox-item",
                    "--workspace",
                    temp_dir,
                    "--url",
                    "https://www.xiaohongshu.com/explore/test-note",
                    "--user-intent",
                    "学习结构",
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
                ],
                expected_code=1,
            )

            self.assertFalse(capture["ok"])
            outcome = capture["outcome"]
            self.assertEqual(outcome["status_category"], "failed")
            self.assertIn("复制标题和正文", outcome["recommended_action"])
            self.assertNotIn("JSON", outcome["user_summary"])

    def test_capture_xhs_link_missing_inbox_with_manual_file_is_not_manual_file_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_file = Path(temp_dir) / "manual-capture.json"
            manual_file.write_text(
                json.dumps({"title": "可见标题", "body": "可见正文"}, ensure_ascii=False),
                encoding="utf-8",
            )

            capture = self._run_cli(
                [
                    "capture-xhs-link",
                    "--workspace",
                    temp_dir,
                    "--inbox-item-id",
                    "missing-inbox",
                    "--manual-file",
                    str(manual_file),
                ],
                expected_code=1,
            )

            self.assertFalse(capture["ok"])
            outcome = capture["outcome"]
            self.assertNotEqual(outcome["technical_details"]["error_code"], "manual_file_invalid")
            self.assertNotIn("重新提供一份可读取的手动内容", outcome["recommended_action"])

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
            outcome = output["result"]["analysis_outcome"]
            self.assertEqual(outcome["status_category"], "complete")
            self.assertIn("【客观数据】", outcome["user_summary"])
            self.assertIn("【Codex 判断】", outcome["user_summary"])
            self.assertIn("【信息不足】", outcome["user_summary"])
            self.assertNotIn(output["result"]["candidate_rule_ids"][0], outcome["user_summary"])
            self.assertNotIn("account_fit", outcome["user_summary"])
            item = JsonRepository(data_dir, ContentInboxItem).read(inbox_item.id)
            self.assertEqual(item.status, "analyzed")

    def test_analyze_captured_post_uses_video_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            _, capture = self._seed_capture(data_dir, content_type="video")

            output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["analysis_template"], "video_tutorial")
            summary = output["result"]["analysis_outcome"]["user_summary"]
            self.assertIn("没有视频帧或字幕", summary)
            self.assertNotIn("前 3 秒", summary)
            self.assertNotIn("音乐", summary)

    def test_assess_account_fit_updates_only_existing_analysis_and_can_be_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            JsonRepository(data_dir, CreatorProfile).create(
                CreatorProfile(
                    id="creator-secondary",
                    name="第二账号",
                    platform="小红书",
                    positioning="另一个定位",
                    target_audience=["另一类用户"],
                    content_style=["具体"],
                    forbidden_expressions=[],
                    goals=["建立信任"],
                    content_formats=["图文"],
                    publish_frequency="每周 1 次",
                    notes="用于验证显式选择。",
                )
            )
            inbox_item, capture = self._seed_capture(data_dir, content_type="image")
            analysis_output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])
            protected_collections = (
                CreatorProfile,
                RuleCard,
                RuleEvidence,
                DecisionRequest,
                BenchmarkPost,
                TopicItem,
                ContentDraft,
            )
            before_counts = {model.collection_name: len(JsonRepository(data_dir, model).list_all()) for model in protected_collections}

            output = self._run_cli(
                [
                    "assess-account-fit",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    analysis_output["result"]["analysis_id"],
                    "--creator-id",
                    "creator-main",
                ]
            )
            repeated = self._run_cli(
                [
                    "assess-account-fit",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    analysis_output["result"]["analysis_id"],
                    "--creator-id",
                    "creator-main",
                ]
            )

            self.assertTrue(output["ok"])
            self.assertIn("account_fit_summary", output["result"])
            self.assertIn("【与你账号的匹配判断】", output["result"]["account_fit_summary"])
            self.assertEqual(output["result"]["account_fit"]["source_profile_id"], "creator-main")
            self.assertEqual(repeated["result"]["analysis_id"], analysis_output["result"]["analysis_id"])
            self.assertEqual(before_counts, {model.collection_name: len(JsonRepository(data_dir, model).list_all()) for model in protected_collections})
            self.assertEqual(JsonRepository(data_dir, ContentInboxItem).read(inbox_item.id).status, "analyzed")
            self.assertEqual(JsonRepository(data_dir, CaptureRecord).read(capture.id).title, capture.title)
            self.assertEqual(len(JsonRepository(data_dir, BenchmarkAnalysis).list_all()), 1)

    def test_assess_account_fit_rejects_analysis_with_missing_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            JsonRepository(data_dir, BenchmarkAnalysis).create(
                BenchmarkAnalysis(id="analysis-missing-capture", capture_id="capture-missing")
            )

            output = self._run_cli(
                [
                    "assess-account-fit",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    "analysis-missing-capture",
                    "--creator-id",
                    "creator-main",
                ],
                expected_code=1,
            )

            self.assertFalse(output["ok"])
            self.assertEqual(JsonRepository(data_dir, BenchmarkAnalysis).read("analysis-missing-capture").account_fit, {})

    def test_assess_account_fit_rejects_missing_analysis_or_profile_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            _, capture = self._seed_capture(data_dir, content_type="image")
            analysis_output = self._run_cli(["analyze-captured-post", "--workspace", temp_dir, "--capture-id", capture.id])
            before_profile_count = len(JsonRepository(data_dir, CreatorProfile).list_all())

            missing_analysis = self._run_cli(
                [
                    "assess-account-fit",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    "missing-analysis",
                    "--creator-id",
                    "creator-main",
                ],
                expected_code=1,
            )
            missing_profile = self._run_cli(
                [
                    "assess-account-fit",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    analysis_output["result"]["analysis_id"],
                    "--creator-id",
                    "missing-creator",
                ],
                expected_code=1,
            )

            self.assertFalse(missing_analysis["ok"])
            self.assertFalse(missing_profile["ok"])
            self.assertEqual(len(JsonRepository(data_dir, CreatorProfile).list_all()), before_profile_count)
            self.assertEqual(JsonRepository(data_dir, BenchmarkAnalysis).read(analysis_output["result"]["analysis_id"]).account_fit, {"observable": {}, "inference": "PR-3A 不判断账号适配。"})

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
            self.assertEqual(rule.created_by, "codex")
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

    def test_propose_candidate_rules_creates_only_candidate_artifacts_with_safe_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            profile = CreatorProfile(
                id="creator-proposal",
                name="主账号",
                positioning="帮助职场新人提升表达能力",
                target_audience=["职场新人"],
                content_style=["具体"],
                forbidden_expressions=[],
                goals=["建立信任"],
                content_formats=["图文"],
                publish_frequency="每周 3 次",
                notes="测试账号。",
            )
            capture = CaptureRecord(
                id="capture-proposal-cli",
                inbox_item_id="inbox-proposal-cli",
                source_url="https://example.test/proposal",
                capture_status="success",
                title="职场新人如何准备第一次工作汇报",
                body="先说明汇报对象，再给出三个当天可完成的准备步骤。",
                content_type="image",
                metrics={},
            )
            analysis = BenchmarkAnalysis(
                id="analysis-proposal-cli",
                capture_id=capture.id,
                title_analysis={"observable": capture.title, "inference": "标题明确说明适用对象和问题。"},
            )
            analysis.account_fit = {
                "status_category": "complete",
                "source_profile_id": profile.id,
                "source_profile_version": profile.version,
                "assessments": [
                    {
                        "element": "标题",
                        "classification": "directly_borrowable",
                        "post_evidence": [capture.title],
                        "profile_evidence": ["目标受众明确包含：职场新人"],
                        "reason": "目标受众明确出现：职场新人",
                        "adaptation_guidance": "保留已验证的方法，用自己的内容重新表达。",
                    }
                ],
            }
            JsonRepository(data_dir, CreatorProfile).create(profile)
            JsonRepository(data_dir, CaptureRecord).create(capture)
            JsonRepository(data_dir, BenchmarkAnalysis).create(analysis)
            proposal_file = data_dir / "proposals.json"
            proposal_file.write_text(
                json.dumps(
                    {
                        "proposals": [
                            {
                                "rule_text": "标题先明确具体目标人群，再说明需要解决的问题。",
                                "rule_type": "title",
                                "scope": ["职场新人内容", "标题"],
                                "applicable_when": ["内容面向明确的职场新人群体"],
                                "not_applicable_when": ["内容没有明确目标人群"],
                                "evidence": [{"dimension": "标题", "observable_fact": capture.title}],
                                "account_fit_basis": ["目标受众明确出现：职场新人"],
                                "limitations": ["单篇帖子证据，仍需更多样本验证"],
                                "risk_notes": [],
                                "confidence": "low",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = self._run_cli(
                [
                    "propose-candidate-rules",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    analysis.id,
                    "--creator-id",
                    profile.id,
                    "--proposals-file",
                    str(proposal_file),
                ]
            )

            self.assertTrue(output["ok"])
            self.assertEqual(output["result"]["created_count"], 1)
            self.assertEqual(len(JsonRepository(data_dir, RuleCard).list_all()), 1)
            self.assertEqual(len(JsonRepository(data_dir, RuleEvidence).list_all()), 1)
            self.assertEqual(len(JsonRepository(data_dir, ProvenanceRecord).list_all()), 2)
            self.assertEqual(len(JsonRepository(data_dir, DecisionRequest).list_all()), 0)
            self.assertEqual(JsonRepository(data_dir, BenchmarkAnalysis).read(analysis.id).candidate_rule_ids, [])
            self.assertIn("待确认", output["result"]["candidate_rule_summary"])
            self.assertNotIn("rule-", output["result"]["candidate_rule_summary"])

    def test_propose_candidate_rules_hides_missing_proposal_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_file = Path(temp_dir) / "missing-proposals.json"

            output = self._run_cli(
                [
                    "propose-candidate-rules",
                    "--workspace",
                    temp_dir,
                    "--analysis-id",
                    "analysis-missing",
                    "--creator-id",
                    "creator-missing",
                    "--proposals-file",
                    str(missing_file),
                ],
                expected_code=1,
            )

            self.assertIn("无法读取结构化规则提案", output["error"])
            self.assertNotIn(str(missing_file), output["error"])

    def test_propose_rule_from_mechanism_creates_candidate_artifacts_without_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            mechanism = ContentMechanism(
                id="mechanism-cli-rule",
                name="复杂工具结果化表达",
                description="把复杂工具能力先翻译成用户能感知的运营结果。",
                status="candidate",
                confidence_level="medium",
                confidence=0.6,
                source_refs=[{"source_type": "external_analysis", "source_id": "external-001"}],
                evidence_summary={
                    "observed_facts": [
                        "标题包含 Codex、Obsidian、10min 和爆款工作流",
                        "封面展示工具图标、流程图和结果承诺",
                    ],
                    "inferences": ["工具被包装成内容运营结果"],
                    "missing_information": ["未获取评论区"],
                    "limitations": ["不能确认长期表现"],
                },
                problem="复杂工具内容容易只剩工具名。",
                solution="先讲用户任务，再解释工具。",
                applicable_scope=["AI 内容运营"],
                limitations=["不能夸大时间承诺"],
            )
            profile = CreatorProfile(
                id="creator-mechanism-rule",
                name="主账号",
                positioning="帮助创作者用 AI 做内容运营判断，而不是单纯工具教学。",
                target_audience=["内容创作者"],
                content_style=["真实", "克制"],
                forbidden_expressions=[],
                goals=["提升内容运营效率"],
                content_formats=["图文"],
                publish_frequency="每周 3 次",
                notes="测试账号。",
            )
            JsonRepository(workspace, ContentMechanism).create(mechanism)
            JsonRepository(workspace, CreatorProfile).create(profile)
            proposal_file = workspace / "mechanism-rule.json"
            proposal_file.write_text(
                json.dumps(
                    {
                        "rule_statement": "讲 AI 工具时，优先表达用户能够完成的内容运营任务，而不是先堆叠工具功能。",
                        "rule_type": "topic",
                        "applicable_scope": ["AI 内容运营"],
                        "exclusions": ["纯开发者技术教程"],
                        "selected_observed_facts": [
                            "标题包含 Codex、Obsidian、10min 和爆款工作流",
                            "封面展示工具图标、流程图和结果承诺",
                        ],
                        "account_fit_reason": "当前账号定位强调 AI 内容运营判断，而不是单纯工具教学。",
                        "limitations": ["不能夸大时间承诺"],
                        "confidence_level": "high",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(
                [
                    "propose-rule-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    mechanism.id,
                    "--creator-id",
                    profile.id,
                    "--file",
                    str(proposal_file),
                ]
            )

            self.assertTrue(output["ok"])
            result = output["result"]
            self.assertEqual(result["created_count"], 1)
            self.assertFalse(result["machine_summary"]["decision_request_created"])
            self.assertIn("尚未生效", result["user_summary"])
            self.assertIn("发起用户确认", result["user_summary"])
            for forbidden in ("RuleCard", "content_mechanism", "candidate", ".json", temp_dir, mechanism.id):
                self.assertNotIn(forbidden, result["user_summary"])
            rules = JsonRepository(workspace, RuleCard).list_all()
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].status, "candidate")
            self.assertEqual(len(JsonRepository(workspace, RuleEvidence).list_all()), 2)
            self.assertEqual(len(JsonRepository(workspace, ProvenanceRecord).list_all()), 2)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, TopicItem).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(workspace, PublishTask).list_all(), [])
            after = self._snapshot_workspace(workspace)
            changed = sorted(set(after) - set(before))
            self.assertEqual(
                changed,
                sorted(
                    [
                        f"rule-cards/{rules[0].id}.json",
                        f"rule-evidence/{result['machine_summary']['rule_evidence_ids'][0]}.json",
                        f"rule-evidence/{result['machine_summary']['rule_evidence_ids'][1]}.json",
                        f"provenance-records/{result['machine_summary']['provenance_ids'][0]}.json",
                        f"provenance-records/{result['machine_summary']['provenance_ids'][1]}.json",
                    ]
                ),
            )

    def test_propose_rule_from_mechanism_failures_write_nothing_and_hide_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "missing-workspace"
            proposal_file = Path(temp_dir) / "bad-mechanism-rule.json"
            proposal_file.write_text("{bad json", encoding="utf-8")

            output = self._run_cli(
                [
                    "propose-rule-from-mechanism",
                    "--workspace",
                    str(workspace),
                    "--mechanism-id",
                    "mechanism-missing",
                    "--creator-id",
                    "creator-missing",
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertFalse(output["ok"])
            self.assertIn("无法读取结构化机制规则提案", output["error"])
            self.assertNotIn(str(proposal_file), output["error"])
            self.assertFalse(workspace.exists())

    def test_propose_asset_from_mechanism_creates_candidate_asset_without_generation_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            mechanism = ContentMechanism(
                id="mechanism-cli-asset",
                name="结果前置表达机制",
                description="先呈现用户可获得的内容运营结果，再解释工具和过程。",
                status="candidate",
                confidence_level="medium",
                confidence=0.6,
                source_refs=[{"source_type": "external_analysis", "source_id": "external-001"}],
                evidence_summary={
                    "observed_facts": [
                        "标题先展示结果承诺，再说明使用的工具和流程",
                        "正文先写用户能完成的内容运营任务",
                    ],
                    "inferences": ["内容把复杂工具包装成结果"],
                    "missing_information": ["未获取评论区"],
                    "limitations": ["不能确认长期表现"],
                },
                problem="复杂工具内容容易只剩工具名。",
                solution="先讲结果，再解释工具。",
                applicable_scope=["AI 内容运营"],
                limitations=["不能夸大时间承诺"],
            )
            profile = CreatorProfile(
                id="creator-mechanism-asset",
                name="主账号",
                positioning="帮助创作者用 AI 做内容运营判断。",
                target_audience=["内容创作者"],
                content_style=["真实", "克制"],
                forbidden_expressions=[],
                goals=["提升内容运营效率"],
                content_formats=["图文"],
                publish_frequency="每周 3 次",
                notes="测试账号。",
            )
            JsonRepository(workspace, ContentMechanism).create(mechanism)
            JsonRepository(workspace, CreatorProfile).create(profile)
            proposal_file = workspace / "mechanism-asset.json"
            proposal_file.write_text(
                json.dumps(
                    {
                        "asset_type": "opening_template",
                        "name": "任务结果优先开场",
                        "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
                        "template": "先说明你可以完成的结果：{{result}}。\n再说明实现过程：{{process}}。",
                        "variables": ["result", "process"],
                        "applicable_scope": ["AI 内容运营", "工作流介绍"],
                        "exclusions": ["纯工具安装教程"],
                        "usage_notes": ["先填具体结果，再填过程证据。"],
                        "limitations": ["结果描述必须可验证"],
                        "examples": ["先说明完成选题库，再说明工具流程。"],
                        "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
                        "account_fit_reason": "提案认为这适合当前账号的 AI 内容运营判断定位。",
                        "confidence_level": "medium",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(
                [
                    "propose-asset-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    mechanism.id,
                    "--creator-id",
                    profile.id,
                    "--file",
                    str(proposal_file),
                ]
            )

            self.assertTrue(output["ok"])
            result = output["result"]
            self.assertEqual(result["created_count"], 1)
            self.assertFalse(result["machine_summary"]["generation_context_connected"])
            self.assertFalse(result["machine_summary"]["decision_request_created"])
            self.assertIn("候选内容资产", result["user_summary"])
            self.assertIn("尚未进入内容生成", result["user_summary"])
            for forbidden in ("ContentAsset", "content-assets", "candidate", ".json", temp_dir, mechanism.id):
                self.assertNotIn(forbidden, result["user_summary"])
            assets = JsonRepository(workspace, ContentAsset).list_all()
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].status, "candidate")
            self.assertEqual(len(JsonRepository(workspace, ContentAssetEvidence).list_all()), 1)
            self.assertEqual(len(JsonRepository(workspace, ProvenanceRecord).list_all()), 2)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, RuleCard).list_all(), [])
            self.assertEqual(JsonRepository(workspace, RuleEvidence).list_all(), [])
            self.assertEqual(JsonRepository(workspace, TopicItem).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(workspace, PublishTask).list_all(), [])
            after = self._snapshot_workspace(workspace)
            changed = sorted(set(after) - set(before))
            self.assertEqual(
                changed,
                sorted(
                    [
                        f"content-assets/{assets[0].id}.json",
                        f"content-asset-evidence/{result['machine_summary']['evidence_ids'][0]}.json",
                        f"provenance-records/{result['machine_summary']['provenance_ids'][0]}.json",
                        f"provenance-records/{result['machine_summary']['provenance_ids'][1]}.json",
                    ]
                ),
            )

    def test_propose_asset_from_mechanism_failures_write_nothing_and_hide_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "missing-workspace"
            proposal_file = Path(temp_dir) / "bad-mechanism-asset.json"
            proposal_file.write_text("{bad json", encoding="utf-8")

            output = self._run_cli(
                [
                    "propose-asset-from-mechanism",
                    "--workspace",
                    str(workspace),
                    "--mechanism-id",
                    "mechanism-missing",
                    "--creator-id",
                    "creator-missing",
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertFalse(output["ok"])
            self.assertIn("无法读取结构化机制资产提案", output["error"])
            self.assertNotIn(str(proposal_file), output["error"])
            self.assertFalse(workspace.exists())

    def test_propose_asset_from_mechanism_missing_records_and_duplicates_write_no_business_objects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            proposal = {
                "asset_type": "opening_template",
                "name": "任务结果优先开场",
                "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
                "template": "结果：{{result}}\n过程：{{process}}",
                "variables": ["result", "process"],
                "applicable_scope": ["AI 内容运营"],
                "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
                "account_fit_reason": "提案认为这适合当前账号定位。",
                "limitations": [],
            }
            proposal_file = workspace / "mechanism-asset.json"
            proposal_file.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")
            before = self._snapshot_workspace(workspace)

            missing = self._run_cli(
                [
                    "propose-asset-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    "mechanism-missing",
                    "--creator-id",
                    "creator-missing",
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertIn("未找到指定内容机制或账号档案", missing["error"])
            self.assertEqual(set(self._snapshot_workspace(workspace)) - set(before), set())

            mechanism = ContentMechanism(
                id="mechanism-cli-asset-duplicate",
                name="结果前置表达机制",
                description="先呈现用户可获得的内容运营结果，再解释工具和过程。",
                status="candidate",
                confidence_level="medium",
                confidence=0.6,
                evidence_summary={"observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"]},
                problem="复杂工具内容容易只剩工具名。",
                solution="先讲结果，再解释工具。",
                applicable_scope=["AI 内容运营"],
                limitations=[],
            )
            profile = CreatorProfile(
                id="creator-cli-asset-duplicate",
                name="主账号",
                positioning="帮助创作者用 AI 做内容运营判断。",
                target_audience=["内容创作者"],
                content_style=["真实"],
                forbidden_expressions=[],
                goals=["提升内容运营效率"],
                content_formats=["图文"],
                publish_frequency="每周 3 次",
                notes="测试。",
            )
            JsonRepository(workspace, ContentMechanism).create(mechanism)
            JsonRepository(workspace, CreatorProfile).create(profile)
            first = self._run_cli(
                [
                    "propose-asset-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    mechanism.id,
                    "--creator-id",
                    profile.id,
                    "--file",
                    str(proposal_file),
                ]
            )
            after_first = self._snapshot_workspace(workspace)

            duplicate = self._run_cli(
                [
                    "propose-asset-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    mechanism.id,
                    "--creator-id",
                    profile.id,
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertEqual(first["result"]["created_count"], 1)
            self.assertIn("已有相同", duplicate["error"])
            self.assertEqual(self._snapshot_workspace(workspace), after_first)

    def test_content_asset_lifecycle_cli_activates_and_deprecates_with_safe_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            candidate = ContentAsset(
                id="asset-cli-candidate",
                status="candidate",
                asset_type="opening_template",
                name="任务结果优先开场",
                description="用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
                template="结果：{{result}}\n过程：{{process}}",
                variables=["result", "process"],
                applicable_scope=["AI 内容运营"],
                exclusions=[],
                usage_notes=[],
                limitations=[],
                examples=[],
                creator_profile_id="creator-main",
                source_mechanism_ids=["mechanism-result-framing"],
                selected_observed_facts=["标题先展示结果承诺，再说明使用的工具和流程"],
                account_fit_reason="提案中的账号适配理由。",
                confidence_level="medium",
                confidence=0.6,
            )
            active = ContentAsset.from_dict({**candidate.to_dict(), "id": "asset-cli-active", "status": "active"})
            JsonRepository(workspace, ContentAsset).create(candidate)
            JsonRepository(workspace, ContentAsset).create(active)

            activated = self._run_cli(
                [
                    "activate-content-asset",
                    "--workspace",
                    temp_dir,
                    "--asset-id",
                    candidate.id,
                    "--expected-version",
                    "1",
                    "--actor",
                    "user",
                ]
            )
            deprecated = self._run_cli(
                [
                    "deprecate-content-asset",
                    "--workspace",
                    temp_dir,
                    "--asset-id",
                    active.id,
                    "--expected-version",
                    "1",
                    "--actor",
                    "user",
                ]
            )

            self.assertTrue(activated["ok"])
            self.assertTrue(deprecated["ok"])
            self.assertEqual(JsonRepository(workspace, ContentAsset).read(candidate.id).status, "active")
            self.assertEqual(JsonRepository(workspace, ContentAsset).read(active.id).status, "deprecated")
            self.assertEqual(activated["result"]["machine_summary"]["operation"], "activate")
            self.assertEqual(deprecated["result"]["machine_summary"]["operation"], "deprecate")
            self.assertFalse(activated["result"]["machine_summary"]["generation_context_connected"])
            self.assertFalse(deprecated["result"]["machine_summary"]["decision_request_created"])
            for summary in (activated["result"]["user_summary"], deprecated["result"]["user_summary"]):
                for forbidden in (
                    candidate.id,
                    active.id,
                    "ContentAsset",
                    "content-assets",
                    "candidate",
                    "active",
                    "deprecated",
                    "GenerationContext",
                    ".json",
                    temp_dir,
                ):
                    self.assertNotIn(forbidden, summary)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ProvenanceRecord).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentAssetEvidence).list_all(), [])

    def test_content_asset_lifecycle_cli_failures_are_safe_and_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            asset = ContentAsset(
                id="asset-cli-failure",
                status="candidate",
                asset_type="opening_template",
                name="任务结果优先开场",
                description="用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
                template="结果：{{result}}\n过程：{{process}}",
                variables=["result", "process"],
                applicable_scope=["AI 内容运营"],
                exclusions=[],
                usage_notes=[],
                limitations=[],
                examples=[],
                creator_profile_id="creator-main",
                source_mechanism_ids=["mechanism-result-framing"],
                selected_observed_facts=["标题先展示结果承诺，再说明使用的工具和流程"],
                account_fit_reason="提案中的账号适配理由。",
                confidence_level="medium",
                confidence=0.6,
            )
            JsonRepository(workspace, ContentAsset).create(asset)
            before = self._snapshot_workspace(workspace)

            stale = self._run_cli(
                [
                    "activate-content-asset",
                    "--workspace",
                    temp_dir,
                    "--asset-id",
                    asset.id,
                    "--expected-version",
                    "2",
                    "--actor",
                    "user",
                ],
                expected_code=1,
            )
            missing = self._run_cli(
                [
                    "deprecate-content-asset",
                    "--workspace",
                    temp_dir,
                    "--asset-id",
                    "missing-asset",
                    "--expected-version",
                    "1",
                    "--actor",
                    "user",
                ],
                expected_code=1,
            )
            illegal = self._run_cli(
                [
                    "deprecate-content-asset",
                    "--workspace",
                    temp_dir,
                    "--asset-id",
                    asset.id,
                    "--expected-version",
                    "0",
                    "--actor",
                    "user",
                ],
                expected_code=1,
            )

            self.assertIn("版本冲突", stale["error"])
            self.assertIn("内容资产不存在", missing["error"])
            self.assertIn("输入参数无效", illegal["error"])
            for output in (stale, missing, illegal):
                self.assertFalse(output["ok"])
                self.assertNotIn("Traceback", output["error"])
                self.assertNotIn("ContentAsset", output["error"])
                self.assertNotIn("content-assets", output["error"])
                self.assertNotIn(temp_dir, output["error"])
            self.assertEqual(self._snapshot_workspace(workspace), before)

    def test_content_asset_lifecycle_cli_rejects_missing_or_file_workspace_without_creating_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            missing_workspace = base / "missing-workspace"
            file_workspace = base / "workspace-file"
            file_workspace.write_text("not a directory", encoding="utf-8")

            activate = self._run_cli(
                [
                    "activate-content-asset",
                    "--workspace",
                    str(missing_workspace),
                    "--asset-id",
                    "asset-missing",
                    "--expected-version",
                    "1",
                    "--actor",
                    "user",
                ],
                expected_code=1,
            )
            deprecate = self._run_cli(
                [
                    "deprecate-content-asset",
                    "--workspace",
                    str(file_workspace),
                    "--asset-id",
                    "asset-missing",
                    "--expected-version",
                    "1",
                    "--actor",
                    "user",
                ],
                expected_code=1,
            )

            self.assertFalse(missing_workspace.exists())
            self.assertTrue(file_workspace.is_file())
            self.assertEqual(file_workspace.read_text(encoding="utf-8"), "not a directory")
            for output in (activate, deprecate):
                self.assertFalse(output["ok"])
                self.assertIn("工作区不存在或不可用", output["error"])
                self.assertNotIn(temp_dir, output["error"])
                self.assertNotIn("Traceback", output["error"])
                self.assertNotIn("ContentAsset", output["error"])
                self.assertNotIn("content-assets", output["error"])

    def test_content_asset_lifecycle_cli_rejects_non_integer_expected_version(self) -> None:
        with self.assertRaises(SystemExit):
            self._run_cli(
                [
                    "activate-content-asset",
                    "--workspace",
                    ".",
                    "--asset-id",
                    "asset-missing",
                    "--expected-version",
                    "abc",
                    "--actor",
                    "user",
                ]
            )

    def test_propose_rule_from_mechanism_missing_records_write_no_business_objects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            proposal_file = workspace / "mechanism-rule.json"
            proposal_file.write_text(
                json.dumps(
                    {
                        "rule_statement": "讲 AI 工具时，优先表达用户能够完成的内容运营任务。",
                        "rule_type": "topic",
                        "applicable_scope": ["AI 内容运营"],
                        "exclusions": [],
                        "selected_observed_facts": ["标题先讲用户能完成的内容运营任务"],
                        "account_fit_reason": "当前账号定位强调内容运营判断。",
                        "limitations": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(
                [
                    "propose-rule-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    "mechanism-missing",
                    "--creator-id",
                    "creator-missing",
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertIn("未找到指定内容机制或账号档案", output["error"])
            self.assertEqual(JsonRepository(workspace, RuleCard).list_all(), [])
            self.assertEqual(JsonRepository(workspace, RuleEvidence).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ProvenanceRecord).list_all(), [])
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(set(self._snapshot_workspace(workspace)) - set(before), set())

    def test_propose_rule_from_mechanism_duplicate_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            mechanism = ContentMechanism(
                id="mechanism-cli-duplicate",
                name="结果化表达",
                description="先表达用户结果。",
                status="candidate",
                confidence_level="low",
                confidence=0.4,
                evidence_summary={"observed_facts": ["标题先讲用户能完成的内容运营任务"]},
                problem="工具内容容易看不懂。",
                solution="先讲结果。",
                applicable_scope=["AI 内容运营"],
                limitations=[],
            )
            profile = CreatorProfile(
                id="creator-cli-duplicate",
                name="主账号",
                positioning="帮助创作者用 AI 做内容运营判断。",
                target_audience=["内容创作者"],
                content_style=["真实"],
                forbidden_expressions=[],
                goals=["提升内容运营效率"],
                content_formats=["图文"],
                publish_frequency="每周 3 次",
                notes="测试账号。",
            )
            existing = RuleCard(
                id="rule-existing-duplicate",
                name="旧规则",
                type="topic",
                source_ids=["old"],
                applicable_scenarios=["AI 内容运营"],
                rule_summary="讲 AI 工具时，优先表达用户能够完成的内容运营任务。",
                examples=["旧证据"],
                risks=[],
                adaptation_notes="旧说明",
                status="approved",
            )
            JsonRepository(workspace, ContentMechanism).create(mechanism)
            JsonRepository(workspace, CreatorProfile).create(profile)
            JsonRepository(workspace, RuleCard).create(existing)
            proposal_file = workspace / "duplicate.json"
            proposal_file.write_text(
                json.dumps(
                    {
                        "rule_statement": existing.rule_summary,
                        "rule_type": "topic",
                        "applicable_scope": ["AI 内容运营"],
                        "exclusions": [],
                        "selected_observed_facts": ["标题先讲用户能完成的内容运营任务"],
                        "account_fit_reason": "当前账号定位强调帮助创作者用 AI 做内容运营判断。",
                        "limitations": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            before = self._snapshot_workspace(workspace)

            output = self._run_cli(
                [
                    "propose-rule-from-mechanism",
                    "--workspace",
                    temp_dir,
                    "--mechanism-id",
                    mechanism.id,
                    "--creator-id",
                    profile.id,
                    "--file",
                    str(proposal_file),
                ],
                expected_code=1,
            )

            self.assertIn("已有相同", output["error"])
            self.assertEqual(self._snapshot_workspace(workspace), before)

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

    def _create_rule_decision(
        self,
        workspace: str,
        rule_id: str,
        question: str = "是否确认？",
        expected_code: int = 0,
    ) -> dict:
        return self._run_cli(
            [
                "create-decision",
                "--workspace",
                workspace,
                "--target-type",
                "rule_card",
                "--target-id",
                rule_id,
                "--question",
                question,
                "--option",
                "confirm",
                "--option",
                "reject",
                "--recommendation",
                "confirm",
                "--recommendation-reason",
                "证据清晰。",
                "--impact",
                "确认后进入长期规则。",
            ],
            expected_code=expected_code,
        )

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
        status: str = "approved",
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
            status=status,
        )
        JsonRepository(data_dir, RuleCard).create(rule)
        return rule

    def _seed_rule_generation_support(
        self,
        data_dir: Path,
        rule_id: str,
        *,
        profile_version: int = 1,
        evidence: bool = True,
    ) -> None:
        if evidence:
            JsonRepository(data_dir, RuleEvidence).create(
                RuleEvidence(
                    id=f"evidence-{rule_id}",
                    rule_id=rule_id,
                    source_type="benchmark_analysis",
                    source_id="analysis-001",
                    source_fragment="标题",
                    evidence_type="title",
                    observable_fact="标题点名具体对象。",
                    inference="用于支持选题生成。",
                )
            )
        JsonRepository(data_dir, ProvenanceRecord).create(
            ProvenanceRecord(
                id=f"provenance-{rule_id}",
                target_object_type="rule_card",
                target_object_id=rule_id,
                source_object_type="creator_profile",
                source_object_id="creator-main",
                source_version=profile_version,
                actor="codex",
                artifact_nature="recommendation",
                method="test",
                note="账号档案来源。",
            )
        )
        JsonRepository(data_dir, DecisionRequest).create(
            DecisionRequest(
                id=f"decision-{rule_id}",
                target_object_type="rule_card",
                target_object_id=rule_id,
                question="是否采用？",
                options=["确认使用", "暂不使用"],
                option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
                recommendation="确认使用",
                recommendation_reason="测试。",
                impact="测试。",
                status="confirmed",
                selected_option="确认使用",
                resolved_at="2026-07-11T00:00:00Z",
                resolved_by="user",
            )
        )

    def _seed_audited_topic(self, data_dir: Path, *, reference_assets: Optional[list[dict[str, Any]]] = None) -> TopicItem:
        topic = TopicItem(
            id="topic-audit-001",
            title="新人入职前三天如何快速进入状态",
            content_goal="帮助刚入职的新人明确前三天行动",
            content_format="清单",
            source_rule_cards=["rule-a", "rule-b"],
            reference_posts=["benchmark-post-001"],
            reason="基于账号定位和已确认规则。",
            status="idea",
            tags=["新人入职", "图文"],
            source_profile_id="creator-main",
            source_profile_version=2,
            generation_context_status="limited",
            task_constraints={"topic_area": "新人入职", "content_type": "图文"},
            risk_warnings=["规则缺少独立证据记录"],
            missing_information=["规则缺少独立证据记录"],
            reference_assets=reference_assets or [],
            created_by="codex",
        )
        return JsonRepository(data_dir, TopicItem).create(topic)

    def _seed_content_asset(
        self,
        data_dir: Path,
        asset_id: str,
        *,
        status: str,
        version: int = 1,
        creator_profile_id: str = "creator-main",
    ) -> ContentAsset:
        asset = ContentAsset(
            id=asset_id,
            version=version,
            status=status,
            asset_type="opening_template",
            name="结果优先开场",
            description="先说明用户能得到的结果，再解释过程。",
            template="先说结果：{{result}}。再说过程：{{process}}。",
            variables=["result", "process"],
            applicable_scope=["AI 内容运营"],
            exclusions=["纯工具介绍"],
            usage_notes=["填入具体结果和过程。"],
            limitations=["不能夸大收益。"],
            examples=["先说 10 分钟完成选题库，再说明步骤。"],
            creator_profile_id=creator_profile_id,
            source_mechanism_ids=["mechanism-result-framing"],
            selected_observed_facts=["标题先展示结果承诺，再说明使用的工具和流程"],
            account_fit_reason="适合当前账号强调具体结果的表达方式。",
            confidence_level="medium",
            confidence=0.6,
        )
        return JsonRepository(data_dir, ContentAsset).create(asset)

    def _snapshot_workspace(self, data_dir: Path) -> dict[str, str]:
        return {
            str(path.relative_to(data_dir)): path.read_text(encoding="utf-8")
            for path in sorted(data_dir.rglob("*.json"))
        }

    def _snapshot_collection(self, data_dir: Path, model: type) -> dict[str, dict[str, Any]]:
        return {item.id: item.to_dict() for item in JsonRepository(data_dir, model).list_all()}

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
