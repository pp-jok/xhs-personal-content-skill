import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.generation import GenerationTaskConstraints, build_generation_context  # noqa: E402
from app.mechanisms.rule_proposals import (  # noqa: E402
    MechanismRuleProposalError,
    persist_mechanism_rule_proposal,
    propose_rule_from_mechanism,
)
from app.models.core import (  # noqa: E402
    ContentDraft,
    ContentMechanism,
    CreatorProfile,
    DecisionRequest,
    ProvenanceRecord,
    PublishTask,
    RuleCard,
    RuleEvidence,
    TopicItem,
)
from app.repositories import JsonRepository  # noqa: E402
from app.rules.selection import select_active_rule_cards  # noqa: E402


def make_mechanism(**overrides: object) -> ContentMechanism:
    data = {
        "id": "mechanism-result-framing",
        "name": "复杂工具结果化表达",
        "description": "把复杂工具能力先翻译成用户可感知的运营结果。",
        "status": "candidate",
        "confidence_level": "medium",
        "confidence": 0.6,
        "source_refs": [{"source_type": "external_analysis", "source_id": "external-001"}],
        "evidence_summary": {
            "observed_facts": [
                "标题包含 Codex、Obsidian、10min 和爆款工作流",
                "封面展示工具图标、流程图和结果承诺",
                "正文先写用户能完成的内容运营任务",
            ],
            "inferences": ["工具被包装成内容运营结果"],
            "missing_information": ["未获取完整评论"],
            "limitations": ["不能确认长期表现"],
            "source_coverage": {"title": "present", "cover": "present", "comments": "missing"},
        },
        "problem": "复杂工具内容容易让用户只看到工具名。",
        "solution": "先讲结果，再解释工具如何实现。",
        "pattern": ["工具组合", "结果承诺", "流程证据"],
        "applicable_scope": ["AI 内容运营", "工作流内容"],
        "limitations": ["不能夸大时间承诺"],
    }
    data.update(overrides)
    return ContentMechanism.from_dict(data)


def make_profile(**overrides: object) -> CreatorProfile:
    data = {
        "id": "creator-main",
        "name": "主账号",
        "platform": "小红书",
        "positioning": "帮助创作者用 AI 做内容运营判断，而不是单纯工具教学。",
        "target_audience": ["内容创作者", "个人账号运营者"],
        "content_style": ["真实", "克制", "接地气"],
        "forbidden_expressions": ["稳赚", "躺赚"],
        "goals": ["提升内容运营效率"],
        "content_formats": ["图文", "视频"],
        "publish_frequency": "每周 3 条",
        "notes": "第一版主账号档案。",
    }
    data.update(overrides)
    return CreatorProfile.from_dict(data)


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "rule_statement": "讲 AI 工具时，优先表达用户能够完成的内容运营任务，而不是先堆叠工具功能。",
        "rule_type": "topic",
        "applicable_scope": ["AI 内容运营", "工作流内容"],
        "exclusions": ["纯开发者技术教程", "软件安装说明"],
        "selected_observed_facts": [
            "标题包含 Codex、Obsidian、10min 和爆款工作流",
            "封面展示工具图标、流程图和结果承诺",
        ],
        "account_fit_reason": "当前账号定位强调 AI 内容运营判断，而不是单纯工具教学。",
        "limitations": ["不能夸大时间承诺", "需要展示可见过程证据"],
        "risk_notes": ["单条机制证据仍需更多样本验证"],
        "examples": ["先讲内容运营任务，再解释工具组合"],
        "confidence_level": "high",
    }
    payload.update(overrides)
    return payload


