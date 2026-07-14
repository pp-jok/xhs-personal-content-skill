from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.core import ContentAsset, CreatorProfile, DecisionRequest, ProvenanceRecord, RuleCard, RuleEvidence
from app.rules.selection import select_active_rule_cards


ACTIVE_STATUS_LABELS = {
    "approved": "已批准",
    "testing": "测试中",
    "validated": "已验证",
}
ALIGNMENT_LABELS = {
    "matched": "账号档案来源已匹配",
    "version_mismatch": "来源于当前账号档案的其他版本",
    "different_profile": "来源于其他账号档案",
    "missing": "没有可验证的账号档案来源",
}
EXCLUDED_REASONS = {
    "candidate": ("awaiting_user_confirmation", "尚未经过用户确认"),
    "rejected": ("rejected_by_lifecycle", "该规则已被拒绝"),
    "deprecated": ("deprecated", "该规则已废弃"),
}
ASSET_TYPE_LABELS = {
    "title_pattern": "标题模式",
    "cover_structure": "封面结构",
    "opening_template": "开头模板",
    "body_structure": "正文结构",
    "cta_template": "行动引导模板",
    "comparison_framework": "对比框架",
    "case_framework": "案例框架",
    "image_text_structure": "图文结构",
    "topic_framework": "选题框架",
}


@dataclass(frozen=True)
class GenerationTaskConstraints:
    intent: str = ""
    content_type: str = ""
    topic_area: str = ""
    target_audiences: list[str] = field(default_factory=list)
    content_format: str = ""
    tone: str = ""
    length: str = ""
    do_items: list[str] = field(default_factory=list)
    dont_items: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_cli_values(
        cls,
        *,
        intent: str = "",
        content_type: str = "",
        topic_area: str = "",
        target_audiences: list[str] | None = None,
        content_format: str = "",
        tone: str = "",
        length: str = "",
        do_items: list[str] | None = None,
        dont_items: list[str] | None = None,
        reference_ids: list[str] | None = None,
    ) -> "GenerationTaskConstraints":
        return cls(
            intent=clean_text(intent),
            content_type=clean_text(content_type),
            topic_area=clean_text(topic_area),
            target_audiences=unique_clean_texts(target_audiences or []),
            content_format=clean_text(content_format),
            tone=clean_text(tone),
            length=clean_text(length),
            do_items=unique_clean_texts(do_items or []),
            dont_items=unique_clean_texts(dont_items or []),
            reference_ids=unique_clean_texts(reference_ids or []),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "content_type": self.content_type,
            "topic_area": self.topic_area,
            "target_audiences": list(self.target_audiences),
            "content_format": self.content_format,
            "tone": self.tone,
            "length": self.length,
            "do_items": list(self.do_items),
            "dont_items": list(self.dont_items),
            "reference_ids": list(self.reference_ids),
        }


@dataclass(frozen=True)
class GenerationContext:
    status_category: str
    profile: dict[str, object]
    task_constraints: dict[str, object]
    usable_rules: list[dict[str, object]]
    excluded_rules: list[dict[str, object]]
    risk_warnings: list[str]
    missing_information: list[str]
    user_summary: str
    machine_summary: dict[str, object]
    reference_assets: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "status_category": self.status_category,
            "profile": self.profile,
            "task_constraints": self.task_constraints,
            "usable_rules": self.usable_rules,
            "excluded_rules": self.excluded_rules,
            "reference_assets": self.reference_assets,
            "risk_warnings": self.risk_warnings,
            "missing_information": self.missing_information,
            "user_summary": self.user_summary,
            "machine_summary": self.machine_summary,
        }


def build_reference_asset_snapshots(reference_assets: list[ContentAsset]) -> list[dict[str, object]]:
    if len(reference_assets) > 1:
        raise ValueError("一次生成最多显式引用 1 个 active 内容资产。")
    return [asset_reference_snapshot(asset) for asset in reference_assets]


