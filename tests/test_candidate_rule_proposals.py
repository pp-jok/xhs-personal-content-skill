import sys
import unittest
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import BenchmarkAnalysis, CaptureRecord, CreatorProfile, RuleCard  # noqa: E402
from app.rules.candidate_proposals import CandidateProposalError, propose_candidate_rules  # noqa: E402
from app.rules.selection import select_active_rule_cards  # noqa: E402


class CandidateRuleProposalTests(unittest.TestCase):
    def test_directly_borrowable_proposal_creates_candidate_evidence_and_provenance(self) -> None:
        capture, analysis, profile = make_ready_records()

        result = propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])

        self.assertEqual(len(result["created_rules"]), 1)
        rule = result["created_rules"][0]
        self.assertEqual(rule.status, "candidate")
        self.assertEqual(rule.strength, "weak")
        self.assertEqual(rule.source_ids, [analysis.id, capture.id])
        self.assertEqual(len(result["created_evidence"]), 1)
        self.assertEqual(result["created_evidence"][0].observable_fact, capture.title)
        self.assertEqual(len(result["created_provenance"]), 2)
        self.assertEqual(select_active_rule_cards(result["created_rules"]), [])
        self.assertIn("待确认", result["user_summary"])

    def test_contract_failure_prevents_all_candidate_objects(self) -> None:
        capture, analysis, profile = make_ready_records()

        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, {"proposals": []}, [], [])

    def test_high_confidence_and_extra_top_level_contract_fields_are_rejected(self) -> None:
        capture, analysis, profile = make_ready_records()
        payload = valid_payload()
        payload["proposals"][0]["confidence"] = "high"

        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, payload, [], [])

        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, {"proposals": [], "extra": True}, [], [])

    def test_contract_rejects_missing_fields_and_more_than_three_proposals(self) -> None:
        capture, analysis, profile = make_ready_records()
        payload = valid_payload()
        del payload["proposals"][0]["scope"]
        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, payload, [], [])

        payload = valid_payload()
        payload["proposals"] = payload["proposals"] * 4
        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, payload, [], [])

    def test_missing_or_insufficient_account_fit_prevents_creation(self) -> None:
        capture, analysis, profile = make_ready_records()
        analysis.account_fit = {}

        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])

        capture, analysis, profile = make_ready_records()
        analysis.account_fit["status_category"] = "insufficient"
        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])

    def test_profile_version_mismatch_rejects_before_creation(self) -> None:
        capture, analysis, profile = make_ready_records()
        profile.version = 2

        with self.assertRaisesRegex(CandidateProposalError, "账号适配结果已不是当前账号档案版本"):
            propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])

    def test_evidence_must_stay_in_its_analysis_dimension(self) -> None:
        capture, analysis, profile = make_ready_records()
        payload = valid_payload()
        payload["proposals"][0]["evidence"][0]["dimension"] = "正文结构"

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

    def test_insufficient_account_fit_dimension_cannot_support_proposal(self) -> None:
        capture, analysis, profile = make_ready_records()
        analysis.account_fit["assessments"][0]["classification"] = "insufficient_information"

        with self.assertRaises(CandidateProposalError):
            propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])

    def test_adaptable_proposal_requires_an_explicit_adaptation_boundary(self) -> None:
        capture, analysis, profile = make_ready_records(classification="adaptable")
        payload = valid_payload()
        payload["proposals"][0]["limitations"] = []
        payload["proposals"][0]["not_applicable_when"] = []
        payload["proposals"][0]["account_fit_basis"] = ["目标受众明确出现：职场新人"]
        payload["proposals"][0]["rule_text"] = "标题直接使用具体目标人群表达。"

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

    def test_not_recommended_cannot_be_reversed_into_positive_rule(self) -> None:
        capture, analysis, profile = make_ready_records(classification="not_recommended")
        payload = valid_payload()
        payload["proposals"][0]["risk_notes"] = ["原表达与账号边界不一致"]
        payload["proposals"][0]["rule_text"] = "标题应该使用保证三天见效的承诺。"

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

    def test_risky_and_not_recommended_can_create_negative_rules(self) -> None:
        for classification in ("not_recommended", "risky"):
            capture, analysis, profile = make_ready_records(classification=classification)
            payload = valid_payload()
            payload["proposals"][0]["rule_text"] = "标题避免使用保证三天见效等绝对承诺。"
            payload["proposals"][0]["risk_notes"] = ["绝对承诺与账号边界不一致"]

            result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

            self.assertEqual(len(result["created_rules"]), 1)

    def test_risky_cannot_use_change_to_disguise_a_recommendation(self) -> None:
        capture, analysis, profile = make_ready_records(classification="risky")
        payload = valid_payload()
        payload["proposals"][0]["rule_text"] = "改为使用“一定成功”的表达。"
        payload["proposals"][0]["risk_notes"] = ["绝对承诺与账号边界不一致"]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")
        self.assertEqual(result["created_rules"], [])
        self.assertEqual(result["created_evidence"], [])
        self.assertEqual(result["created_provenance"], [])

    def test_not_recommended_cannot_use_change_to_disguise_a_recommendation(self) -> None:
        capture, analysis, profile = make_ready_records(classification="not_recommended")
        payload = valid_payload()
        payload["proposals"][0]["rule_text"] = "改为采用原帖中的强刺激标题。"
        payload["proposals"][0]["risk_notes"] = ["表达强度与账号边界不一致"]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

    def test_do_not_use_remains_a_negative_rule_despite_positive_action_word(self) -> None:
        capture, analysis, profile = make_ready_records(classification="risky")
        payload = valid_payload()
        payload["proposals"][0]["rule_text"] = "不要使用绝对承诺。"
        payload["proposals"][0]["risk_notes"] = ["绝对承诺与账号边界不一致"]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

        self.assertEqual(result["proposal_results"][0]["outcome"], "created")

    def test_adaptable_allows_change_when_a_boundary_is_present(self) -> None:
        capture, analysis, profile = make_ready_records(classification="adaptable")
        payload = valid_payload()
        payload["proposals"][0]["rule_text"] = "标题改为更具体的人群和问题描述。"

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

        self.assertEqual(result["proposal_results"][0]["outcome"], "created")

    def test_media_path_and_metrics_cannot_be_used_as_evidence(self) -> None:
        capture, analysis, profile = make_ready_records()
        capture.images = [{"path": "image.png", "remote_url": "https://example.test/image.png", "alt": "首图"}]
        analysis.cover_analysis = {"observable": {"image_count": 1}, "inference": "只有结构信息。"}
        analysis.account_fit["assessments"][0] = make_assessment("封面与图片", "directly_borrowable", "image.png")
        payload = valid_payload()
        payload["proposals"][0]["rule_type"] = "cover"
        payload["proposals"][0]["evidence"] = [{"dimension": "封面与图片", "observable_fact": "image.png"}]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

        capture, analysis, profile = make_ready_records()
        analysis.engagement_analysis = {"observable": {"likes": 100}, "inference": "仅供参考。"}
        analysis.account_fit["assessments"][0] = make_assessment("互动表现", "directly_borrowable", "100")
        payload = valid_payload()
        payload["proposals"][0]["rule_type"] = "operation"
        payload["proposals"][0]["evidence"] = [{"dimension": "互动表现", "observable_fact": "100"}]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")

    def test_comment_evidence_cannot_independently_create_a_long_term_candidate(self) -> None:
        capture, analysis, profile = make_ready_records()
        capture.comments = [{"content": "职场新人想学习汇报"}]
        analysis.comment_analysis = {"observable": capture.comments, "inference": "评论可作为有限线索。"}
        analysis.account_fit["assessments"].append(make_assessment("评论", "directly_borrowable", "职场新人想学习汇报"))
        payload = valid_payload()
        payload["proposals"][0]["evidence"] = [{"dimension": "评论", "observable_fact": "职场新人想学习汇报"}]

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")
        self.assertIn("单条评论不足", result["proposal_results"][0]["reasons"][0])

    def test_exact_duplicate_active_rule_is_not_created_or_given_new_evidence(self) -> None:
        capture, analysis, profile = make_ready_records()
        for status in ("candidate", "approved", "testing", "validated"):
            existing = make_rule(summary="标题先明确具体目标人群，再说明需要解决的问题。", status=status)
            result = propose_candidate_rules(capture, analysis, profile, valid_payload(), [existing], [])

            self.assertEqual(result["created_rules"], [])
            self.assertEqual(result["created_evidence"], [])
            self.assertEqual(result["created_provenance"], [])
            self.assertEqual(result["proposal_results"][0]["outcome"], "duplicate")

    def test_duplicate_proposals_in_same_payload_create_only_one_rule(self) -> None:
        capture, analysis, profile = make_ready_records()
        first = valid_payload()["proposals"][0]
        second = deepcopy(first)
        second["scope"] = ["标题", "职场新人 内容！"]

        result = propose_candidate_rules(capture, analysis, profile, {"proposals": [first, second]}, [], [])

        self.assertEqual(len(result["created_rules"]), 1)
        self.assertEqual(len(result["created_evidence"]), 1)
        self.assertEqual(len(result["created_provenance"]), 2)
        self.assertEqual([item["outcome"] for item in result["proposal_results"]], ["created", "duplicate"])
        self.assertIsNone(result["proposal_results"][1]["rule"])
        self.assertNotIn("rule-", result["user_summary"])

    def test_same_text_with_different_scope_in_same_payload_is_not_exact_duplicate(self) -> None:
        capture, analysis, profile = make_ready_records()
        first = valid_payload()["proposals"][0]
        second = deepcopy(first)
        second["scope"] = ["另一类内容", "标题"]

        result = propose_candidate_rules(capture, analysis, profile, {"proposals": [first, second]}, [], [])

        self.assertEqual(len(result["created_rules"]), 2)
        self.assertEqual([item["outcome"] for item in result["proposal_results"]], ["created", "created"])

    def test_rejected_duplicate_allows_a_new_candidate_with_history_warning(self) -> None:
        capture, analysis, profile = make_ready_records()
        original = propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])
        existing = original["created_rules"][0]
        existing.status = "rejected"

        result = propose_candidate_rules(capture, analysis, profile, valid_payload(), [existing], [])

        self.assertEqual(len(result["created_rules"]), 1)
        self.assertNotEqual(result["created_rules"][0].id, existing.id)
        self.assertIn("曾被拒绝", "\n".join(result["proposal_results"][0]["warnings"]))

    def test_punctuation_case_duplicate_is_blocked_but_scope_difference_is_not(self) -> None:
        capture, analysis, profile = make_ready_records()
        existing = make_rule(summary="标题先明确具体目标人群, 再说明需要解决的问题。", status="candidate")
        result = propose_candidate_rules(capture, analysis, profile, valid_payload(), [existing], [])
        self.assertEqual(result["proposal_results"][0]["outcome"], "duplicate")

        existing.applicable_scenarios = ["视频脚本"]
        result = propose_candidate_rules(capture, analysis, profile, valid_payload(), [existing], [])
        self.assertEqual(len(result["created_rules"]), 1)

    def test_user_summary_hides_internal_identifiers_and_statuses(self) -> None:
        capture, analysis, profile = make_ready_records()
        summary = propose_candidate_rules(capture, analysis, profile, valid_payload(), [], [])["user_summary"]

        for forbidden in ("candidate", "approved", "rule-", "evidence-", "provenance-", "source_profile_id", ".json", "/Users/"):
            self.assertNotIn(forbidden, summary)
        for required in ("候选规则", "帖子证据", "账号适配依据", "风险或限制", "待确认", "尚未生效"):
            self.assertIn(required, summary)

    def test_explicit_content_format_conflict_is_rejected_without_blocking_other_proposals(self) -> None:
        capture, analysis, profile = make_ready_records()
        invalid = valid_payload()["proposals"][0]
        invalid["scope"] = ["视频内容"]
        valid = valid_payload()["proposals"][0]
        valid["rule_text"] = "标题先说明职场新人，再明确需要解决的问题。"
        payload = {"proposals": [invalid, valid]}

        result = propose_candidate_rules(capture, analysis, profile, payload, [], [])

        self.assertEqual(result["proposal_results"][0]["outcome"], "rejected")
        self.assertEqual(result["proposal_results"][1]["outcome"], "created")
        self.assertEqual(len(result["created_rules"]), 1)


