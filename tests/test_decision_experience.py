from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.decisions import (  # noqa: E402
    CandidateRuleDecisionError,
    build_candidate_rule_decision_detail,
    create_candidate_rule_decision,
    list_pending_candidate_rule_decisions,
    persist_candidate_rule_decision_resolution,
    resolve_candidate_rule_decision,
)
from app.cli.main import restore_rule_card_exact  # noqa: E402
from app.models.core import DecisionRequest, RuleCard, ValidationError  # noqa: E402
from app.repositories import JsonRepository  # noqa: E402
from app.rules.selection import select_active_rule_cards  # noqa: E402


class CandidateRuleDecisionTests(unittest.TestCase):
    def test_create_candidate_rule_decision_uses_fixed_safe_contract(self) -> None:
        rule = make_candidate_rule()

        result = create_candidate_rule_decision(rule, [])

        self.assertFalse(result.reused_existing)
        self.assertEqual(result.decision.expected_target_version, rule.version)
        self.assertEqual(result.decision.options, ["确认使用", "暂不使用"])
        self.assertEqual(
            result.decision.option_outcomes,
            {"确认使用": "confirmed", "暂不使用": "rejected"},
        )
        self.assertEqual(result.decision.recommendation, "暂不使用")
        self.assertIn("单篇或有限证据", result.user_summary)
        self.assertNotIn(rule.id, result.user_summary)
        self.assertNotIn("candidate", result.user_summary)

    def test_create_reuses_any_pending_decision_for_same_candidate_rule(self) -> None:
        rule = make_candidate_rule()
        existing = make_decision(rule, question="另一个问题")

        result = create_candidate_rule_decision(rule, [existing])

        self.assertTrue(result.reused_existing)
        self.assertIs(result.decision, existing)

    def test_pending_list_hides_stale_records_and_keeps_safe_summary(self) -> None:
        rule = make_candidate_rule()
        current = make_decision(rule)
        stale = make_decision(make_candidate_rule("rule-stale"))
        stale.expected_target_version = 2

        result = list_pending_candidate_rule_decisions(
            [current, stale],
            [rule, make_candidate_rule("rule-stale")],
            [],
        )

        self.assertEqual(result.stale_count, 1)
        self.assertEqual(len(result.items), 1)
        self.assertIn("标题先明确", result.items[0])
        self.assertIn("确认使用", result.items[0])
        self.assertNotIn(rule.id, result.items[0])
        self.assertNotIn("pending", result.items[0])

    def test_detail_explains_pending_decision_without_internal_identifiers(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)

        detail = build_candidate_rule_decision_detail(decision, rule, [])

        self.assertIn("【需要你决定】", detail)
        self.assertIn("帖子证据", detail)
        self.assertIn("暂不使用", detail)
        self.assertNotIn(decision.id, detail)
        self.assertNotIn(rule.id, detail)
        self.assertNotIn("DecisionRequest", detail)

    def test_resolve_confirm_updates_rule_and_decision_with_actual_change(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)

        result = resolve_candidate_rule_decision(decision, rule, "确认使用", "适合账号。", [decision])

        self.assertEqual(result.rule.status, "approved")
        self.assertEqual(result.rule.version, 2)
        self.assertEqual(result.decision.status, "confirmed")
        self.assertEqual(result.decision.version, 2)
        self.assertEqual(result.decision.selected_option, "确认使用")
        self.assertEqual(result.decision.resolved_by, "user")
        self.assertEqual(
            result.decision.resulting_state_changes,
            [{"object_type": "rule_card", "field": "status", "from": "candidate", "to": "approved"}],
        )
        self.assertEqual(select_active_rule_cards([result.rule]), [result.rule])
        self.assertIn("已批准状态", result.user_summary)
        self.assertNotIn(rule.id, result.user_summary)

    def test_resolve_reject_keeps_rule_out_of_active_selection(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)

        result = resolve_candidate_rule_decision(decision, rule, "暂不使用", "先不采用。", [decision])

        self.assertEqual(result.rule.status, "rejected")
        self.assertEqual(result.decision.status, "rejected")
        self.assertEqual(select_active_rule_cards([result.rule]), [])
        self.assertIn("已拒绝状态", result.user_summary)

    def test_resolve_rejects_stale_version_without_mutation(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)
        rule.version = 2

        with self.assertRaisesRegex(CandidateRuleDecisionError, "版本已变化"):
            resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision])

        self.assertEqual(rule.status, "candidate")
        self.assertEqual(decision.status, "pending")

    def test_expected_target_version_accepts_none_or_positive_integer_only(self) -> None:
        rule = make_candidate_rule()
        self.assertIsNone(make_decision(rule, expected_target_version=None).expected_target_version)
        self.assertEqual(make_decision(rule, expected_target_version=1).expected_target_version, 1)
        old_data = make_decision(rule).to_dict()
        del old_data["expected_target_version"]
        self.assertIsNone(DecisionRequest.from_dict(old_data).expected_target_version)
        for value in (0, -1, "1"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                make_decision(rule, expected_target_version=value)

    def test_create_rejects_non_candidate_rule_without_creating_a_decision(self) -> None:
        rule = make_candidate_rule()
        rule.status = "approved"

        with self.assertRaisesRegex(CandidateRuleDecisionError, "不是待确认状态"):
            create_candidate_rule_decision(rule, [])

    def test_pending_list_counts_missing_and_changed_rule_as_stale(self) -> None:
        rule = make_candidate_rule()
        missing = make_decision(make_candidate_rule("rule-missing"))
        changed_rule = make_candidate_rule("rule-changed")
        changed = make_decision(changed_rule)
        changed_rule.status = "approved"

        result = list_pending_candidate_rule_decisions([missing, changed], [changed_rule], [])

        self.assertEqual(result.items, [])
        self.assertEqual(result.stale_count, 2)

    def test_resolve_rejects_missing_version_and_conflicting_history(self) -> None:
        rule = make_candidate_rule()
        missing_version = make_decision(rule, expected_target_version=None)
        with self.assertRaisesRegex(CandidateRuleDecisionError, "缺少规则版本"):
            resolve_candidate_rule_decision(missing_version, rule, "确认使用", "", [missing_version])

        decision = make_decision(rule)
        old = make_decision(rule, question="旧决定")
        old.id = "decision-old"
        old.status = "confirmed"
        old.selected_option = "确认使用"
        old.resolved_at = "2026-07-11T00:00:00Z"
        old.resolved_by = "user"
        with self.assertRaisesRegex(CandidateRuleDecisionError, "另一项已完成决定"):
            resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision, old])

    def test_resolve_rejects_any_of_two_pending_decisions_without_writes(self) -> None:
        rule = make_candidate_rule()
        first = make_decision(rule, question="第一个决定")
        second = make_decision(rule, question="第二个决定")
        second.id = "decision-second"

        for decision in (first, second):
            with self.subTest(decision=decision.id), self.assertRaisesRegex(
                CandidateRuleDecisionError, "多个待处理决定"
            ):
                resolve_candidate_rule_decision(decision, rule, "确认使用", "", [first, second])

        self.assertEqual(rule.status, "candidate")
        for decision in (first, second):
            self.assertEqual(decision.status, "pending")
            self.assertEqual(decision.selected_option, "")
            self.assertIsNone(decision.resolved_by)
            self.assertIsNone(decision.resolved_at)

    def test_resolution_compensates_when_decision_save_fails(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)
        result = resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision])
        save_rule = Mock(return_value=result.rule)
        save_decision = Mock(side_effect=OSError("decision write failed"))
        restore_rule = Mock(return_value=rule)

        with self.assertRaisesRegex(CandidateRuleDecisionError, "本次未完成"):
            persist_candidate_rule_decision_resolution(result, save_rule, save_decision, restore_rule)

        save_rule.assert_called_once_with(result.rule)
        restore_rule.assert_called_once_with(rule)

    def test_resolution_does_not_save_decision_when_rule_save_fails(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)
        result = resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision])
        save_decision = Mock()

        with self.assertRaisesRegex(CandidateRuleDecisionError, "规则状态保存失败"):
            persist_candidate_rule_decision_resolution(
                result,
                Mock(side_effect=OSError("rule write failed")),
                save_decision,
                Mock(),
            )

        save_decision.assert_not_called()

    def test_resolution_reports_inconsistency_when_compensation_fails(self) -> None:
        rule = make_candidate_rule()
        decision = make_decision(rule)
        result = resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision])

        with self.assertRaisesRegex(CandidateRuleDecisionError, "恢复失败"):
            persist_candidate_rule_decision_resolution(
                result,
                Mock(return_value=result.rule),
                Mock(side_effect=OSError("decision write failed")),
                Mock(side_effect=OSError("restore failed")),
            )

    def test_resolution_restores_exact_rule_after_second_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            rule = make_candidate_rule()
            decision = make_decision(rule)
            rule_repo = JsonRepository(workspace, RuleCard)
            decision_repo = JsonRepository(workspace, DecisionRequest)
            rule_repo.create(rule)
            decision_repo.create(decision)
            result = resolve_candidate_rule_decision(decision, rule, "确认使用", "", [decision])

            with self.assertRaisesRegex(CandidateRuleDecisionError, "本次未完成"):
                persist_candidate_rule_decision_resolution(
                    result,
                    lambda item: rule_repo.upsert(item, changed_by="user"),
                    lambda item: (_ for _ in ()).throw(OSError("decision write failed")),
                    lambda item: restore_rule_card_exact(workspace, item),
                )

            self.assertEqual(rule_repo.read(rule.id).to_dict(), rule.to_dict())
            self.assertEqual(decision_repo.read(decision.id).status, "pending")


def make_candidate_rule(rule_id: str = "rule-candidate") -> RuleCard:
    return RuleCard(
        id=rule_id,
        name="候选标题规则",
        type="title",
        source_ids=["analysis-001"],
        applicable_scenarios=["标题"],
        rule_summary="标题先明确具体目标人群。",
        examples=["职场新人如何准备第一次工作汇报"],
        risks=["单篇内容形成，仍需更多样本验证"],
        adaptation_notes="暂不适用于：没有明确目标人群的内容。",
        status="candidate",
        strength="weak",
        created_by="codex",
    )


def make_decision(
    rule: RuleCard,
    question: str = "是否采用这条候选规则？",
    expected_target_version: object = 1,
) -> DecisionRequest:
    return DecisionRequest(
        id=f"decision-{rule.id}",
        target_object_type="rule_card",
        target_object_id=rule.id,
        question=question,
        options=["确认使用", "暂不使用"],
        option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
        recommendation="暂不使用",
        recommendation_reason="有限证据。",
        impact="确认或拒绝。",
        expected_target_version=expected_target_version,  # type: ignore[arg-type]
        created_by="codex",
    )