def asset_reference_snapshot(asset: ContentAsset) -> dict[str, object]:
    if not isinstance(asset, ContentAsset):
        raise ValueError("引用资产必须是 ContentAsset。")
    asset.validate()
    if asset.status != "active":
        raise ValueError("只有 active 内容资产可以被显式引用进入生成。")
    return {
        "asset_id": asset.id,
        "asset_version": asset.version,
        "asset_type": asset.asset_type,
        "name": asset.name,
        "description": asset.description,
        "template": asset.template,
        "variables": list(asset.variables),
        "scope": list(asset.applicable_scope),
        "applicable_scope": list(asset.applicable_scope),
        "exclusions": list(asset.exclusions),
        "usage_notes": list(asset.usage_notes),
        "limitations": list(asset.limitations),
        "examples": list(asset.examples),
        "evidence_facts": list(asset.selected_observed_facts),
        "selected_observed_facts": list(asset.selected_observed_facts),
        "creator_profile_id": asset.creator_profile_id,
        "source_mechanism_ids": list(asset.source_mechanism_ids),
        "account_fit_reason": asset.account_fit_reason,
        "confidence_level": asset.confidence_level,
    }


def build_generation_context(
    *,
    profile: CreatorProfile,
    rules: list[RuleCard],
    evidence: list[RuleEvidence],
    provenance: list[ProvenanceRecord],
    decisions: list[DecisionRequest],
    task_constraints: GenerationTaskConstraints,
    reference_assets: list[ContentAsset] | None = None,
) -> GenerationContext:
    active_ids = {rule.id for rule in select_active_rule_cards(rules, allow_candidate_ids=[])}
    evidence_by_rule = group_evidence(evidence)
    provenance_by_rule = group_provenance(provenance)
    decisions_by_rule = group_decisions(decisions)
    risk_warnings: list[str] = []
    missing_information: list[str] = []

    usable_rules: list[dict[str, object]] = []
    for rule in sorted((item for item in rules if item.id in active_ids), key=rule_sort_key):
        rule_evidence = evidence_by_rule.get(rule.id, [])
        rule_provenance = provenance_by_rule.get(rule.id, [])
        related_decisions = decisions_by_rule.get(rule.id, [])
        alignment = profile_alignment(profile, rule_provenance)
        warnings: list[str] = []

        if not rule_evidence:
            warning = "当前规则没有独立证据记录"
            warnings.append(warning)
            append_unique(risk_warnings, warning)
            append_unique(missing_information, f"规则「{rule.rule_summary}」缺少独立证据记录")
        alignment_warning = alignment_warning_for(alignment)
        if alignment_warning:
            warnings.append(alignment_warning)
            append_unique(risk_warnings, alignment_warning)
            append_unique(missing_information, missing_text_for_alignment(rule.rule_summary, alignment))
        if any(decision.status == "pending" for decision in related_decisions):
            warning = "该规则仍关联未完成的待决记录"
            warnings.append(warning)
            append_unique(risk_warnings, warning)

        for risk in rule.risks:
            append_unique(risk_warnings, risk)

        usable_rules.append(
            {
                "rule_id": rule.id,
                "rule_version": rule.version,
                "rule_type": rule.type,
                "summary": rule.rule_summary,
                "status": rule.status,
                "strength": rule.strength,
                "applicable_scenarios": list(rule.applicable_scenarios),
                "examples": list(rule.examples),
                "risks": list(rule.risks),
                "adaptation_notes": rule.adaptation_notes,
                "evidence_summaries": [evidence_summary(item) for item in sorted(rule_evidence, key=evidence_sort_key)],
                "provenance_summaries": [provenance_summary(item) for item in sorted(rule_provenance, key=provenance_sort_key)],
                "decision_basis": decision_basis_for(rule, related_decisions),
                "profile_alignment": alignment,
                "warnings": unique_texts(warnings),
            }
        )

    excluded_rules = [
        excluded_rule_summary(rule)
        for rule in sorted((item for item in rules if item.id not in active_ids), key=rule_sort_key)
    ]
    if not usable_rules:
        append_unique(risk_warnings, "当前没有可用规则")
        append_unique(missing_information, "没有可用规则")
    for expression in profile.forbidden_expressions:
        append_unique(risk_warnings, expression)

    status_category = "ready"
    if not usable_rules or missing_information:
        status_category = "limited"

    profile_summary = profile_to_summary(profile)
    constraints = task_constraints.to_dict()
    asset_references = build_reference_asset_snapshots(reference_assets or [])
    machine_summary = {
        "profile_id": profile.id,
        "profile_version": profile.version,
        "task_constraints": constraints,
        "reference_asset_ids": [item["asset_id"] for item in asset_references],
        "reference_assets": asset_references,
        "usable_rule_ids": [item["rule_id"] for item in usable_rules],
        "excluded_rule_ids": [item["rule_id"] for item in excluded_rules],
        "usable_rules": usable_rules,
        "excluded_rules": excluded_rules,
        "risk_warnings": list(risk_warnings),
        "missing_information": list(missing_information),
        "status_category": status_category,
    }
    user_summary = build_generation_context_user_summary(
        profile=profile,
        task_constraints=constraints,
        usable_rules=usable_rules,
        excluded_rules=excluded_rules,
        reference_assets=asset_references,
        risk_warnings=risk_warnings,
        missing_information=missing_information,
        status_category=status_category,
    )
    return GenerationContext(
        status_category=status_category,
        profile=profile_summary,
        task_constraints=constraints,
        usable_rules=usable_rules,
        excluded_rules=excluded_rules,
        reference_assets=asset_references,
        risk_warnings=risk_warnings,
        missing_information=missing_information,
        user_summary=user_summary,
        machine_summary=machine_summary,
    )


