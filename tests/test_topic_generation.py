from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.generation.context import GenerationContext  # noqa: E402
from app.generation.topics import TopicGenerationError, generate_topics_from_context  # noqa: E402


class TopicGenerationTests(unittest.TestCase):
    def test_ready_context_generates_requested_topics_with_audit_fields(self) -> None:
        context = make_context(status="ready", usable_rules=[make_rule("rule-approved", "title", "标题点名具体对象")])

        result = generate_topics_from_context(context=context, topic_count=3)

        self.assertEqual(result.context_status, "ready")
        self.assertEqual(len(result.topics), 3)
        self.assertEqual(len({topic.title for topic in result.topics}), 3)
        for topic in result.topics:
            self.assertEqual(topic.source_profile_id, "creator-main")
            self.assertEqual(topic.source_profile_version, 2)
            self.assertEqual(topic.generation_context_status, "ready")
            self.assertEqual(topic.task_constraints["topic_area"], "新人入职")
            self.assertEqual(topic.risk_warnings, ["避免对象过宽。"])
            self.assertEqual(topic.missing_information, [])
            self.assertEqual(topic.source_rule_cards, ["rule-approved"])
            self.assertEqual(topic.reference_posts, ["benchmark-post-001"])
            self.assertEqual(topic.content_format, "清单")
            self.assertEqual(topic.status, "idea")
        self.assertEqual(result.machine_summary["profile_id"], "creator-main")
        self.assertEqual(result.machine_summary["topic_count"], 3)
        self.assertEqual(result.machine_summary["usable_rule_ids"], ["rule-approved"])
        json.dumps(result.machine_summary, ensure_ascii=False)

    def test_explicit_reference_asset_is_carried_into_topics(self) -> None:
        reference_asset = make_reference_asset()
        context = make_context(
            status="ready",
            usable_rules=[make_rule("rule-approved", "title", "标题点名具体对象")],
            reference_assets=[reference_asset],
        )

        result = generate_topics_from_context(context=context, topic_count=1)

        topic = result.topics[0]
        self.assertEqual(topic.reference_assets, [reference_asset])
        self.assertEqual(result.machine_summary["reference_asset_ids"], ["asset-opening"])
        self.assertEqual(result.machine_summary["reference_assets"], [reference_asset])

    def test_limited_context_with_usable_rules_generates_topics_and_warning(self) -> None:
        context = make_context(
            status="limited",
            usable_rules=[make_rule("rule-testing", "structure", "正文保留行动步骤")],
            missing_information=["规则「正文保留行动步骤」缺少独立证据记录"],
        )

        result = generate_topics_from_context(context=context, topic_count=1)

        self.assertEqual(len(result.topics), 1)
        self.assertIn("当前上下文有信息限制", result.warnings)
        self.assertIn("可使用但有限制", result.user_summary)
        self.assertEqual(result.topics[0].generation_context_status, "limited")
        self.assertEqual(result.topics[0].missing_information, ["规则「正文保留行动步骤」缺少独立证据记录"])

    def test_no_usable_rules_fails_without_topics(self) -> None:
        context = make_context(status="limited", usable_rules=[])

        with self.assertRaises(TopicGenerationError) as caught:
            generate_topics_from_context(context=context, topic_count=1)

        self.assertIn("没有可用规则", str(caught.exception))

    def test_excluded_rule_ids_never_enter_topic_sources(self) -> None:
        context = make_context(
            status="ready",
            usable_rules=[make_rule("rule-approved", "title", "标题点名具体对象")],
            excluded_rules=[
                {"rule_id": "rule-candidate", "reason_code": "awaiting_user_confirmation"},
                {"rule_id": "rule-rejected", "reason_code": "rejected_by_lifecycle"},
                {"rule_id": "rule-deprecated", "reason_code": "deprecated"},
            ],
        )

        result = generate_topics_from_context(context=context, topic_count=2)

        for topic in result.topics:
            self.assertEqual(topic.source_rule_cards, ["rule-approved"])
            self.assertNotIn("rule-candidate", topic.source_rule_cards)
            self.assertNotIn("rule-rejected", topic.source_rule_cards)
            self.assertNotIn("rule-deprecated", topic.source_rule_cards)

    def test_user_summary_hides_ids_paths_and_machine_enums(self) -> None:
        context = make_context(
            status="limited",
            usable_rules=[make_rule("rule-secret", "title", "标题点名具体对象")],
            excluded_rules=[{"rule_id": "rule-candidate", "reason_code": "awaiting_user_confirmation"}],
            missing_information=["规则缺少独立证据记录"],
        )

        result = generate_topics_from_context(context=context, topic_count=1)

        forbidden = [
            "creator-main",
            "rule-secret",
            "rule-candidate",
            "topic-from",
            "TopicItem",
            "RuleCard",
            "GenerationContext",
            "approved",
            "testing",
            "validated",
            "candidate",
            "rejected",
            "deprecated",
            "ready",
            "limited",
            "JSON",
            ".py",
            ".json",
            "/Users/",
        ]
        for text in forbidden:
            self.assertNotIn(text, result.user_summary)

    def test_topic_count_bounds_are_explicit(self) -> None:
        context = make_context(status="ready", usable_rules=[make_rule("rule-approved", "title", "标题点名具体对象")])

        self.assertEqual(len(generate_topics_from_context(context=context, topic_count=1).topics), 1)
        self.assertEqual(len(generate_topics_from_context(context=context, topic_count=10).topics), 10)
        for invalid_count in (0, -1, 11):
            with self.assertRaises(TopicGenerationError):
                generate_topics_from_context(context=context, topic_count=invalid_count)


