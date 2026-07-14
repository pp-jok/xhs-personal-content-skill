from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
import re
from typing import Any, Callable

from app.models.core import ContentMechanism, CreatorProfile, ProvenanceRecord, RuleCard, RuleEvidence


RULE_TYPES = {"title", "structure", "topic", "cover", "script", "operation"}
CONFIDENCE_VALUES = {"low": 0.4, "medium": 0.6, "high": 0.8}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
ACTIVE_DUPLICATE_STATUSES = {"candidate", "approved", "testing", "validated"}
REQUIRED_FIELDS = {
    "rule_statement",
    "rule_type",
    "applicable_scope",
    "exclusions",
    "selected_observed_facts",
    "account_fit_reason",
    "limitations",
}
OPTIONAL_FIELDS = {"title", "risk_notes", "examples", "confidence_level"}
GENERIC_STATEMENTS = {"很好", "有价值", "值得使用", "值得借鉴", "适合学习", "内容优质"}
LIFECYCLE_WORDS = {"active", "approved", "testing", "validated", "rejected", "deprecated"}
PUNCTUATION = re.compile(r"[\s\.,;:!?，。；：！？、()（）\[\]【】'\"“”‘’<>《》]", re.UNICODE)


class MechanismRuleProposalError(ValueError):
    """Raised before mechanism rule proposal writes are considered successful."""


@dataclass
class MechanismRuleProposalResult:
    created: bool
    rule: RuleCard
    rule_evidence: list[RuleEvidence]
    provenance_records: list[ProvenanceRecord]
    warnings: list[str] = field(default_factory=list)
    duplicate_check: dict[str, Any] = field(default_factory=dict)
    user_summary: str = ""
    machine_summary: dict[str, Any] = field(default_factory=dict)


def propose_rule_from_mechanism(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    proposal_payload: dict[str, Any],
    existing_rules: list[RuleCard],
    existing_provenance: list[ProvenanceRecord],
) -> MechanismRuleProposalResult:
    if mechanism.status == "deprecated":
        raise MechanismRuleProposalError("该内容机制已废弃，不能继续转为候选规则。")
    if mechanism.status not in {"candidate", "active"}:
        raise MechanismRuleProposalError("该内容机制当前状态不支持转为候选规则。")

    proposal = validate_proposal_payload(proposal_payload, mechanism, profile)
    duplicate = find_exact_duplicate(proposal, existing_rules)
    duplicate_check = {"status": "none", "existing_rule_id": ""}
    warnings: list[str] = []
    if duplicate and duplicate.status in ACTIVE_DUPLICATE_STATUSES:
        raise MechanismRuleProposalError("已有相同候选或正式规则，本次不重复保存。")
    if duplicate and duplicate.status == "rejected":
        warnings.append("相同规则曾被拒绝；本次将作为新的待确认候选保留。")
        duplicate_check = {"status": "rejected_history", "existing_rule_id": duplicate.id}
    if duplicate and duplicate.status == "deprecated":
        warnings.append("相同规则曾被废弃；本次将作为新的待确认候选保留。")
        duplicate_check = {"status": "deprecated_history", "existing_rule_id": duplicate.id}

    same_source = find_same_mechanism_profile_candidate(mechanism, profile, existing_rules, existing_provenance)
    if same_source:
        raise MechanismRuleProposalError("同一机制和账号已经存在待确认候选规则，本次不重复保存。")

    rule = build_rule_card(mechanism, profile, proposal, existing_rules)
    evidence = build_rule_evidence(rule, mechanism, proposal)
    provenance = build_provenance_records(rule, mechanism, profile)
    for item in [rule, *evidence, *provenance]:
        item.validate()

    summary = build_user_summary(rule, proposal, mechanism, warnings)
    machine_summary = {
        "mechanism_id": mechanism.id,
        "mechanism_version": mechanism.version,
        "mechanism_status": mechanism.status,
        "profile_id": profile.id,
        "profile_version": profile.version,
        "rule_id": rule.id,
        "rule_status": rule.status,
        "rule_evidence_ids": [item.id for item in evidence],
        "provenance_ids": [item.id for item in provenance],
        "selected_observed_facts": list(proposal["selected_observed_facts"]),
        "applicable_scope": list(proposal["applicable_scope"]),
        "exclusions": list(proposal["exclusions"]),
        "limitations": list(proposal["limitations"]),
        "confidence_level": proposal["confidence_level"],
        "duplicate_check": duplicate_check,
        "warnings": warnings,
        "decision_request_created": False,
    }
    return MechanismRuleProposalResult(
        created=True,
        rule=rule,
        rule_evidence=evidence,
        provenance_records=provenance,
        warnings=warnings,
        duplicate_check=duplicate_check,
        user_summary=summary,
        machine_summary=machine_summary,
    )