def make_ready_records(classification: str = "directly_borrowable") -> tuple[CaptureRecord, BenchmarkAnalysis, CreatorProfile]:
    profile = CreatorProfile(
        id="creator-main",
        name="主账号",
        positioning="帮助职场新人提升表达能力",
        target_audience=["职场新人"],
        content_style=["具体", "克制"],
        forbidden_expressions=["保证"],
        goals=["建立信任"],
        content_formats=["图文"],
        publish_frequency="每周 3 次",
        notes="测试账号。",
    )
    capture = CaptureRecord(
        id="capture-proposal",
        inbox_item_id="inbox-proposal",
        source_url="https://example.test/note",
        capture_status="success",
        title="职场新人如何准备第一次工作汇报",
        body="先说明汇报对象，再给出三个当天可完成的准备步骤。",
        content_type="image",
        metrics={},
    )
    analysis = BenchmarkAnalysis(
        id="analysis-proposal",
        capture_id=capture.id,
        title_analysis={"observable": capture.title, "inference": "标题明确说明适用对象和问题。"},
        structure_analysis={"observable": capture.body, "inference": "正文按对象和步骤展开。"},
    )
    analysis.account_fit = {
        "status_category": "complete",
        "source_profile_id": profile.id,
        "source_profile_version": profile.version,
        "assessments": [make_assessment("标题", classification, capture.title)],
    }
    return capture, analysis, profile


