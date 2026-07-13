from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.generation.context import GenerationTaskConstraints, build_generation_context  # noqa: E402
from app.models.core import (  # noqa: E402
    BenchmarkAnalysis,
    BenchmarkPost,
    CaptureRecord,
    ContentMechanism,
    CreatorProfile,
    DecisionRequest,
    ProvenanceRecord,
    RuleCard,
    RuleEvidence,
)
from app.repositories import JsonRepository  # noqa: E402


class GenerationContextTests(unittest.TestCase):
    def test_builds_limited_context_with_usable_excluded_evidence_provenance_and_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            profile = self._seed_profile(workspace, version=2)
            self._seed_rule_set(workspace)
            before = snapshot_workspace(workspace)

            context = build_generation_context(
                profile=profile,
                rules=JsonRepository(workspace, RuleCard).list_all(),
                evidence=JsonRepository(workspace, RuleEvidence).list_all(),
                provenance=JsonRepository(workspace, ProvenanceRecord).list_all(),
                decisions=JsonRepository(workspace, DecisionRequest).list_all(),
                task_constraints=GenerationTaskConstraints(
                    intent="准备后续选题",
                    content_type="图文",
                    target_audiences=["刚入职的新人"],
                    content_format="清单",
                    tone="直接、具体",
                    do_items=["给出可执行步骤"],
                    dont_items=["夸大效果"],
                ),
            )

            self.assertEqual(context.status_category, "limited")
            usable_by_id = {item["rule_id"]: item for item in context.usable_rules}
            self.assertEqual([item["rule_id"] for item in context.usable_rules], ["rule-b", "rule-a"])
            self.assertEqual(usable_by_id["rule-a"]["decision_basis"], "user_confirmed")
            self.assertEqual(usable_by_id["rule-b"]["decision_basis"], "testing_or_validated")
            self.assertEqual(usable_by_id["rule-a"]["profile_alignment"], "matched")
            self.assertEqual(usable_by_id["rule-b"]["profile_alignment"], "version_mismatch")
            self.assertEqual(usable_by_id["rule-a"]["evidence_summaries"][0]["observable_fact"], "标题点名刚入职的新人。")
            self.assertEqual(usable_by_id["rule-b"]["evidence_summaries"], [])
            self.assertIn("当前规则没有独立证据记录", usable_by_id["rule-b"]["warnings"])
            self.assertIn("该规则来源于当前账号档案的其他版本", usable_by_id["rule-b"]["warnings"])
            self.assertEqual(
                [(item["rule_id"], item["reason_code"]) for item in context.excluded_rules],
                [
                    ("rule-c", "awaiting_user_confirmation"),
                    ("rule-e", "deprecated"),
                    ("rule-d", "rejected_by_lifecycle"),
                ],
            )
            self.assertIn("规则「正文结构保留行动步骤」缺少独立证据记录", context.missing_information)
            self.assertIn("规则「正文结构保留行动步骤」来源于当前账号档案的其他版本", context.missing_information)
            self.assertIn("夸张承诺", context.risk_warnings)
            self.assertEqual(context.profile["profile_id"], "creator-main")
            self.assertEqual(context.profile["profile_version"], 2)
            self.assertEqual(context.task_constraints["intent"], "准备后续选题")
            self.assertEqual(context.machine_summary["usable_rule_ids"], ["rule-b", "rule-a"])
            json.dumps(context.to_dict(), ensure_ascii=False)
            self.assertEqual(snapshot_workspace(workspace), before)

    def test_ready_requires_usable_rule_evidence_and_matched_profile_provenance(self) -> None:
        profile = CreatorProfile(
            id="creator-main",
            version=2,
            name="主账号",
            platform="小红书",
            positioning="职场新人表达成长",
            target_audience=["职场新人"],
            content_style=["真实", "具体"],
            forbidden_expressions=[],
            goals=["提升收藏"],
            content_formats=["图文"],
            publish_frequency="每周 3 篇",
            notes="测试。",
        )
        rule = make_rule("rule-ready", "approved", "标题点名具体对象", rule_type="title")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[make_evidence("evidence-ready", rule.id, "标题点名职场新人。")],
            provenance=[make_profile_provenance("provenance-ready", rule.id, profile.id, profile.version)],
            decisions=[make_confirmed_decision("decision-ready", rule.id)],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "ready")
        self.assertEqual(context.missing_information, [])
        self.assertEqual(context.usable_rules[0]["profile_alignment"], "matched")

    def test_content_mechanism_records_do_not_enter_generation_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            profile = self._seed_profile(workspace, version=1)
            rule = make_rule("rule-ready", "approved", "标题点名具体对象", rule_type="title")
            JsonRepository(workspace, RuleCard).create(rule)
            JsonRepository(workspace, RuleEvidence).create(make_evidence("evidence-ready", rule.id, "标题点名职场新人。"))
            JsonRepository(workspace, ProvenanceRecord).create(
                make_profile_provenance("provenance-ready", rule.id, profile.id, profile.version)
            )
            JsonRepository(workspace, DecisionRequest).create(make_confirmed_decision("decision-ready", rule.id))
            JsonRepository(workspace, ContentMechanism).create(
                ContentMechanism(
                    id="mechanism-ignored",
                    name="结果前置机制",
                    description="先讲结果，再讲过程。",
                    status="candidate",
                    confidence_level="medium",
                    confidence=0.6,
                    source_refs=[{"source_type": "benchmark_analysis", "source_id": "analysis-001"}],
                    evidence_summary={"observed_facts": ["封面先讲结果"]},
                    problem="过程型内容门槛高。",
                    solution="结果前置。",
                    pattern=["结果前置"],
                )
            )
            before = snapshot_workspace(workspace)

            context = build_generation_context(
                profile=profile,
                rules=JsonRepository(workspace, RuleCard).list_all(),
                evidence=JsonRepository(workspace, RuleEvidence).list_all(),
                provenance=JsonRepository(workspace, ProvenanceRecord).list_all(),
                decisions=JsonRepository(workspace, DecisionRequest).list_all(),
                task_constraints=GenerationTaskConstraints(),
            )

            self.assertEqual(context.status_category, "ready")
            self.assertEqual(context.machine_summary["usable_rule_ids"], ["rule-ready"])
            serialized = json.dumps(context.to_dict(), ensure_ascii=False)
            self.assertNotIn("mechanism-ignored", serialized)
            self.assertNotIn("结果前置机制", serialized)
            self.assertEqual(snapshot_workspace(workspace), before)

    def test_excludes_candidate_even_with_confirmed_looking_decision(self) -> None:
        profile = self._profile()
        candidate = make_rule("rule-candidate", "candidate", "候选规则")
        context = build_generation_context(
            profile=profile,
            rules=[candidate],
            evidence=[make_evidence("evidence-candidate", candidate.id, "候选证据。")],
            provenance=[make_profile_provenance("provenance-candidate", candidate.id, profile.id, profile.version)],
            decisions=[make_confirmed_decision("decision-candidate", candidate.id)],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.usable_rules, [])
        self.assertEqual(context.excluded_rules[0]["reason_code"], "awaiting_user_confirmation")
        self.assertEqual(context.status_category, "limited")

    def test_marks_different_profile_alignment_as_limited(self) -> None:
        profile = self._profile()
        rule = make_rule("rule-different-profile", "approved", "标题贴近具体人群")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[make_evidence("evidence-different-profile", rule.id, "标题点名具体人群。")],
            provenance=[make_profile_provenance("provenance-different-profile", rule.id, "other-profile", 1)],
            decisions=[make_confirmed_decision("decision-different-profile", rule.id)],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "limited")
        self.assertEqual(context.usable_rules[0]["profile_alignment"], "different_profile")
        self.assertIn("该规则来源于其他账号档案", context.usable_rules[0]["warnings"])
        self.assertIn("规则「标题贴近具体人群」来源于其他账号档案", context.missing_information)

    def test_marks_missing_profile_provenance_as_limited(self) -> None:
        profile = self._profile()
        rule = make_rule("rule-missing-provenance", "approved", "标题使用真实经历")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[make_evidence("evidence-missing-provenance", rule.id, "标题来自真实经历。")],
            provenance=[],
            decisions=[make_confirmed_decision("decision-missing-provenance", rule.id)],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "limited")
        self.assertEqual(context.usable_rules[0]["profile_alignment"], "missing")
        self.assertIn("当前规则没有可验证的账号档案来源", context.usable_rules[0]["warnings"])
        self.assertIn("规则「标题使用真实经历」缺少账号档案来源记录", context.missing_information)

    def test_no_usable_rules_is_limited(self) -> None:
        profile = self._profile()
        context = build_generation_context(
            profile=profile,
            rules=[make_rule("rule-rejected-only", "rejected", "不再使用的标题规则")],
            evidence=[],
            provenance=[],
            decisions=[],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "limited")
        self.assertEqual(context.usable_rules, [])
        self.assertEqual(context.excluded_rules[0]["reason_code"], "rejected_by_lifecycle")
        self.assertIn("当前没有可用规则", context.risk_warnings)
        self.assertIn("没有可用规则", context.missing_information)

    def test_lifecycle_approved_rule_without_decision_keeps_explicit_basis(self) -> None:
        profile = self._profile()
        rule = make_rule("rule-lifecycle-approved", "approved", "标题给出明确场景")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[make_evidence("evidence-lifecycle-approved", rule.id, "标题给出明确场景。")],
            provenance=[make_profile_provenance("provenance-lifecycle-approved", rule.id, profile.id, profile.version)],
            decisions=[],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "ready")
        self.assertEqual(context.usable_rules[0]["decision_basis"], "lifecycle_approved_without_decision")
        self.assertEqual(context.usable_rules[0]["profile_alignment"], "matched")

    def test_active_rule_with_pending_decision_adds_warning_without_excluding_rule(self) -> None:
        profile = self._profile()
        rule = make_rule("rule-pending-decision", "approved", "标题保留口语表达")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[make_evidence("evidence-pending-decision", rule.id, "标题保留口语表达。")],
            provenance=[make_profile_provenance("provenance-pending-decision", rule.id, profile.id, profile.version)],
            decisions=[make_pending_decision("decision-pending", rule.id)],
            task_constraints=GenerationTaskConstraints(),
        )

        self.assertEqual(context.status_category, "ready")
        self.assertEqual([item["rule_id"] for item in context.usable_rules], [rule.id])
        self.assertIn("该规则仍关联未完成的待决记录", context.usable_rules[0]["warnings"])
        self.assertIn("该规则仍关联未完成的待决记录", context.risk_warnings)

    def test_task_constraints_trim_deduplicate_and_do_not_infer_defaults(self) -> None:
        constraints = GenerationTaskConstraints.from_cli_values(
            intent=" 准备选题 ",
            content_type=" ",
            topic_area=" 职场表达 ",
            target_audiences=[" 新人 ", "", "新人", "管理者"],
            content_format=" 清单 ",
            tone=" 具体 ",
            length=" ",
            do_items=[" 给步骤 ", "给步骤", ""],
            dont_items=[" 夸张 ", "夸张"],
            reference_ids=[" ref-1 ", "ref-1", "ref-2"],
        )

        self.assertEqual(constraints.to_dict()["intent"], "准备选题")
        self.assertEqual(constraints.to_dict()["content_type"], "")
        self.assertEqual(constraints.to_dict()["target_audiences"], ["新人", "管理者"])
        self.assertEqual(constraints.to_dict()["do_items"], ["给步骤"])
        self.assertEqual(constraints.to_dict()["reference_ids"], ["ref-1", "ref-2"])

    def test_user_summary_hides_internal_identifiers_and_machine_enums(self) -> None:
        profile = self._profile()
        rule = make_rule("rule-secret", "approved", "标题给出具体对象", rule_type="title")
        context = build_generation_context(
            profile=profile,
            rules=[rule],
            evidence=[],
            provenance=[],
            decisions=[],
            task_constraints=GenerationTaskConstraints(intent="准备选题"),
        )

        forbidden = [
            "creator-main",
            "rule-secret",
            "RuleCard",
            "RuleEvidence",
            "DecisionRequest",
            "ProvenanceRecord",
            "approved",
            "candidate",
            "version_mismatch",
            "repository",
            ".json",
            "/Users/",
        ]
        for text in forbidden:
            self.assertNotIn(text, context.user_summary)

    def _seed_profile(self, workspace: Path, version: int) -> CreatorProfile:
        profile = self._profile()
        data = profile.to_dict()
        data["version"] = version
        saved = CreatorProfile.from_dict(data)
        JsonRepository(workspace, CreatorProfile).create(saved)
        return saved

    def _profile(self) -> CreatorProfile:
        return CreatorProfile(
            id="creator-main",
            name="主账号",
            platform="小红书",
            positioning="职场新人表达成长",
            target_audience=["职场新人"],
            content_style=["真实", "具体"],
            forbidden_expressions=["夸张承诺"],
            goals=["提升收藏"],
            content_formats=["图文"],
            publish_frequency="每周 3 篇",
            notes="测试。",
        )

    def _seed_rule_set(self, workspace: Path) -> None:
        rules = [
            make_rule("rule-a", "approved", "标题点名刚入职的新人", rule_type="title", scenarios=["图文标题"]),
            make_rule("rule-b", "testing", "正文结构保留行动步骤", rule_type="structure", scenarios=["正文结构"]),
            make_rule("rule-c", "candidate", "候选标题规则", rule_type="title"),
            make_rule("rule-d", "rejected", "被拒绝规则", rule_type="title"),
            make_rule("rule-e", "deprecated", "已废弃规则", rule_type="title"),
        ]
        for rule in rules:
            JsonRepository(workspace, RuleCard).create(rule)
        JsonRepository(workspace, RuleEvidence).create(make_evidence("evidence-a", "rule-a", "标题点名刚入职的新人。"))
        JsonRepository(workspace, ProvenanceRecord).create(make_profile_provenance("provenance-a", "rule-a", "creator-main", 2))
        JsonRepository(workspace, ProvenanceRecord).create(make_profile_provenance("provenance-b", "rule-b", "creator-main", 1))
        JsonRepository(workspace, DecisionRequest).create(make_confirmed_decision("decision-a", "rule-a"))
        JsonRepository(workspace, DecisionRequest).create(make_pending_decision("decision-b", "rule-b"))
        JsonRepository(workspace, BenchmarkAnalysis).create(BenchmarkAnalysis(id="analysis-001", capture_id="capture-001"))
        JsonRepository(workspace, BenchmarkPost).create(
            BenchmarkPost(
                id="benchmark-post-001",
                account_id="benchmark-account-001",
                title="测试",
                content_type="图文",
                raw_content="测试内容。",
            )
        )
        JsonRepository(workspace, CaptureRecord).create(
            CaptureRecord(id="capture-001", inbox_item_id="inbox-001", source_url="https://example.test/post")
        )


