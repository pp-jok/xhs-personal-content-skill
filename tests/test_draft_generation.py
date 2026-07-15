from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.generation.drafts import (  # noqa: E402
    DraftGenerationError,
    generate_draft_from_topic,
    resolve_draft_reference_assets,
    revise_draft_with_focus,
)
from app.models.core import ContentDraft, TopicItem, ValidationError  # noqa: E402


class DraftGenerationTests(unittest.TestCase):
    def test_topic_generates_one_draft_with_audit_diagnosis_and_safe_summary(self) -> None:
        topic = make_topic()

        result = generate_draft_from_topic(topic=topic)

        draft = result.draft
        self.assertIsInstance(draft, ContentDraft)
        self.assertEqual(draft.topic_id, topic.id)
        self.assertEqual(draft.source_profile_id, topic.source_profile_id)
        self.assertEqual(draft.source_profile_version, topic.source_profile_version)
        self.assertEqual(draft.source_rule_cards, topic.source_rule_cards)
        self.assertEqual(draft.generation_context_status, topic.generation_context_status)
        self.assertEqual(draft.task_constraints, topic.task_constraints)
        self.assertEqual(draft.risk_warnings, topic.risk_warnings)
        self.assertEqual(draft.missing_information, topic.missing_information)
        self.assertEqual(draft.parent_draft_id, "")
        self.assertEqual(draft.revision_focus, "")
        self.assertTrue(draft.titles)
        self.assertTrue(draft.cover_titles)
        self.assertTrue(draft.script)
        self.assertTrue(draft.shot_suggestions)
        self.assertIn("strengths", draft.diagnosis)
        self.assertIn("issues", draft.diagnosis)
        self.assertIn("suggested_revision_focuses", draft.diagnosis)
        self.assertGreaterEqual(len(draft.diagnosis["strengths"]), 1)
        self.assertGreaterEqual(len(draft.diagnosis["issues"]), 1)
        self.assertLessEqual(len(draft.diagnosis["issues"]), 3)
        self.assertGreaterEqual(len(draft.diagnosis["suggested_revision_focuses"]), 1)
        self.assertLessEqual(len(draft.diagnosis["suggested_revision_focuses"]), 3)
        json.dumps(result.machine_summary, ensure_ascii=False)
        self.assertEqual(result.machine_summary["draft_id"], draft.id)
        self.assertEqual(result.machine_summary["topic_id"], topic.id)
        self.assertEqual(result.machine_summary["source_profile_id"], topic.source_profile_id)
        self.assertEqual(result.machine_summary["source_rule_cards"], topic.source_rule_cards)
        self.assertEqual(result.machine_summary["diagnosis"], draft.diagnosis)
        for forbidden in forbidden_user_texts(topic.id, draft.id, *topic.source_rule_cards):
            self.assertNotIn(forbidden, result.user_summary)

    def test_draft_preserves_topic_reference_assets(self) -> None:
        asset_reference = make_reference_asset("asset-opening", 2)
        topic = make_topic(reference_assets=[asset_reference])

        result = generate_draft_from_topic(topic=topic)

        self.assertEqual(result.draft.reference_assets, [asset_reference])
        self.assertEqual(result.machine_summary["reference_asset_ids"], ["asset-opening"])
        self.assertEqual(result.machine_summary["reference_assets"], [asset_reference])

    def test_draft_accepts_explicit_reference_asset_without_mutating_topic(self) -> None:
        asset_reference = make_reference_asset("asset-opening", 2)
        topic = make_topic()
        before = topic.to_dict()

        result = generate_draft_from_topic(topic=topic, reference_assets=[asset_reference])

        self.assertEqual(result.draft.reference_assets, [asset_reference])
        self.assertEqual(topic.to_dict(), before)

    def test_generation_records_accept_zero_or_one_reference_asset(self) -> None:
        empty_topic = make_topic()
        single_topic = make_topic(reference_assets=[make_reference_asset("asset-opening", 2)])
        empty_draft = make_draft()
        single_draft = ContentDraft.from_dict(
            {
                **make_draft().to_dict(),
                "id": "draft-single-reference",
                "reference_assets": [make_reference_asset("asset-opening", 2)],
            }
        )

        self.assertEqual(empty_topic.reference_assets, [])
        self.assertEqual(len(single_topic.reference_assets), 1)
        self.assertEqual(empty_draft.reference_assets, [])
        self.assertEqual(len(single_draft.reference_assets), 1)

    def test_generation_records_reject_multiple_reference_assets(self) -> None:
        references = [make_reference_asset("asset-opening", 2), make_reference_asset("asset-cover", 1)]

        with self.assertRaises(ValidationError) as topic_error:
            make_topic(reference_assets=references)
        with self.assertRaises(ValidationError) as draft_error:
            ContentDraft.from_dict({**make_draft().to_dict(), "id": "draft-two-references", "reference_assets": references})

        self.assertIn("at most one", str(topic_error.exception))
        self.assertIn("at most one", str(draft_error.exception))
        self.assertNotIn("asset-opening", str(topic_error.exception))
        self.assertNotIn("asset-cover", str(draft_error.exception))

    def test_reference_asset_aliases_must_match(self) -> None:
        valid_reference = make_reference_asset("asset-opening", 2)
        reference_with_scope = {**valid_reference, "scope": list(valid_reference["applicable_scope"])}
        reference_with_evidence = {
            **valid_reference,
            "evidence_facts": list(valid_reference["selected_observed_facts"]),
        }

        self.assertEqual(make_topic(reference_assets=[reference_with_scope]).reference_assets[0]["scope"], ["AI 内容运营"])
        self.assertEqual(
            make_topic(reference_assets=[reference_with_evidence]).reference_assets[0]["evidence_facts"],
            ["标题先展示结果承诺，再说明使用的工具和流程"],
        )

        mismatched_scope = {**valid_reference, "scope": ["其他场景"]}
        mismatched_evidence = {**valid_reference, "evidence_facts": ["其他事实"]}
        with self.assertRaises(ValidationError) as scope_error:
            make_topic(reference_assets=[mismatched_scope])
        with self.assertRaises(ValidationError) as evidence_error:
            ContentDraft.from_dict(
                {**make_draft().to_dict(), "id": "draft-evidence-mismatch", "reference_assets": [mismatched_evidence]}
            )

        self.assertIn("scope aliases must match", str(scope_error.exception))
        self.assertIn("evidence aliases must match", str(evidence_error.exception))

    def test_draft_rejects_multiple_inherited_reference_assets(self) -> None:
        references = [make_reference_asset("asset-opening", 2), make_reference_asset("asset-cover", 1)]

        with self.assertRaises(DraftGenerationError) as inherited_error:
            resolve_draft_reference_assets(references, None)
        with self.assertRaises(DraftGenerationError) as explicit_error:
            resolve_draft_reference_assets(references, [make_reference_asset("asset-opening", 2)])

        self.assertIn("at most one", str(inherited_error.exception))
        self.assertIn("at most one", str(explicit_error.exception))

    def test_invalid_topic_data_fails_clearly(self) -> None:
        with self.assertRaises(DraftGenerationError) as caught:
            generate_draft_from_topic(topic=None)  # type: ignore[arg-type]

        self.assertIn("选题", str(caught.exception))

    def test_revision_with_focus_creates_new_draft_and_preserves_original(self) -> None:
        original = make_draft()
        before = original.to_dict()

        result = revise_draft_with_focus(draft=original, focus=" 开头更直接 ")

        revised = result.draft
        self.assertIsInstance(revised, ContentDraft)
        self.assertNotEqual(revised.id, original.id)
        self.assertEqual(revised.parent_draft_id, original.id)
        self.assertEqual(revised.revision_focus, "开头更直接")
        self.assertEqual(revised.topic_id, original.topic_id)
        self.assertEqual(revised.source_profile_id, original.source_profile_id)
        self.assertEqual(revised.source_profile_version, original.source_profile_version)
        self.assertEqual(revised.source_rule_cards, original.source_rule_cards)
        self.assertEqual(revised.generation_context_status, original.generation_context_status)
        self.assertEqual(revised.task_constraints, original.task_constraints)
        self.assertEqual(revised.risk_warnings, original.risk_warnings)
        self.assertEqual(revised.missing_information, original.missing_information)
        self.assertIn("开头更直接", revised.script)
        self.assertEqual(original.to_dict(), before)
        json.dumps(result.machine_summary, ensure_ascii=False)
        self.assertEqual(result.machine_summary["draft_id"], revised.id)
        self.assertEqual(result.machine_summary["parent_draft_id"], original.id)
        self.assertEqual(result.machine_summary["revision_focus"], "开头更直接")
        for forbidden in forbidden_user_texts(original.id, revised.id, *original.source_rule_cards):
            self.assertNotIn(forbidden, result.user_summary)

    def test_revision_empty_focus_fails_without_mutating_original(self) -> None:
        original = make_draft()
        before = original.to_dict()

        with self.assertRaises(DraftGenerationError) as caught:
            revise_draft_with_focus(draft=original, focus="   ")

        self.assertIn("focus", str(caught.exception))
        self.assertEqual(original.to_dict(), before)