def make_assessment(element: str, classification: str, evidence: str) -> dict[str, object]:
    return {
        "element": element,
        "classification": classification,
        "post_evidence": [evidence],
        "profile_evidence": ["目标受众明确包含：职场新人"],
        "reason": "目标受众明确出现：职场新人",
        "adaptation_guidance": "保留已验证的方法，用自己的内容重新表达。",
    }


def valid_payload() -> dict[str, object]:
    return {
        "proposals": [
            {
                "rule_text": "标题先明确具体目标人群，再说明需要解决的问题。",
                "rule_type": "title",
                "scope": ["职场新人内容", "标题"],
                "applicable_when": ["内容面向明确的职场新人群体"],
                "not_applicable_when": ["内容没有明确目标人群"],
                "evidence": [{"dimension": "标题", "observable_fact": "职场新人如何准备第一次工作汇报"}],
                "account_fit_basis": ["目标受众明确出现：职场新人"],
                "limitations": ["单篇帖子证据，仍需更多样本验证"],
                "risk_notes": [],
                "confidence": "low",
            }
        ]
    }


def make_rule(summary: str, status: str) -> RuleCard:
    return RuleCard(
        id=f"existing-{status}",
        name="已有规则",
        type="title",
        source_ids=["analysis-old"],
        applicable_scenarios=["职场新人内容", "标题", "内容面向明确的职场新人群体"],
        rule_summary=summary,
        examples=["例子"],
        risks=[],
        adaptation_notes="已有规则。",
        status=status,
    )


if __name__ == "__main__":
    unittest.main()