def make_rule(
    rule_id: str,
    status: str,
    summary: str,
    *,
    rule_type: str = "title",
    scenarios: list[str] | None = None,
) -> RuleCard:
    return RuleCard(
        id=rule_id,
        name=summary,
        type=rule_type,
        source_ids=["analysis-001"],
        applicable_scenarios=scenarios or ["图文标题"],
        rule_summary=summary,
        examples=["示例"],
        risks=["对象过宽会变泛。"],
        adaptation_notes="适合当前账号。",
        status=status,
        strength="medium",
    )


def make_evidence(evidence_id: str, rule_id: str, fact: str) -> RuleEvidence:
    return RuleEvidence(
        id=evidence_id,
        rule_id=rule_id,
        source_type="benchmark_analysis",
        source_id="analysis-001",
        source_fragment="标题",
        evidence_type="title",
        observable_fact=fact,
        inference="用于支持规则。",
    )


def make_profile_provenance(provenance_id: str, rule_id: str, profile_id: str, profile_version: int) -> ProvenanceRecord:
    return ProvenanceRecord(
        id=provenance_id,
        target_object_type="rule_card",
        target_object_id=rule_id,
        source_object_type="creator_profile",
        source_object_id=profile_id,
        source_version=profile_version,
        actor="codex",
        artifact_nature="recommendation",
        method="test",
        note="账号档案来源。",
    )


def make_confirmed_decision(decision_id: str, rule_id: str) -> DecisionRequest:
    return DecisionRequest(
        id=decision_id,
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


def make_pending_decision(decision_id: str, rule_id: str) -> DecisionRequest:
    return DecisionRequest(
        id=decision_id,
        target_object_type="rule_card",
        target_object_id=rule_id,
        question="是否采用？",
        options=["确认使用", "暂不使用"],
        option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
        recommendation="暂不使用",
        recommendation_reason="测试。",
        impact="测试。",
        status="pending",
    )


def snapshot_workspace(workspace: Path) -> dict[str, str]:
    return {
        str(path.relative_to(workspace)): path.read_text(encoding="utf-8")
        for path in sorted(workspace.rglob("*.json"))
    }


if __name__ == "__main__":
    unittest.main()