def build_generation_context_user_summary(
    *,
    profile: CreatorProfile,
    task_constraints: dict[str, object],
    usable_rules: list[dict[str, object]],
    excluded_rules: list[dict[str, object]],
    reference_assets: list[dict[str, object]],
    risk_warnings: list[str],
    missing_information: list[str],
    status_category: str,
) -> str:
    lines = [
        "【中央生成上下文】",
        "",
        "账号档案：",
        f"{profile.name}：{profile.positioning}",
        f"档案版本：第 {profile.version} 版",
        "",
        "本次任务：",
    ]
    task_lines = task_constraint_lines(task_constraints)
    lines.extend(task_lines or ["未提供额外任务约束"])
    lines.extend(["", "可使用规则："])
    if usable_rules:
        for index, rule in enumerate(usable_rules, start=1):
            evidence = rule["evidence_summaries"]
            first_evidence = "无独立证据记录" if not evidence else str(evidence[0]["observable_fact"])  # type: ignore[index]
            lines.extend(
                [
                    f"{index}. {rule['summary']}",
                    f"   状态：{ACTIVE_STATUS_LABELS[str(rule['status'])]}",
                    f"   适用场景：{'、'.join(rule['applicable_scenarios']) or '未标明'}",
                    f"   证据：{first_evidence}",
                    f"   风险：{'；'.join(rule['risks']) or '未标明'}",
                    f"   账号匹配：{ALIGNMENT_LABELS[str(rule['profile_alignment'])]}",
                ]
            )
    else:
        lines.append("暂无可使用规则。")

    lines.extend(["", "排除规则："])
    if excluded_rules:
        for rule in excluded_rules:
            lines.append(f"- {rule['summary']}：{rule['reason']}")
    else:
        lines.append("没有被排除的规则。")

    lines.extend(["", "显式引用资产："])
    if reference_assets:
        for asset in reference_assets:
            label = ASSET_TYPE_LABELS.get(str(asset["asset_type"]), "内容资产")
            lines.append(f"- {asset['name']}（{label}，第 {asset['asset_version']} 版）")
    else:
        lines.append("未显式引用内容资产。")

    if profile.forbidden_expressions:
        lines.extend(["", "需要避免："])
        lines.extend(f"- {item}" for item in profile.forbidden_expressions)

    lines.extend(["", "风险与缺失信息："])
    issues = unique_texts(list(risk_warnings) + list(missing_information))
    if issues:
        lines.extend(f"- {item}" for item in issues)
    else:
        lines.append("未发现影响上下文可信度的缺失信息。")

    status_label = "可直接使用" if status_category == "ready" else "可使用但有限制"
    lines.extend(["", f"上下文状态：{status_label}"])
    return "\n".join(lines)


def profile_to_summary(profile: CreatorProfile) -> dict[str, object]:
    return {
        "profile_id": profile.id,
        "profile_version": profile.version,
        "name": profile.name,
        "platform": profile.platform,
        "positioning": profile.positioning,
        "target_audience": list(profile.target_audience),
        "content_style": list(profile.content_style),
        "forbidden_expressions": list(profile.forbidden_expressions),
        "goals": list(profile.goals),
        "content_formats": list(profile.content_formats),
        "publish_frequency": profile.publish_frequency,
    }


def excluded_rule_summary(rule: RuleCard) -> dict[str, object]:
    reason_code, reason = EXCLUDED_REASONS.get(rule.status, ("not_active", "当前规则不可用于生成"))
    return {
        "rule_id": rule.id,
        "summary": rule.rule_summary,
        "status": rule.status,
        "reason_code": reason_code,
        "reason": reason,
    }


