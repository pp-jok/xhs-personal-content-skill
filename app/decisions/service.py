from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Callable

from app.models.core import DecisionRequest, RuleCard, RuleEvidence, now_iso


QUESTION = "是否采用这条候选规则？"
CONFIRM_OPTION = "确认使用"
REJECT_OPTION = "暂不使用"
OPTION_OUTCOMES = {CONFIRM_OPTION: "confirmed", REJECT_OPTION: "rejected"}
RECOMMENDATION_REASON = "这条规则目前仍是单篇或有限证据形成的候选，建议先保留证据，暂不进入正式规则。"


class CandidateRuleDecisionError(ValueError):
    """Raised when a candidate-rule decision cannot be safely handled."""


@dataclass(frozen=True)
class CandidateRuleDecisionCreation:
    decision: DecisionRequest
    reused_existing: bool
    user_summary: str


@dataclass(frozen=True)
class PendingCandidateRuleDecisions:
    items: list[str]
    stale_count: int


@dataclass(frozen=True)
class CandidateRuleDecisionResolution:
    original_rule: RuleCard
    rule: RuleCard
    decision: DecisionRequest
    user_summary: str


def create_candidate_rule_decision(
    rule: RuleCard,
    decisions: list[DecisionRequest],
    user_note: str = "",
) -> CandidateRuleDecisionCreation:
    if rule.status != "candidate":
        raise CandidateRuleDecisionError("这条规则当前不是待确认状态，不能创建新的决定。")
    if rule.version < 1:
        raise CandidateRuleDecisionError("这条规则版本无效，暂不能创建决定。")

    existing = next(
        (
            item
            for item in decisions
            if item.target_object_type == "rule_card"
            and item.target_object_id == rule.id
            and item.status == "pending"
        ),
        None,
    )
    if existing is not None:
        return CandidateRuleDecisionCreation(
            decision=existing,
            reused_existing=True,
            user_summary="已有待处理决定，本次未重复创建。",
        )

    decision = DecisionRequest(
        id=build_decision_id(rule.id),
        target_object_type="rule_card",
        target_object_id=rule.id,
        question=QUESTION,
        options=[CONFIRM_OPTION, REJECT_OPTION],
        option_outcomes=OPTION_OUTCOMES,
        recommendation=REJECT_OPTION,
        recommendation_reason=RECOMMENDATION_REASON,
        impact="确认使用后会进入已批准状态；暂不使用后会进入已拒绝状态，证据和来源记录会保留。",
        expected_target_version=rule.version,
        user_note=user_note,
        created_by="codex",
        source_type="candidate_rule",
        created_from="create-rule-decision",
    )
    return CandidateRuleDecisionCreation(
        decision=decision,
        reused_existing=False,
        user_summary="已准备一项候选规则决定。建议暂不使用：这条规则目前仍是单篇或有限证据形成的候选。",
    )


def build_decision_id(rule_id: str) -> str:
    return "decision-rule-" + sha1(rule_id.encode("utf-8")).hexdigest()[:12]


def list_pending_candidate_rule_decisions(
    decisions: list[DecisionRequest],
    rules: list[RuleCard],
    evidence: list[RuleEvidence],
) -> PendingCandidateRuleDecisions:
    rules_by_id = {rule.id: rule for rule in rules}
    evidence_by_rule: dict[str, list[RuleEvidence]] = {}
    for item in evidence:
        evidence_by_rule.setdefault(item.rule_id, []).append(item)

    items: list[str] = []
    stale_count = 0
    for decision in decisions:
        if decision.target_object_type != "rule_card" or decision.status != "pending":
            continue
        rule = rules_by_id.get(decision.target_object_id)
        if not is_executable_pending_decision(decision, rule):
            stale_count += 1
            continue
        assert rule is not None
        items.append(build_pending_summary(decision, rule, evidence_by_rule.get(rule.id, [])))
    return PendingCandidateRuleDecisions(items=items, stale_count=stale_count)