def validate_proposal_payload(
    payload: dict[str, Any],
    mechanism: ContentMechanism,
    profile: CreatorProfile,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MechanismRuleProposalError("规则提案必须是一个 JSON object。")
    unknown = set(payload) - REQUIRED_FIELDS - OPTIONAL_FIELDS
    missing = REQUIRED_FIELDS - set(payload)
    if unknown or missing:
        raise MechanismRuleProposalError("规则提案字段不完整或包含不支持字段。")

    rule_statement = text(payload["rule_statement"])
    if not rule_statement:
        raise MechanismRuleProposalError("规则内容不能为空。")
    if normalized_text(rule_statement) == normalized_text(mechanism.name) or normalized_text(rule_statement) in {
        normalized_text(item) for item in GENERIC_STATEMENTS
    }:
        raise MechanismRuleProposalError("规则内容过于空泛，不能保存为候选规则。")
    if any(word in rule_statement for word in LIFECYCLE_WORDS):
        raise MechanismRuleProposalError("规则内容不能包含生命周期要求。")

    rule_type = text(payload["rule_type"])
    if rule_type not in RULE_TYPES:
        raise MechanismRuleProposalError("规则类型不受支持。")

    observed_facts = observed_facts_by_stripped_text(mechanism)
    selected = unique_required_list(payload["selected_observed_facts"], "selected_observed_facts")
    if len(selected) > 3:
        raise MechanismRuleProposalError("每次最多选择 3 条机制事实。")
    for fact in selected:
        if fact.strip() not in observed_facts:
            raise MechanismRuleProposalError("规则证据必须完全来自机制中的可观察事实。")

    account_fit_reason = text(payload["account_fit_reason"])
    if not account_fit_reason or is_generic_account_fit_reason(account_fit_reason):
        raise MechanismRuleProposalError("账号适配说明不足，暂不能转为候选规则。")
    if not has_account_fit_support(account_fit_reason, mechanism, profile):
        raise MechanismRuleProposalError("账号适配说明缺少来自账号档案或机制字段的明确支撑。")

    confidence_level = text(payload.get("confidence_level")) or mechanism.confidence_level
    if confidence_level not in CONFIDENCE_VALUES:
        raise MechanismRuleProposalError("置信度级别不受支持。")
    if CONFIDENCE_ORDER[confidence_level] > CONFIDENCE_ORDER[mechanism.confidence_level]:
        confidence_level = mechanism.confidence_level

    return {
        "rule_statement": rule_statement,
        "rule_type": rule_type,
        "applicable_scope": unique_required_list(payload["applicable_scope"], "applicable_scope"),
        "exclusions": optional_text_list(payload["exclusions"], "exclusions"),
        "selected_observed_facts": selected,
        "account_fit_reason": account_fit_reason,
        "limitations": optional_text_list(payload["limitations"], "limitations"),
        "risk_notes": optional_text_list(payload.get("risk_notes", []), "risk_notes"),
        "examples": optional_text_list(payload.get("examples", []), "examples"),
        "title": text(payload.get("title", "")),
        "confidence_level": confidence_level,
    }


def build_rule_card(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    proposal: dict[str, Any],
    existing_rules: list[RuleCard],
) -> RuleCard:
    base_id = stable_id("rule-mechanism", mechanism.id, profile.id, proposal["rule_statement"])
    rule_id = available_rule_id(base_id, existing_rules)
    return RuleCard(
        id=rule_id,
        name=proposal["title"] or f"候选{proposal['rule_type']}规则：{short_text(proposal['rule_statement'])}",
        type=proposal["rule_type"],
        source_ids=[mechanism.id, profile.id],
        applicable_scenarios=list(proposal["applicable_scope"]),
        rule_summary=proposal["rule_statement"],
        examples=list(proposal["selected_observed_facts"] or proposal["examples"]),
        risks=unique_texts(proposal["risk_notes"] + proposal["limitations"]),
        adaptation_notes=build_adaptation_notes(proposal),
        tags=["candidate", "evidence-grounded", "mechanism-derived", "pr-5b"],
        status="candidate",
        strength="weak",
        applicable_content_types=[],
        applicable_audiences=[
            audience for audience in profile.target_audience if audience and audience in proposal["account_fit_reason"]
        ],
        source_type="content_mechanism",
        source_note=mechanism.id,
        created_from="propose-rule-from-mechanism",
        confidence=CONFIDENCE_VALUES[proposal["confidence_level"]],
        created_by="codex",
    )


def build_rule_evidence(
    rule: RuleCard,
    mechanism: ContentMechanism,
    proposal: dict[str, Any],
) -> list[RuleEvidence]:
    index_by_fact = observed_facts_by_stripped_text(mechanism)
    return [
        RuleEvidence(
            id=stable_id("evidence-mechanism", rule.id, str(position), fact),
            rule_id=rule.id,
            source_type="content_mechanism",
            source_id=mechanism.id,
            source_fragment=f"evidence_summary.observed_facts[{index_by_fact[fact.strip()]}]",
            evidence_type="content_mechanism",
            observable_fact=fact,
            inference=f"该机制事实被结构化提案用于支持候选规则：“{proposal['rule_statement']}”。",
            confidence=CONFIDENCE_VALUES[proposal["confidence_level"]],
            source_note=mechanism.name,
            created_from="propose-rule-from-mechanism",
            created_by="codex",
        )
        for position, fact in enumerate(proposal["selected_observed_facts"], start=1)
    ]


def build_provenance_records(
    rule: RuleCard,
    mechanism: ContentMechanism,
    profile: CreatorProfile,
) -> list[ProvenanceRecord]:
    return [
        ProvenanceRecord(
            id=f"provenance-{rule.id}-mechanism",
            target_object_type="rule_card",
            target_object_id=rule.id,
            source_object_type="content_mechanism",
            source_object_id=mechanism.id,
            source_version=mechanism.version,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-rule-from-mechanism",
            note="候选规则基于已保存的内容机制。",
            created_by="codex",
            source_type="content_mechanism",
            source_note=mechanism.id,
            created_from="propose-rule-from-mechanism",
        ),
        ProvenanceRecord(
            id=f"provenance-{rule.id}-profile",
            target_object_type="rule_card",
            target_object_id=rule.id,
            source_object_type="creator_profile",
            source_object_id=profile.id,
            source_version=profile.version,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-rule-from-mechanism",
            note="候选规则已核对指定账号档案。",
            created_by="codex",
            source_type="creator_profile",
            source_note=profile.id,
            created_from="propose-rule-from-mechanism",
        ),
    ]


def persist_mechanism_rule_proposal(
    result: MechanismRuleProposalResult,
    *,
    create_rule: Callable[[RuleCard], RuleCard],
    create_evidence: Callable[[RuleEvidence], RuleEvidence],
    create_provenance: Callable[[ProvenanceRecord], ProvenanceRecord],
    delete_rule: Callable[[str], None],
    delete_evidence: Callable[[str], None],
    delete_provenance: Callable[[str], None],
) -> MechanismRuleProposalResult:
    created_rules: list[str] = []
    created_evidence: list[str] = []
    created_provenance: list[str] = []
    try:
        create_rule(result.rule)
        created_rules.append(result.rule.id)
        for evidence in result.rule_evidence:
            create_evidence(evidence)
            created_evidence.append(evidence.id)
        for provenance in result.provenance_records:
            create_provenance(provenance)
            created_provenance.append(provenance.id)
    except Exception as exc:
        rollback_errors: list[str] = []
        for record_id in reversed(created_provenance):
            try:
                delete_provenance(record_id)
            except Exception as rollback_exc:  # pragma: no cover - exact type depends on repository.
                rollback_errors.append(str(rollback_exc))
        for record_id in reversed(created_evidence):
            try:
                delete_evidence(record_id)
            except Exception as rollback_exc:  # pragma: no cover
                rollback_errors.append(str(rollback_exc))
        for record_id in reversed(created_rules):
            try:
                delete_rule(record_id)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if rollback_errors:
            raise MechanismRuleProposalError("候选规则写入失败，且回滚失败；需要人工检查本地数据。") from exc
        raise MechanismRuleProposalError("候选规则写入失败，已回滚本次创建内容。") from exc
    return result


def find_exact_duplicate(proposal: dict[str, Any], existing_rules: list[RuleCard]) -> RuleCard | None:
    key = duplicate_key(proposal["rule_statement"], proposal["rule_type"], proposal["applicable_scope"])
    for rule in existing_rules:
        if key == duplicate_key(rule.rule_summary, rule.type, rule.applicable_scenarios):
            return rule
    return None


def find_same_mechanism_profile_candidate(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    existing_rules: list[RuleCard],
    existing_provenance: list[ProvenanceRecord],
) -> RuleCard | None:
    candidate_ids = {rule.id for rule in existing_rules if rule.status == "candidate"}
    by_target: dict[str, set[tuple[str, str]]] = {}
    for item in existing_provenance:
        if item.target_object_type != "rule_card" or item.target_object_id not in candidate_ids:
            continue
        by_target.setdefault(item.target_object_id, set()).add((item.source_object_type, item.source_object_id))
    for rule in existing_rules:
        if rule.status != "candidate":
            continue
        if rule.source_type == "content_mechanism" and mechanism.id in rule.source_ids and profile.id in rule.source_ids:
            return rule
        sources = by_target.get(rule.id, set())
        if ("content_mechanism", mechanism.id) in sources and ("creator_profile", profile.id) in sources:
            return rule
    return None


def build_user_summary(
    rule: RuleCard,
    proposal: dict[str, Any],
    mechanism: ContentMechanism,
    warnings: list[str],
) -> str:
    evidence_limit = "；".join(proposal["limitations"] + proposal["risk_notes"])
    if mechanism.confidence_level == "low":
        evidence_limit = "；".join(unique_texts([evidence_limit, "来源机制置信度较低，需要更多样本验证"]))
    history = "；".join(warnings) if warnings else "未发现精确重复的生效规则；近义重复和语义冲突仍需人工判断。"
    return "\n".join(
        [
            "已创建 1 条候选规则，但尚未生效。",
            f"规则：{rule.rule_summary}",
            f"适用范围：{'、'.join(rule.applicable_scenarios)}",
            f"不适用范围：{'、'.join(proposal['exclusions']) or '暂未补充'}",
            f"为什么适合当前账号：{proposal['account_fit_reason']}",
            f"事实证据：{'；'.join(proposal['selected_observed_facts'])}",
            f"限制和风险：{evidence_limit or '单个机制来源，仍需人工确认。'}",
            f"与现有规则关系：{history}",
            "下一步：使用现有候选规则确认流程发起用户确认；确认前不会进入正式生成。",
        ]
    )


def build_adaptation_notes(proposal: dict[str, Any]) -> str:
    sections = [
        "账号适配依据：" + proposal["account_fit_reason"],
        "不适用范围：" + ("；".join(proposal["exclusions"]) if proposal["exclusions"] else "暂未补充"),
        "限制：" + ("；".join(proposal["limitations"]) if proposal["limitations"] else "暂未补充"),
    ]
    return "\n".join(sections)


def has_account_fit_support(reason: str, mechanism: ContentMechanism, profile: CreatorProfile) -> bool:
    sources = [
        profile.positioning,
        *profile.target_audience,
        *profile.content_style,
        *profile.goals,
        *profile.content_formats,
        profile.notes,
        mechanism.problem,
        mechanism.solution,
        *mechanism.applicable_scope,
        *mechanism.limitations,
    ]
    return any(source and (source in reason or reason in source) for source in sources)


def is_generic_account_fit_reason(reason: str) -> bool:
    return normalized_text(reason) in {normalized_text(item) for item in GENERIC_STATEMENTS | {"这条规则很好", "很适合账号"}}


def observed_facts_by_stripped_text(mechanism: ContentMechanism) -> dict[str, int]:
    facts = mechanism.evidence_summary.get("observed_facts", [])
    return {str(fact).strip(): index for index, fact in enumerate(facts)}


def unique_required_list(value: Any, field_name: str) -> list[str]:
    items = optional_text_list(value, field_name)
    if not items:
        raise MechanismRuleProposalError(f"{field_name} 不能为空。")
    return items


def optional_text_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise MechanismRuleProposalError(f"{field_name} 必须是文本列表。")
    cleaned: list[str] = []
    for item in value:
        item_text = text(item)
        if not item_text:
            raise MechanismRuleProposalError(f"{field_name} 不能包含空内容。")
        if item_text not in cleaned:
            cleaned.append(item_text)
    return cleaned


def duplicate_key(statement: str, rule_type: str, scope: list[str]) -> tuple[str, str, tuple[str, ...]]:
    normalized_scope = tuple(sorted(normalized_text(item) for item in scope if normalized_text(item)))
    return normalized_text(statement), rule_type, normalized_scope


def stable_id(*parts: str) -> str:
    digest = sha1("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{parts[0]}-{digest}"


def available_rule_id(base_id: str, existing_rules: list[RuleCard]) -> str:
    used = {rule.id for rule in existing_rules}
    if base_id not in used:
        return base_id
    index = 2
    while f"{base_id}-{index}" in used:
        index += 1
    return f"{base_id}-{index}"


def short_text(value: str, limit: int = 28) -> str:
    return value if len(value) <= limit else value[:limit].rstrip() + "..."


def unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = text(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def normalized_text(value: str) -> str:
    return PUNCTUATION.sub("", value.strip())


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