def evidence_summary(evidence: RuleEvidence) -> dict[str, object]:
    return {
        "source_type": evidence.source_type,
        "source_id": evidence.source_id,
        "source_fragment": evidence.source_fragment,
        "observable_fact": evidence.observable_fact,
        "inference": evidence.inference,
    }


def provenance_summary(provenance: ProvenanceRecord) -> dict[str, object]:
    return {
        "source_object_type": provenance.source_object_type,
        "source_object_id": provenance.source_object_id,
        "source_version": provenance.source_version,
        "actor": provenance.actor,
        "artifact_nature": provenance.artifact_nature,
        "method": provenance.method,
        "note": provenance.note,
    }


def profile_alignment(profile: CreatorProfile, provenance: list[ProvenanceRecord]) -> str:
    profile_records = [item for item in provenance if item.source_object_type == "creator_profile"]
    if any(item.source_object_id == profile.id and item.source_version == profile.version for item in profile_records):
        return "matched"
    if any(item.source_object_id == profile.id and item.source_version != profile.version for item in profile_records):
        return "version_mismatch"
    if profile_records:
        return "different_profile"
    return "missing"


def alignment_warning_for(alignment: str) -> str:
    if alignment == "version_mismatch":
        return "该规则来源于当前账号档案的其他版本"
    if alignment == "different_profile":
        return "该规则来源于其他账号档案"
    if alignment == "missing":
        return "当前规则没有可验证的账号档案来源"
    return ""


def missing_text_for_alignment(summary: str, alignment: str) -> str:
    if alignment == "version_mismatch":
        return f"规则「{summary}」来源于当前账号档案的其他版本"
    if alignment == "different_profile":
        return f"规则「{summary}」来源于其他账号档案"
    return f"规则「{summary}」缺少账号档案来源记录"


def decision_basis_for(rule: RuleCard, decisions: list[DecisionRequest]) -> str:
    if any(item.status == "confirmed" and item.resolved_by == "user" for item in decisions):
        return "user_confirmed"
    if rule.status in {"testing", "validated"}:
        return "testing_or_validated"
    return "lifecycle_approved_without_decision"


def group_evidence(evidence: list[RuleEvidence]) -> dict[str, list[RuleEvidence]]:
    grouped: dict[str, list[RuleEvidence]] = {}
    for item in evidence:
        grouped.setdefault(item.rule_id, []).append(item)
    return grouped


def group_provenance(provenance: list[ProvenanceRecord]) -> dict[str, list[ProvenanceRecord]]:
    grouped: dict[str, list[ProvenanceRecord]] = {}
    for item in provenance:
        if item.target_object_type == "rule_card":
            grouped.setdefault(item.target_object_id, []).append(item)
    return grouped


def group_decisions(decisions: list[DecisionRequest]) -> dict[str, list[DecisionRequest]]:
    grouped: dict[str, list[DecisionRequest]] = {}
    for item in decisions:
        if item.target_object_type == "rule_card":
            grouped.setdefault(item.target_object_id, []).append(item)
    return grouped


def rule_sort_key(rule: RuleCard) -> tuple[str, str, str, str]:
    return (rule.type, " ".join(rule.applicable_scenarios), rule.rule_summary, rule.id)


def evidence_sort_key(evidence: RuleEvidence) -> tuple[str, str, str, str]:
    return (evidence.source_type, evidence.source_id, evidence.observable_fact, evidence.id)


def provenance_sort_key(provenance: ProvenanceRecord) -> tuple[str, str, int, str]:
    return (provenance.source_object_type, provenance.source_object_id, provenance.source_version, provenance.id)


def task_constraint_lines(constraints: dict[str, object]) -> list[str]:
    labels = {
        "intent": "意图",
        "content_type": "内容类型",
        "topic_area": "选题方向",
        "target_audiences": "目标受众",
        "content_format": "形式",
        "tone": "语气",
        "length": "长度",
        "do_items": "要做",
        "dont_items": "不要做",
        "reference_ids": "参考标识",
    }
    lines = []
    for key, label in labels.items():
        value = constraints[key]
        if isinstance(value, list):
            if value:
                lines.append(f"- {label}：{'、'.join(str(item) for item in value)}")
        elif value:
            lines.append(f"- {label}：{value}")
    return lines


def clean_text(value: str) -> str:
    return value.strip() if isinstance(value, str) else ""


def unique_clean_texts(values: list[str]) -> list[str]:
    return unique_texts([clean_text(value) for value in values if clean_text(value)])


def unique_texts(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)