def build_candidate_rule_decision_detail(
    decision: DecisionRequest,
    rule: RuleCard,
    evidence: list[RuleEvidence],
) -> str:
    if decision.target_object_type != "rule_card" or decision.target_object_id != rule.id:
        raise CandidateRuleDecisionError("该待决记录不属于候选规则决策，不能通过此入口查看。")
    if rule.status not in {"candidate", "approved", "rejected"}:
        raise CandidateRuleDecisionError("这条规则当前不能通过候选规则决定入口查看。")

    evidence_lines = evidence_lines_for(rule, evidence)
    if decision.status == "pending":
        executable = is_executable_pending_decision(decision, rule)
        lines = [
            "【需要你决定】",
            f"问题：{decision.question}",
            f"规则：{rule.rule_summary}",
            f"适用场景：{'、'.join(rule.applicable_scenarios) or '当前已验证场景'}",
            "帖子证据：",
            *evidence_lines,
            f"风险或限制：{'；'.join(rule.risks) or rule.adaptation_notes}",
            "账号适配依据：该候选规则已通过创建时的账号边界检查；当前持久化记录未保存独立的适配依据快照。",
            f"推荐：{decision.recommendation}",
            f"推荐理由：{decision.recommendation_reason}",
            "确认使用：规则会进入已批准状态，并可被后续有效规则选择流程使用。",
            "暂不使用：规则会进入已拒绝状态，证据和来源记录继续保留。",
            f"当前状态：{'可以作出决定' if executable else '这项决定已失效，暂不能执行'}",
        ]
        return "\n".join(lines)

    result = "已批准状态，可以被后续有效规则选择流程使用。" if rule.status == "approved" else "已拒绝状态，不会进入有效规则选择；已有证据和来源记录仍然保留。"
    return "\n".join(
        [
            "【决定已完成】",
            f"你的选择：{decision.selected_option}",
            f"结果：这条规则{result}",
            f"规则：{rule.rule_summary}",
            "帖子证据：",
            *evidence_lines,
            f"风险或限制：{'；'.join(rule.risks) or rule.adaptation_notes}",
            f"你的备注：{decision.user_note or '无'}",
            f"完成时间：{decision.resolved_at or '未记录'}",
        ]
    )


def resolve_candidate_rule_decision(
    decision: DecisionRequest,
    rule: RuleCard,
    selected_option: str,
    user_note: str,
    related_decisions: list[DecisionRequest],
) -> CandidateRuleDecisionResolution:
    validate_resolve_request(decision, rule, selected_option, related_decisions)
    outcome = decision.option_outcomes[selected_option]
    target_status = "approved" if outcome == "confirmed" else "rejected"
    timestamp = now_iso()
    updated_rule = copy_rule(rule, status=target_status, updated_at=timestamp)
    updated_decision = copy_decision(
        decision,
        status=outcome,
        selected_option=selected_option,
        user_note=user_note,
        resolved_at=timestamp,
        resolved_by="user",
        resulting_state_changes=[
            {
                "object_type": "rule_card",
                "field": "status",
                "from": "candidate",
                "to": target_status,
            }
        ],
        updated_at=timestamp,
    )
    result_text = (
        "这条规则已进入已批准状态，可以被后续有效规则选择流程使用。"
        if target_status == "approved"
        else "这条规则已进入已拒绝状态，不会进入有效规则选择；已有证据和来源记录仍然保留。"
    )
    summary = "\n".join(
        [
            "【决定已完成】",
            f"你的选择：{selected_option}",
            f"结果：{result_text}",
            f"规则：{rule.rule_summary}",
            f"你的备注：{user_note or '无'}",
        ]
    )
    return CandidateRuleDecisionResolution(rule, updated_rule, updated_decision, summary)


def persist_candidate_rule_decision_resolution(
    result: CandidateRuleDecisionResolution,
    save_rule: Callable[[RuleCard], RuleCard],
    save_decision: Callable[[DecisionRequest], DecisionRequest],
    restore_rule: Callable[[RuleCard], RuleCard],
) -> CandidateRuleDecisionResolution:
    try:
        saved_rule = save_rule(result.rule)
    except Exception as exc:
        raise CandidateRuleDecisionError("规则状态保存失败，本次未完成。") from exc
    try:
        saved_decision = save_decision(result.decision)
    except Exception as exc:
        try:
            restore_rule(result.original_rule)
        except Exception as restore_exc:
            raise CandidateRuleDecisionError(
                "决定记录保存失败，且规则恢复失败，需要人工检查当前规则状态。"
            ) from restore_exc
        raise CandidateRuleDecisionError("决定记录保存失败，本次未完成。") from exc
    return CandidateRuleDecisionResolution(result.original_rule, saved_rule, saved_decision, result.user_summary)


