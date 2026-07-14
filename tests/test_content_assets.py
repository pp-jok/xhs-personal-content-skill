import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.generation import GenerationTaskConstraints, build_generation_context  # noqa: E402
from app.mechanisms.assets import (  # noqa: E402
    MechanismAssetProposalError,
    persist_mechanism_asset_proposal,
    propose_asset_from_mechanism,
)
from app.models.core import (  # noqa: E402
    ContentAsset,
    ContentAssetEvidence,
    ContentDraft,
    ContentMechanism,
    CreatorProfile,
    DecisionRequest,
    ProvenanceRecord,
    PublishTask,
    RuleCard,
    RuleEvidence,
    TopicItem,
    ValidationError,
)
from app.repositories import JsonRepository  # noqa: E402


ASSET_TYPES = [
    "title_pattern",
    "cover_structure",
    "opening_template",
    "body_structure",
    "cta_template",
    "comparison_framework",
    "case_framework",
    "image_text_structure",
    "topic_framework",
]


def make_mechanism(**overrides: object) -> ContentMechanism:
    data: dict[str, object] = {
        "id": "mechanism-result-framing",
        "name": "结果前置表达机制",
        "description": "先呈现用户可获得的内容运营结果，再解释工具和过程。",
        "status": "candidate",
        "confidence_level": "medium",
        "confidence": 0.6,
        "source_refs": [{"source_type": "external_analysis", "source_id": "external-001"}],
        "evidence_summary": {
            "observed_facts": [
                "标题先展示结果承诺，再说明使用的工具和流程",
                "正文先写用户能完成的内容运营任务",
                "封面突出可见流程和最终产物",
            ],
            "inferences": ["内容把复杂工具包装成结果"],
            "missing_information": ["未获取完整评论"],
            "limitations": ["不能确认长期表现"],
            "source_coverage": {"title": "present", "body": "present", "cover": "present"},
        },
        "problem": "复杂工具内容容易让用户只看到工具名。",
        "solution": "先讲结果，再解释工具如何实现。",
        "pattern": ["结果承诺", "过程说明", "产物展示"],
        "applicable_scope": ["AI 内容运营", "工作流介绍"],
        "limitations": ["不能夸大时间承诺"],
    }
    data.update(overrides)
    return ContentMechanism.from_dict(data)


def make_profile(**overrides: object) -> CreatorProfile:
    data: dict[str, object] = {
        "id": "creator-main",
        "name": "主账号",
        "platform": "小红书",
        "positioning": "帮助创作者用 AI 做内容运营判断。",
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
        "asset_type": "opening_template",
        "name": "任务结果优先开场",
        "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
        "template": "先说明你可以完成的结果：{{result}}。\n再说明实现过程：{{process}}。",
        "variables": ["result", "process"],
        "applicable_scope": ["AI 内容运营", "工作流介绍"],
        "exclusions": ["纯工具安装教程"],
        "usage_notes": ["先填具体结果，再填过程证据。"],
        "limitations": ["结果描述必须可验证", "不能夸大时间和收益"],
        "examples": ["先说明 10 分钟完成选题库，再说明工具流程。"],
        "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
        "account_fit_reason": "提案认为这适合当前账号的 AI 内容运营判断定位。",
        "confidence_level": "medium",
    }
    payload.update(overrides)
    return payload


