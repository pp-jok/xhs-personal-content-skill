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
    DecisionRequest,
    OwnPost,
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

    def test_generate_topics_passes_only_active_rules_to_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            for status in ("candidate", "approved", "testing", "validated", "rejected", "deprecated"):
                self._seed_rule(data_dir, f"rule-{status}", status=status)
            prompt_service = RecordingPromptService()

            with patch("app.cli.main.build_prompt_service", return_value=prompt_service):
                output = self._run_cli(
                    [
                        "generate-topics",
                        "--workspace",
                        temp_dir,
                        "--creator-id",
                        "creator-main",
                        "--benchmark-post-id",
                        "benchmark-post-001",
                    ]
                )

            payload = prompt_service.payloads["generate_topic_pool"][0]
            self.assertTrue(output["ok"])
            self.assertEqual(
                [rule["id"] for rule in payload["rule_cards"]],
                ["rule-approved", "rule-testing", "rule-validated"],
            )

    def test_generate_draft_passes_only_active_rules_to_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            JsonRepository(data_dir, TopicItem).create(
                TopicItem(
                    id="topic-001",
                    title="测试选题",
                    content_goal="提升收藏",
                    content_format="图文",
                    source_rule_cards=[],
                    reference_posts=["benchmark-post-001"],
                    reason="测试。",
                )
            )
            for status in ("candidate", "approved", "testing", "validated", "rejected", "deprecated"):
                self._seed_rule(data_dir, f"rule-{status}", status=status)
            prompt_service = RecordingPromptService()

            with patch("app.cli.main.build_prompt_service", return_value=prompt_service):
                output = self._run_cli(["generate-draft", "--workspace", temp_dir, "--topic-id", "topic-001"])

            payload = prompt_service.payloads["generate_content_draft"][0]
            self.assertTrue(output["ok"])
            self.assertEqual(
                [rule["id"] for rule in payload["rule_cards"]],
                ["rule-approved", "rule-testing", "rule-validated"],
            )

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