def make_context(
    *,
    status: str,
    usable_rules: list[dict[str, object]],
    excluded_rules: list[dict[str, object]] | None = None,
    missing_information: list[str] | None = None,
    reference_assets: list[dict[str, object]] | None = None,
) -> GenerationContext:
    task_constraints = {
        "intent": "准备后续选题",
        "content_type": "图文",
        "topic_area": "新人入职",
        "target_audiences": ["刚入职的新人"],
        "content_format": "清单",
        "tone": "直接、具体",
        "length": "",
        "do_items": ["给出可执行步骤"],
        "dont_items": ["夸大效果"],
        "reference_ids": ["benchmark-post-001"],
    }
    excluded = excluded_rules or []
    missing = missing_information or []
    machine_summary = {
        "profile_id": "creator-main",
        "profile_version": 2,
        "task_constraints": task_constraints,
        "usable_rule_ids": [item["rule_id"] for item in usable_rules],
        "excluded_rule_ids": [item["rule_id"] for item in excluded],
        "usable_rules": usable_rules,
        "excluded_rules": excluded,
        "risk_warnings": ["避免对象过宽。"],
        "missing_information": missing,
        "status_category": status,
        "reference_asset_ids": [item["asset_id"] for item in reference_assets or []],
        "reference_assets": reference_assets or [],
    }
    return GenerationContext(
        status_category=status,
        profile={
            "profile_name": "主账号",
            "positioning": "职场新人表达成长",
            "target_audience": ["职场新人"],
            "goals": ["提升收藏"],
            "content_formats": ["图文"],
        },
        task_constraints=task_constraints,
        usable_rules=usable_rules,
        excluded_rules=excluded,
        risk_warnings=["避免对象过宽。"],
        missing_information=missing,
        user_summary="测试上下文摘要。",
        machine_summary=machine_summary,
        reference_assets=reference_assets or [],
    )


def make_rule(rule_id: str, rule_type: str, summary: str) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "rule_version": 1,
        "rule_type": rule_type,
        "summary": summary,
        "status": "approved",
        "strength": "medium",
        "applicable_scenarios": ["图文标题"],
        "examples": ["给新人看的步骤清单"],
        "risks": ["避免对象过宽。"],
        "adaptation_notes": "适合当前账号。",
        "evidence_summaries": [{"observable_fact": "标题点名刚入职的新人。"}],
        "provenance_summaries": [],
        "decision_basis": "user_confirmed",
        "profile_alignment": "matched",
        "warnings": [],
    }


def make_reference_asset() -> dict[str, object]:
    return {
        "asset_id": "asset-opening",
        "asset_version": 2,
        "asset_type": "opening_template",
        "name": "结果优先开场",
        "template": "先说结果：{{result}}。再说过程：{{process}}。",
        "variables": ["result", "process"],
        "applicable_scope": ["AI 内容运营"],
        "limitations": ["不能夸大收益。"],
        "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
        "source_mechanism_ids": ["mechanism-result-framing"],
        "confidence_level": "medium",
    }


if __name__ == "__main__":
    unittest.main()