class ContentAssetModelTests(unittest.TestCase):
    def test_content_asset_and_evidence_round_trip_and_registered_collections(self) -> None:
        asset = ContentAsset.from_dict(
            {
                "id": "asset-opening",
                "status": "candidate",
                "asset_type": "opening_template",
                "name": "任务结果优先开场",
                "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
                "template": "结果：{{result}}\n过程：{{process}}",
                "variables": ["result", "process"],
                "applicable_scope": ["AI 内容运营"],
                "exclusions": [],
                "usage_notes": [],
                "limitations": [],
                "examples": [],
                "creator_profile_id": "creator-main",
                "source_mechanism_ids": ["mechanism-result-framing"],
                "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
                "account_fit_reason": "提案中的账号适配理由。",
                "confidence_level": "medium",
                "confidence": 0.6,
                "created_from": "propose-asset-from-mechanism",
                "created_by": "codex",
            }
        )
        evidence = ContentAssetEvidence.from_dict(
            {
                "id": "asset-evidence-1",
                "asset_id": asset.id,
                "source_type": "content_mechanism",
                "source_id": "mechanism-result-framing",
                "source_version": 1,
                "source_fragment": "evidence_summary.observed_facts[0]",
                "evidence_text": "标题先展示结果承诺，再说明使用的工具和流程",
                "confidence_level": "medium",
                "confidence": 0.6,
                "created_by": "codex",
            }
        )

        self.assertEqual(ContentAsset.from_dict(asset.to_dict()).collection_name, "content-assets")
        self.assertEqual(ContentAssetEvidence.from_dict(evidence.to_dict()).collection_name, "content-asset-evidence")

    def test_content_asset_validates_status_types_template_variables_and_placeholders(self) -> None:
        base = {
            "id": "asset-opening",
            "status": "candidate",
            "asset_type": "opening_template",
            "name": "任务结果优先开场",
            "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
            "template": "结果：{{result}}\n过程：{{process}}",
            "variables": ["result", "process"],
            "applicable_scope": ["AI 内容运营"],
            "exclusions": [],
            "usage_notes": [],
            "limitations": [],
            "examples": [],
            "creator_profile_id": "creator-main",
            "source_mechanism_ids": ["mechanism-result-framing"],
            "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
            "account_fit_reason": "提案中的账号适配理由。",
            "confidence_level": "medium",
            "confidence": 0.6,
            "created_from": "propose-asset-from-mechanism",
            "created_by": "codex",
        }
        for asset_type in ASSET_TYPES:
            with self.subTest(asset_type=asset_type):
                self.assertEqual(ContentAsset.from_dict({**base, "asset_type": asset_type}).asset_type, asset_type)

        invalid_cases = [
            {"status": "draft"},
            {"asset_type": "generic"},
            {"template": "   "},
            {"template": "{{result}}", "variables": ["result"]},
            {"template": "结果：{{missing}}", "variables": ["result"]},
            {"template": "结果：{{result}}", "variables": ["result", "unused"]},
            {"template": "结果：{{}}", "variables": ["result"]},
            {"template": "结果：{{result", "variables": ["result"]},
            {"template": "结果：{{outer{{inner}}}}", "variables": ["outer"]},
            {"variables": ["result", "result"]},
            {"variables": ["结果"]},
            {"applicable_scope": []},
            {"name": "很好"},
            {"description": "通用模板"},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    ContentAsset.from_dict({**base, **overrides})

    def test_content_asset_evidence_rejects_non_mechanism_sources_and_bad_confidence(self) -> None:
        base = {
            "id": "asset-evidence-1",
            "asset_id": "asset-opening",
            "source_type": "content_mechanism",
            "source_id": "mechanism-result-framing",
            "source_version": 1,
            "source_fragment": "evidence_summary.observed_facts[0]",
            "evidence_text": "标题先展示结果承诺，再说明使用的工具和流程",
            "confidence_level": "medium",
            "confidence": 0.6,
        }
        self.assertEqual(ContentAssetEvidence.from_dict(base).source_type, "content_mechanism")
        with self.assertRaises(ValidationError):
            ContentAssetEvidence.from_dict({**base, "source_type": "rule_card"})
        with self.assertRaises(ValidationError):
            ContentAssetEvidence.from_dict({**base, "confidence_level": "high", "confidence": 0.6})


class MechanismAssetProposalTests(unittest.TestCase):
    def test_candidate_mechanism_creates_candidate_asset_evidence_and_provenance(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()

        result = propose_asset_from_mechanism(mechanism, profile, valid_payload(), [], [])

        self.assertTrue(result.created)
        self.assertEqual(result.asset.status, "candidate")
        self.assertEqual(result.asset.asset_type, "opening_template")
        self.assertEqual(result.asset.creator_profile_id, profile.id)
        self.assertEqual(result.asset.source_mechanism_ids, [mechanism.id])
        self.assertEqual(result.asset.confidence_level, "medium")
        self.assertEqual(len(result.asset_evidence), 1)
        self.assertEqual(result.asset_evidence[0].source_fragment, "evidence_summary.observed_facts[0]")
        self.assertEqual({item.source_object_type for item in result.provenance_records}, {"content_mechanism", "creator_profile"})
        self.assertFalse(result.machine_summary["generation_context_connected"])
        self.assertFalse(result.machine_summary["decision_request_created"])
        self.assertIn("候选内容资产", result.user_summary)
        self.assertNotIn(mechanism.id, result.user_summary)
        json.dumps(result.machine_summary, ensure_ascii=False)

    def test_active_mechanism_is_allowed_and_deprecated_mechanism_is_rejected(self) -> None:
        active = make_mechanism(status="active")
        result = propose_asset_from_mechanism(active, make_profile(), valid_payload(), [], [])
        self.assertEqual(result.asset.status, "candidate")
        self.assertEqual(active.status, "active")

        with self.assertRaisesRegex(MechanismAssetProposalError, "已废弃"):
            propose_asset_from_mechanism(make_mechanism(status="deprecated"), make_profile(), valid_payload(), [], [])

    def test_three_selected_facts_create_three_evidence_records(self) -> None:
        mechanism = make_mechanism()
        payload = valid_payload(selected_observed_facts=mechanism.evidence_summary["observed_facts"])

        result = propose_asset_from_mechanism(mechanism, make_profile(), payload, [], [])

        self.assertEqual(len(result.asset_evidence), 3)
        self.assertEqual([item.evidence_text for item in result.asset_evidence], mechanism.evidence_summary["observed_facts"])

    def test_confidence_defaults_to_mechanism_and_cannot_exceed_mechanism(self) -> None:
        low = make_mechanism(confidence_level="low", confidence=0.4)
        inherited = propose_asset_from_mechanism(low, make_profile(), valid_payload(confidence_level=None), [], [])
        self.assertEqual(inherited.asset.confidence_level, "low")
        self.assertEqual(inherited.asset.confidence, 0.4)

        with self.assertRaisesRegex(MechanismAssetProposalError, "置信度"):
            propose_asset_from_mechanism(low, make_profile(), valid_payload(confidence_level="medium"), [], [])

    def test_rejects_invalid_contract_facts_template_variables_and_hollow_content(self) -> None:
        mechanism = make_mechanism()
        invalid_cases = [
            {"extra": "field"},
            {"asset_type": "generic"},
            {"name": "推荐"},
            {"description": "很好"},
            {"template": ""},
            {"template": "{{result}}", "variables": ["result"]},
            {"template": "结果：{{missing}}", "variables": ["result"]},
            {"template": "结果：{{result}}", "variables": ["result", "unused"]},
            {"variables": ["result", "result"]},
            {"variables": ["result.name"]},
            {"applicable_scope": []},
            {"selected_observed_facts": []},
            {"selected_observed_facts": mechanism.evidence_summary["observed_facts"] + ["额外事实"]},
            {"selected_observed_facts": [mechanism.evidence_summary["observed_facts"][0], mechanism.evidence_summary["observed_facts"][0]]},
            {"selected_observed_facts": ["内容把复杂工具包装成结果"]},
            {"selected_observed_facts": ["未获取完整评论"]},
            {"account_fit_reason": ""},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(MechanismAssetProposalError):
                    propose_asset_from_mechanism(mechanism, make_profile(), valid_payload(**overrides), [], [])

    def test_exact_duplicate_and_same_source_duplicate_handling(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        existing = propose_asset_from_mechanism(mechanism, profile, valid_payload(), [], []).asset

        for status in ("candidate", "active"):
            with self.subTest(status=status):
                existing.status = status
                with self.assertRaisesRegex(MechanismAssetProposalError, "已有相同"):
                    propose_asset_from_mechanism(mechanism, profile, valid_payload(), [existing], [])

        existing.status = "deprecated"
        result = propose_asset_from_mechanism(mechanism, profile, valid_payload(), [existing], [])
        self.assertIn("曾被废弃", result.user_summary)
        self.assertIn("deprecated_history", result.duplicate_check["status"])

        mixed = [ContentAsset.from_dict({**existing.to_dict(), "id": "asset-old", "status": "deprecated"}), ContentAsset.from_dict({**existing.to_dict(), "id": "asset-active", "status": "active"})]
        with self.assertRaisesRegex(MechanismAssetProposalError, "已有相同"):
            propose_asset_from_mechanism(mechanism, profile, valid_payload(), mixed, [])

    def test_same_source_candidate_blocks_but_other_types_profiles_and_mechanisms_are_allowed(self) -> None:
        mechanism = make_mechanism()
        profile = make_profile()
        existing = propose_asset_from_mechanism(
            mechanism,
            profile,
            valid_payload(asset_type="title_pattern", template="标题：{{result}} 怎么做到", variables=["result"]),
            [],
            [],
        ).asset

        with self.assertRaisesRegex(MechanismAssetProposalError, "同一机制和账号"):
            propose_asset_from_mechanism(
                mechanism,
                profile,
                valid_payload(asset_type="title_pattern", template="另一个标题：{{result}}", variables=["result"]),
                [existing],
                [],
            )

        allowed_different_type = propose_asset_from_mechanism(mechanism, profile, valid_payload(), [existing], [])
        self.assertTrue(allowed_different_type.created)

        other_profile = make_profile(id="creator-other")
        allowed_different_profile = propose_asset_from_mechanism(mechanism, other_profile, valid_payload(), [], [])
        self.assertTrue(allowed_different_profile.created)

        other_mechanism = make_mechanism(id="mechanism-other")
        allowed_different_mechanism = propose_asset_from_mechanism(other_mechanism, profile, valid_payload(), [], [])
        self.assertTrue(allowed_different_mechanism.created)

    def test_persist_rolls_back_created_objects_and_preserves_existing_records(self) -> None:
        result = propose_asset_from_mechanism(make_mechanism(), make_profile(), valid_payload(), [], [])
        stores: dict[str, dict[str, object]] = {
            "assets": {"existing": object()},
            "evidence": {"existing": object()},
            "provenance": {"existing": object()},
        }
        before = {key: dict(value) for key, value in stores.items()}

        def create_asset(item: ContentAsset) -> ContentAsset:
            stores["assets"][item.id] = item
            return item

        def create_evidence(item: ContentAssetEvidence) -> ContentAssetEvidence:
            raise OSError("evidence failed")

        with self.assertRaisesRegex(MechanismAssetProposalError, "已回滚"):
            persist_mechanism_asset_proposal(
                result,
                create_asset=create_asset,
                create_evidence=create_evidence,
                create_provenance=lambda item: stores["provenance"].setdefault(item.id, item),
                delete_asset=lambda record_id: stores["assets"].pop(record_id),
                delete_evidence=lambda record_id: stores["evidence"].pop(record_id),
                delete_provenance=lambda record_id: stores["provenance"].pop(record_id),
            )
        self.assertEqual(stores, before)

    def test_persist_rolls_back_each_evidence_and_provenance_failure_position(self) -> None:
        mechanism = make_mechanism()
        result = propose_asset_from_mechanism(
            mechanism,
            make_profile(),
            valid_payload(selected_observed_facts=mechanism.evidence_summary["observed_facts"]),
            [],
            [],
        )

        for failure_kind, failure_position in [
            ("evidence", 1),
            ("evidence", 2),
            ("evidence", 3),
            ("provenance", 1),
            ("provenance", 2),
        ]:
            with self.subTest(failure_kind=failure_kind, failure_position=failure_position):
                stores: dict[str, dict[str, object]] = {"assets": {}, "evidence": {}, "provenance": {}}
                calls = {"evidence": 0, "provenance": 0}

                def create_evidence(item: ContentAssetEvidence) -> ContentAssetEvidence:
                    calls["evidence"] += 1
                    if failure_kind == "evidence" and calls["evidence"] == failure_position:
                        raise OSError("evidence failed")
                    stores["evidence"][item.id] = item
                    return item

                def create_provenance(item: ProvenanceRecord) -> ProvenanceRecord:
                    calls["provenance"] += 1
                    if failure_kind == "provenance" and calls["provenance"] == failure_position:
                        raise OSError("provenance failed")
                    stores["provenance"][item.id] = item
                    return item

                with self.assertRaisesRegex(MechanismAssetProposalError, "已回滚"):
                    persist_mechanism_asset_proposal(
                        result,
                        create_asset=lambda item: stores["assets"].setdefault(item.id, item),
                        create_evidence=create_evidence,
                        create_provenance=create_provenance,
                        delete_asset=lambda record_id: stores["assets"].pop(record_id),
                        delete_evidence=lambda record_id: stores["evidence"].pop(record_id),
                        delete_provenance=lambda record_id: stores["provenance"].pop(record_id),
                    )

                self.assertEqual(stores, {"assets": {}, "evidence": {}, "provenance": {}})

    def test_rollback_failure_reports_inconsistency_and_preserves_cause(self) -> None:
        result = propose_asset_from_mechanism(make_mechanism(), make_profile(), valid_payload(), [], [])

        with self.assertRaisesRegex(MechanismAssetProposalError, "回滚失败") as context:
            persist_mechanism_asset_proposal(
                result,
                create_asset=lambda item: item,
                create_evidence=Mock(side_effect=OSError("evidence failed")),
                create_provenance=Mock(),
                delete_asset=Mock(side_effect=OSError("rollback failed")),
                delete_evidence=Mock(),
                delete_provenance=Mock(),
            )
        self.assertIsInstance(context.exception.__cause__, OSError)

    def test_content_asset_boundaries_do_not_mutate_generation_or_other_business_objects(self) -> None:
        mechanism = make_mechanism(status="active")
        profile = make_profile()
        result = propose_asset_from_mechanism(mechanism, profile, valid_payload(), [], [])

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            JsonRepository(workspace, CreatorProfile).create(profile)
            JsonRepository(workspace, ContentMechanism).create(mechanism)
            JsonRepository(workspace, ContentAsset).create(result.asset)
            active_asset = ContentAsset.from_dict({**result.asset.to_dict(), "id": "asset-active", "status": "active"})
            JsonRepository(workspace, ContentAsset).create(active_asset)
            before_mechanism = JsonRepository(workspace, ContentMechanism).read(mechanism.id).to_dict()
            before_profile = JsonRepository(workspace, CreatorProfile).read(profile.id).to_dict()

            context = build_generation_context(
                profile=profile,
                rules=JsonRepository(workspace, RuleCard).list_all(),
                evidence=JsonRepository(workspace, RuleEvidence).list_all(),
                provenance=JsonRepository(workspace, ProvenanceRecord).list_all(),
                decisions=JsonRepository(workspace, DecisionRequest).list_all(),
                task_constraints=GenerationTaskConstraints(),
            )

            serialized = json.dumps(context.to_dict(), ensure_ascii=False)
            self.assertNotIn(result.asset.id, serialized)
            self.assertNotIn(active_asset.id, serialized)
            self.assertEqual(JsonRepository(workspace, ContentMechanism).read(mechanism.id).to_dict(), before_mechanism)
            self.assertEqual(JsonRepository(workspace, CreatorProfile).read(profile.id).to_dict(), before_profile)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, RuleCard).list_all(), [])
            self.assertEqual(JsonRepository(workspace, RuleEvidence).list_all(), [])
            self.assertEqual(JsonRepository(workspace, TopicItem).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentDraft).list_all(), [])
            self.assertEqual(JsonRepository(workspace, PublishTask).list_all(), [])


if __name__ == "__main__":
    unittest.main()