def make_topic(**overrides: object) -> TopicItem:
    data = {
        "id": "topic-audit-001",
        "title": "新人入职前三天如何快速进入状态",
        "content_goal": "帮助刚入职的新人明确前三天行动",
        "content_format": "清单",
        "source_rule_cards": ["rule-a", "rule-b"],
        "reference_posts": ["benchmark-post-001"],
        "reason": "基于账号定位和已确认规则。",
        "status": "idea",
        "tags": ["新人入职", "图文"],
        "source_profile_id": "creator-main",
        "source_profile_version": 2,
        "generation_context_status": "limited",
        "task_constraints": {"topic_area": "新人入职", "content_type": "图文"},
        "risk_warnings": ["规则缺少独立证据记录"],
        "missing_information": ["规则缺少独立证据记录"],
        "reference_assets": [],
        "created_by": "codex",
    }
    data.update(overrides)
    return TopicItem.from_dict(data)


def make_draft() -> ContentDraft:
    return ContentDraft.from_dict(
        {
            "id": "draft-original",
            "topic_id": "topic-audit-001",
            "titles": ["新人入职前三天快速进入状态"],
            "cover_titles": ["前三天清单"],
            "script": "开头说明新人入职场景，再给出三步行动。",
            "shot_suggestions": ["问题场景", "三步清单"],
            "status": "draft",
            "tags": ["新人入职", "图文"],
            "source_profile_id": "creator-main",
            "source_profile_version": 2,
            "source_rule_cards": ["rule-a", "rule-b"],
            "generation_context_status": "limited",
            "task_constraints": {"topic_area": "新人入职", "content_type": "图文"},
            "risk_warnings": ["规则缺少独立证据记录"],
            "missing_information": ["规则缺少独立证据记录"],
            "reference_assets": [],
            "diagnosis": {
                "strengths": ["选题对象明确。"],
                "issues": ["开头还可以更直接。"],
                "suggested_revision_focuses": ["开头更直接"],
            },
            "created_by": "codex",
        }
    )


def make_reference_asset(asset_id: str, version: int) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "asset_version": version,
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


def forbidden_user_texts(*ids: str) -> list[str]:
    return [
        *ids,
        "ContentDraft",
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
        "blocked",
        "JSON",
        ".py",
        ".json",
        "/Users/",
    ]


if __name__ == "__main__":
    unittest.main()