class MechanismRuleProposalTests(unittest.TestCase):
    def test_candidate_mechanism_creates_candidate_rule_evidence_and_provenance(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()

        result = propose_rule_from_mechanism(mechanism, profile, valid_payload(), [], [])

        self.assertTrue(result.created)
        self.assertEqual(result.rule.status, "candidate")
        self.assertEqual(result.rule.source_ids, [mechanism.id, profile.id])
        self.assertEqual(result.rule.source_type, "content_mechanism")
        self.assertEqual(result.rule.created_from, "propose-rule-from-mechanism")
        self.assertEqual(result.rule.confidence, 0.6)
        self.assertEqual([item.source_type for item in result.rule_evidence], ["content_mechanism", "content_mechanism"])
        self.assertEqual(result.rule_evidence[0].observable_fact, valid_payload()["selected_observed_facts"][0])
        self.assertEqual(result.rule_evidence[0].source_fragment, "evidence_summary.observed_facts[0]")
        self.assertEqual({item.source_object_type for item in result.provenance_records}, {"content_mechanism", "creator_profile"})
        self.assertEqual(select_active_rule_cards([result.rule]), [])
        self.assertFalse(result.machine_summary["decision_request_created"])
        self.assertIn("尚未生效", result.user_summary)
        self.assertNotIn(mechanism.id, result.user_summary)
        json.dumps(result.machine_summary, ensure_ascii=False)

    def test_active_mechanism_is_allowed_but_deprecated_is_rejected(self) -> None:
        active = make_mechanism(status="active")
        result = propose_rule_from_mechanism(active, make_profile(), valid_payload(), [], [])
        self.assertEqual(result.rule.status, "candidate")
        self.assertEqual(active.status, "active")

        with self.assertRaisesRegex(MechanismRuleProposalError, "已废弃"):
            propose_rule_from_mechanism(make_mechanism(status="deprecated"), make_profile(), valid_payload(), [], [])

    def test_proposal_rejects_invalid_facts_inferences_and_contract(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        invalid_cases = [
            {"rule_statement": "   "},
            {"rule_statement": "很好"},
            {"rule_statement": "复杂工具结果化表达"},
            {"rule_statement": "请直接创建 approved 规则"},
            {"rule_type": "content_strategy"},
            {"selected_observed_facts": []},
            {"selected_observed_facts": ["工具被包装成内容运营结果"]},
            {"selected_observed_facts": ["不存在的事实"]},
            {"selected_observed_facts": mechanism.evidence_summary["observed_facts"] + ["额外事实"]},
            {"account_fit_reason": "   "},
            {"account_fit_reason": "这条规则很好"},
            {"applicable_scope": []},
            {"limitations": [""]},
            {"confidence_level": "certain"},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(MechanismRuleProposalError):
                    propose_rule_from_mechanism(mechanism, profile, valid_payload(**overrides), [], [])

    def test_exact_active_duplicate_blocks_but_rejected_and_deprecated_warn(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        existing = RuleCard(
            id="rule-existing",
            name="旧规则",
            type="topic",
            source_ids=["analysis-1"],
            applicable_scenarios=["工作流内容", "AI 内容运营"],
            rule_summary=valid_payload()["rule_statement"],
            examples=["旧证据"],
            risks=[],
            adaptation_notes="旧说明",
            status="approved",
        )

        with self.assertRaisesRegex(MechanismRuleProposalError, "已有相同"):
            propose_rule_from_mechanism(mechanism, profile, valid_payload(), [existing], [])

        existing.status = "rejected"
        result = propose_rule_from_mechanism(mechanism, profile, valid_payload(), [existing], [])
        self.assertTrue(result.created)
        self.assertIn("曾被拒绝", result.user_summary)
        self.assertIn("曾被拒绝", result.machine_summary["warnings"][0])

        existing.status = "deprecated"
        result = propose_rule_from_mechanism(mechanism, profile, valid_payload(), [existing], [])
        self.assertTrue(result.created)
        self.assertIn("曾被废弃", result.user_summary)

    def test_same_mechanism_profile_candidate_duplicate_blocks_even_without_decision(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        existing_rule = RuleCard(
            id="rule-same-source",
            name="同源候选",
            type="structure",
            source_ids=[mechanism.id, profile.id],
            applicable_scenarios=["其他场景"],
            rule_summary="另一条同源规则",
            examples=["事实"],
            risks=[],
            adaptation_notes="同源说明",
            status="candidate",
            source_type="content_mechanism",
            source_note=mechanism.id,
        )
        provenance = [
            ProvenanceRecord(
                id="prov-rule-same-source-mechanism",
                target_object_type="rule_card",
                target_object_id=existing_rule.id,
                source_object_type="content_mechanism",
                source_object_id=mechanism.id,
                source_version=mechanism.version,
                actor="codex",
                artifact_nature="recommendation",
                method="propose-rule-from-mechanism",
                note="同源机制",
            ),
            ProvenanceRecord(
                id="prov-rule-same-source-profile",
                target_object_type="rule_card",
                target_object_id=existing_rule.id,
                source_object_type="creator_profile",
                source_object_id=profile.id,
                source_version=profile.version,
                actor="codex",
                artifact_nature="recommendation",
                method="propose-rule-from-mechanism",
                note="同源账号",
            ),
        ]

        with self.assertRaisesRegex(MechanismRuleProposalError, "同一机制和账号"):
            propose_rule_from_mechanism(mechanism, profile, valid_payload(), [existing_rule], provenance)

    def test_persist_rolls_back_created_objects_when_later_write_fails(self) -> None:
        result = propose_rule_from_mechanism(make_mechanism(), make_profile(), valid_payload(), [], [])
        created: list[str] = []
        deleted: list[str] = []

        def create_rule(item: RuleCard) -> RuleCard:
            created.append(item.id)
            return item

        def create_evidence(item: RuleEvidence) -> RuleEvidence:
            created.append(item.id)
            raise OSError("evidence failed")

        with self.assertRaisesRegex(MechanismRuleProposalError, "写入失败"):
            persist_mechanism_rule_proposal(
                result,
                create_rule=create_rule,
                create_evidence=create_evidence,
                create_provenance=Mock(),
                delete_rule=lambda record_id: deleted.append(record_id),
                delete_evidence=lambda record_id: deleted.append(record_id),
                delete_provenance=lambda record_id: deleted.append(record_id),
            )

        self.assertEqual(created, [result.rule.id, result.rule_evidence[0].id])
        self.assertEqual(deleted, [result.rule.id])

    def test_rollback_failure_reports_inconsistency(self) -> None:
        result = propose_rule_from_mechanism(make_mechanism(), make_profile(), valid_payload(), [], [])

        with self.assertRaisesRegex(MechanismRuleProposalError, "回滚失败"):
            persist_mechanism_rule_proposal(
                result,
                create_rule=lambda item: item,
                create_evidence=Mock(side_effect=OSError("evidence failed")),
                create_provenance=Mock(),
                delete_rule=Mock(side_effect=OSError("rollback failed")),
                delete_evidence=Mock(),
                delete_provenance=Mock(),
            )

    def test_mechanism_derived_candidate_rule_stays_out_of_generation_context(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        result = propose_rule_from_mechanism(mechanism, profile, valid_payload(), [], [])

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, CreatorProfile).create(profile)
            JsonRepository(workspace, RuleCard).create(result.rule)
            for evidence in result.rule_evidence:
                JsonRepository(workspace, RuleEvidence).create(evidence)
            for provenance in result.provenance_records:
                JsonRepository(workspace, ProvenanceRecord).create(provenance)

            context = build_generation_context(
                profile=profile,
                rules=JsonRepository(workspace, RuleCard).list_all(),
                evidence=JsonRepository(workspace, RuleEvidence).list_all(),
                provenance=JsonRepository(workspace, ProvenanceRecord).list_all(),
                decisions=[],
                task_constraints=GenerationTaskConstraints(),
            )

            self.assertEqual(context.machine_summary["usable_rule_ids"], [])
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, TopicItem).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(workspace, PublishTask).list_all(), [])