def validate_resolve_request(
    decision: DecisionRequest,
    rule: RuleCard,
    selected_option: str,
    related_decisions: list[DecisionRequest],
) -> None:
    if decision.target_object_type != "rule_card" or decision.target_object_id != rule.id:
        raise CandidateRuleDecisionError("该待决记录不属于候选规则决定。")
    if decision.status != "pending":
        raise CandidateRuleDecisionError("这项决定已完成，不能再次处理。")
    if selected_option not in decision.options or selected_option not in decision.option_outcomes:
        raise CandidateRuleDecisionError("请选择页面提供的完整选项。")
    if decision.option_outcomes[selected_option] not in {"confirmed", "rejected"}:
        raise CandidateRuleDecisionError("该选项不能用于候选规则决定。")
    if rule.status != "candidate":
        raise CandidateRuleDecisionError("候选规则状态已发生变化，这条待决事项已失效。")
    if decision.expected_target_version is None:
        raise CandidateRuleDecisionError("这条待决事项缺少规则版本信息，暂不能执行。")
    if rule.version != decision.expected_target_version:
        raise CandidateRuleDecisionError("候选规则版本已变化，这条待决事项已失效。")
    if any(
        item.id != decision.id
        and item.target_object_type == "rule_card"
        and item.target_object_id == rule.id
        and item.status == "pending"
        for item in related_decisions
    ):
        raise CandidateRuleDecisionError("这条候选规则存在多个待处理决定，需要先由技术流程清理后再继续。")
    if any(
        item.id != decision.id
        and item.target_object_type == "rule_card"
        and item.target_object_id == rule.id
        and item.status in {"confirmed", "rejected"}
        for item in related_decisions
    ):
        raise CandidateRuleDecisionError("这条规则已有另一项已完成决定，需要人工检查后再处理。")


def is_executable_pending_decision(decision: DecisionRequest, rule: RuleCard | None) -> bool:
    return bool(
        rule
        and decision.expected_target_version is not None
        and decision.target_object_type == "rule_card"
        and decision.status == "pending"
        and rule.status == "candidate"
        and rule.version == decision.expected_target_version
    )


def build_pending_summary(decision: DecisionRequest, rule: RuleCard, evidence: list[RuleEvidence]) -> str:
    return "\n".join(
        [
            "【需要你决定】",
            f"要决定什么：{decision.question}",
            f"规则：{rule.rule_summary}",
            f"适用场景：{'、'.join(rule.applicable_scenarios) or '当前已验证场景'}",
            "帖子证据：",
            *evidence_lines_for(rule, evidence),
            f"风险或限制：{'；'.join(rule.risks) or rule.adaptation_notes}",
            f"推荐：{decision.recommendation}",
            f"推荐理由：{decision.recommendation_reason}",
            "确认使用：规则会进入已批准状态，并可被后续有效规则选择流程使用。",
            "暂不使用：规则会进入已拒绝状态，证据和来源记录继续保留。",
            "当前状态：等待你的决定",
        ]
    )


def evidence_lines_for(rule: RuleCard, evidence: list[RuleEvidence]) -> list[str]:
    facts = [item.observable_fact for item in evidence if item.rule_id == rule.id]
    facts = facts or rule.examples
    return [f"- {item}" for item in facts] or ["- 当前持久化记录没有可展示的帖子证据。"]


def copy_rule(rule: RuleCard, *, status: str, updated_at: str) -> RuleCard:
    data = rule.to_dict()
    data.update({"status": status, "version": rule.version + 1, "updated_at": updated_at})
    return RuleCard.from_dict(data)


def copy_decision(decision: DecisionRequest, **changes: object) -> DecisionRequest:
    data = decision.to_dict()
    data.update(changes)
    data["version"] = decision.version + 1
    return DecisionRequest.from_dict(data)
