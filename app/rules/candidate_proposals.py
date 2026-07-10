from __future__ import annotations

import hashlib
import re
from typing import Any

from app.analysis.outcome import build_analysis_outcome
from app.models.core import BenchmarkAnalysis, CaptureRecord, CreatorProfile, ProvenanceRecord, RuleCard, RuleEvidence


RULE_TYPES = {"title", "structure", "topic", "cover", "script", "operation"}
CONFIDENCE_VALUES = {"low": 0.4, "medium": 0.6}
REQUIRED_PROPOSAL_FIELDS = {
    "rule_text",
    "rule_type",
    "scope",
    "applicable_when",
    "not_applicable_when",
    "evidence",
    "account_fit_basis",
    "limitations",
    "risk_notes",
    "confidence",
}
ACTIVE_DUPLICATE_STATUSES = {"candidate", "approved", "testing", "validated"}
NON_COMMENT_DIMENSIONS = {"选题", "标题", "正文结构", "封面与图片", "视频与视觉", "音频与字幕"}
NEGATIVE_MARKERS = ("避免", "不要", "不使用", "禁止", "风险", "不建议", "不应", "不能", "删除", "改为")
POSITIVE_MARKERS = ("应该使用", "直接使用", "必须使用", "推荐使用", "照搬")
PUNCTUATION = re.compile(r"[\s\.,;:!?，。；：！？、()（）\[\]【】'\"“”‘’<>《》]", re.UNICODE)


class CandidateProposalError(ValueError):
    """Raised before a candidate proposal command performs any writes."""


def propose_candidate_rules(
    capture: CaptureRecord,
    analysis: BenchmarkAnalysis,
    profile: CreatorProfile,
    proposal_payload: dict[str, Any],
    existing_rules: list[RuleCard],
    existing_evidence: list[RuleEvidence],
) -> dict[str, Any]:
    del existing_evidence  # Evidence maintenance for existing rules is intentionally deferred.
    proposals = validate_proposal_payload(proposal_payload)
    assessment_by_dimension = validate_account_fit(analysis, profile)
    saved_judgments = judgments_by_dimension(capture, analysis)

    result = empty_result(analysis)
    for index, proposal in enumerate(proposals, start=1):
        try:
            validate_proposal_evidence(proposal, saved_judgments, assessment_by_dimension)
            validate_classification_direction(proposal, assessment_by_dimension)
            validate_profile_boundaries(proposal, profile)
        except CandidateProposalError as exc:
            result["proposal_results"].append(proposal_result(index, "rejected", reasons=[str(exc)]))
            continue
        duplicate = find_exact_duplicate(proposal, existing_rules)
        if duplicate and duplicate.status in ACTIVE_DUPLICATE_STATUSES:
            result["proposal_results"].append(
                proposal_result(index, "duplicate", reasons=["已有相同候选或正式规则，本次不重复保存。"])
            )
            continue

        warnings: list[str] = []
        if duplicate and duplicate.status == "rejected":
            warnings.append("相同规则曾被拒绝；本次将作为新的待确认候选保留。")
        if duplicate and duplicate.status == "deprecated":
            warnings.append("相同规则曾被废弃；本次将作为新的待确认候选保留。")

        rule = build_rule_card(capture, analysis, profile, proposal, index, existing_rules)
        evidence = build_rule_evidence(rule, analysis, capture, proposal)
        provenance = build_provenance_records(rule, analysis, profile)
        result["created_rules"].append(rule)
        result["created_evidence"].extend(evidence)
        result["created_provenance"].extend(provenance)
        result["proposal_results"].append(proposal_result(index, "created", rule=rule, warnings=warnings))

    result["user_summary"] = build_candidate_rule_summary(result)
    return result


def validate_proposal_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or set(payload) != {"proposals"}:
        raise CandidateProposalError("规则提案文件只能包含 proposals。")
    proposals = payload.get("proposals")
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 3:
        raise CandidateProposalError("每次需要提供 1 到 3 条规则提案。")

    validated: list[dict[str, Any]] = []
    for proposal in proposals:
        if not isinstance(proposal, dict) or set(proposal) != REQUIRED_PROPOSAL_FIELDS:
            raise CandidateProposalError("每条规则提案必须包含完整的结构化字段。")
        for field in ("rule_text",):
            if not text(proposal[field]):
                raise CandidateProposalError("规则内容不能为空。")
        if proposal["rule_type"] not in RULE_TYPES:
            raise CandidateProposalError("规则类型不受支持。")
        if proposal["confidence"] not in CONFIDENCE_VALUES:
            raise CandidateProposalError("单篇内容提案的置信度只能为 low 或 medium。")
        for field in ("scope", "applicable_when", "not_applicable_when", "account_fit_basis", "limitations", "risk_notes"):
            ensure_text_list(proposal[field], field)
        evidence = proposal["evidence"]
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise CandidateProposalError("每条规则需要 1 到 3 条帖子证据。")
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"dimension", "observable_fact"}:
                raise CandidateProposalError("帖子证据必须包含维度和可见事实。")
            if not text(item["dimension"]) or not text(item["observable_fact"]):
                raise CandidateProposalError("帖子证据不能为空。")
        validated.append(proposal)
    return validated


def validate_account_fit(analysis: BenchmarkAnalysis, profile: CreatorProfile) -> dict[str, dict[str, Any]]:
    account_fit = analysis.account_fit
    assessments = account_fit.get("assessments") if isinstance(account_fit, dict) else None
    if not account_fit or account_fit.get("status_category") == "insufficient" or not isinstance(assessments, list):
        raise CandidateProposalError("当前账号适配信息不足，暂不能提炼长期候选规则。")
    if account_fit.get("source_profile_id") != profile.id or account_fit.get("source_profile_version") != profile.version:
        raise CandidateProposalError("账号适配结果已不是当前账号档案版本，需要重新评估。")

    usable = {
        str(item.get("element")): item
        for item in assessments
        if isinstance(item, dict)
        and item.get("classification") != "insufficient_information"
        and item.get("classification") in {"directly_borrowable", "adaptable", "not_recommended", "risky"}
        and any(text(value) for value in item.get("post_evidence", []))
    }
    if not usable:
        raise CandidateProposalError("当前账号适配信息不足，暂不能提炼长期候选规则。")
    return usable


def judgments_by_dimension(capture: CaptureRecord, analysis: BenchmarkAnalysis) -> dict[str, dict[str, Any]]:
    return {
        str(item["dimension"]): item
        for item in build_analysis_outcome(capture, analysis)["analysis_judgments"]
    }


def validate_proposal_evidence(
    proposal: dict[str, Any],
    judgments: dict[str, dict[str, Any]],
    assessments: dict[str, dict[str, Any]],
) -> None:
    dimensions: list[str] = []
    used_assessments: list[dict[str, Any]] = []
    for evidence in proposal["evidence"]:
        dimension = str(evidence["dimension"])
        observable_fact = str(evidence["observable_fact"])
        judgment = judgments.get(dimension)
        assessment = assessments.get(dimension)
        if judgment is None or assessment is None:
            raise CandidateProposalError("提案证据必须来自同时具备帖子分析和账号适配判断的维度。")
        if not matches_observed_evidence(observable_fact, judgment.get("evidence", [])):
            raise CandidateProposalError("提案中的可见事实没有对应到该维度已保存的帖子证据。")
        dimensions.append(dimension)
        used_assessments.append(assessment)

    if not basis_matches_assessments(proposal["account_fit_basis"], used_assessments):
        raise CandidateProposalError("账号适配依据必须来自对应维度的已保存判断。")

    if dimensions and all(dimension == "评论" for dimension in dimensions):
        raise CandidateProposalError("评论可以作为补充证据，但单条评论不足以独立形成长期候选规则。")
    if "互动表现" in dimensions:
        raise CandidateProposalError("互动数据不能作为长期候选规则的帖子证据。")
    expected_dimensions = expected_dimensions_for_type(str(proposal["rule_type"]))
    if expected_dimensions and not set(dimensions).issubset(expected_dimensions):
        raise CandidateProposalError("提案证据与规则类型不属于同一分析维度。")


def validate_classification_direction(proposal: dict[str, Any], assessments: dict[str, dict[str, Any]]) -> None:
    classifications = {assessments[str(item["dimension"])]["classification"] for item in proposal["evidence"]}
    rule_text = str(proposal["rule_text"])
    negative = is_negative_rule(rule_text, proposal["risk_notes"])
    positive = any(marker in rule_text for marker in POSITIVE_MARKERS)
    if "adaptable" in classifications and not has_adaptation_boundary(proposal):
        raise CandidateProposalError("需要改造的内容必须说明调整边界，不能作为无条件规则保存。")
    if "not_recommended" in classifications and (not negative or positive or not proposal["risk_notes"]):
        raise CandidateProposalError("不建议直接使用的内容只能形成禁止或边界规则。")
    if "risky" in classifications and (not negative or positive):
        raise CandidateProposalError("存在风险的内容只能形成风险提醒或避免规则。")


def validate_profile_boundaries(proposal: dict[str, Any], profile: CreatorProfile) -> None:
    rule_text = str(proposal["rule_text"])
    if requires_video(proposal) and "视频" not in profile.content_formats:
        raise CandidateProposalError("该提案明确要求视频形式，但当前账号档案未包含视频内容形式。")
    if is_negative_rule(rule_text, proposal["risk_notes"]):
        return
    for expression in profile.forbidden_expressions:
        if expression and expression in rule_text:
            raise CandidateProposalError("正向规则不能包含账号已明确禁用的表达。")


def find_exact_duplicate(proposal: dict[str, Any], existing_rules: list[RuleCard]) -> RuleCard | None:
    key = duplicate_key(str(proposal["rule_text"]), str(proposal["rule_type"]), proposal["scope"] + proposal["applicable_when"])
    for rule in existing_rules:
        existing_key = duplicate_key(rule.rule_summary, rule.type, rule.applicable_scenarios)
        if key == existing_key:
            return rule
    return None


def build_rule_card(
    capture: CaptureRecord,
    analysis: BenchmarkAnalysis,
    profile: CreatorProfile,
    proposal: dict[str, Any],
    index: int,
    existing_rules: list[RuleCard],
) -> RuleCard:
    rule_id = available_rule_id(stable_id("rule-proposal", analysis.id, index, proposal["rule_text"]), existing_rules)
    applicable_audiences = [
        audience for audience in profile.target_audience if any(audience in basis for basis in proposal["account_fit_basis"])
    ]
    return RuleCard(
        id=rule_id,
        name=f"候选{proposal['rule_type']}规则：{short_text(str(proposal['rule_text']))}",
        type=str(proposal["rule_type"]),
        source_ids=[analysis.id, capture.id],
        applicable_scenarios=unique_texts(proposal["scope"] + proposal["applicable_when"]),
        rule_summary=str(proposal["rule_text"]),
        examples=[str(item["observable_fact"]) for item in proposal["evidence"]],
        risks=list(proposal["risk_notes"]),
        adaptation_notes=build_adaptation_notes(proposal),
        tags=["candidate", "evidence-grounded", "pr-3c"],
        status="candidate",
        strength="weak",
        applicable_content_types=content_type_labels(capture.content_type),
        applicable_audiences=applicable_audiences,
        conflicts_with=[],
        source_type="benchmark_analysis",
        source_note=analysis.id,
        created_from="propose-candidate-rules",
        confidence=CONFIDENCE_VALUES[str(proposal["confidence"])],
        created_by="codex",
    )


def build_rule_evidence(
    rule: RuleCard,
    analysis: BenchmarkAnalysis,
    capture: CaptureRecord,
    proposal: dict[str, Any],
) -> list[RuleEvidence]:
    return [
        RuleEvidence(
            id=stable_id("evidence-proposal", rule.id, index, evidence["observable_fact"]),
            rule_id=rule.id,
            source_type="benchmark_analysis",
            source_id=analysis.id,
            source_fragment=str(evidence["dimension"]),
            evidence_type=evidence_type_for_dimension(str(evidence["dimension"])),
            observable_fact=str(evidence["observable_fact"]),
            inference=f"该可见事实被用户提交的结构化提案用于支持候选规则：“{proposal['rule_text']}”。",
            confidence=CONFIDENCE_VALUES[str(proposal["confidence"])],
            source_note=capture.id,
            created_from="propose-candidate-rules",
            created_by="codex",
        )
        for index, evidence in enumerate(proposal["evidence"], start=1)
    ]


def build_provenance_records(rule: RuleCard, analysis: BenchmarkAnalysis, profile: CreatorProfile) -> list[ProvenanceRecord]:
    return [
        ProvenanceRecord(
            id=f"provenance-{rule.id}-analysis",
            target_object_type="rule_card",
            target_object_id=rule.id,
            source_object_type="benchmark_analysis",
            source_object_id=analysis.id,
            source_version=analysis.version,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-candidate-rules",
            note="候选规则基于已保存的 evidence-first 分析。",
            created_by="codex",
            source_type="benchmark_analysis",
            source_note=analysis.id,
            created_from="propose-candidate-rules",
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
            method="propose-candidate-rules",
            note="候选规则已核对指定账号档案及其账号适配结果。",
            created_by="codex",
            source_type="creator_profile",
            source_note=profile.id,
            created_from="propose-candidate-rules",
        ),
    ]


def empty_result(analysis: BenchmarkAnalysis) -> dict[str, Any]:
    return {
        "status_category": str(analysis.account_fit.get("status_category", "insufficient")),
        "created_rules": [],
        "created_evidence": [],
        "created_provenance": [],
        "proposal_results": [],
        "user_summary": "",
    }


def proposal_result(index: int, outcome: str, rule: RuleCard | None = None, reasons: list[str] | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    return {"index": index, "outcome": outcome, "rule": rule, "duplicate_rule_id": "", "reasons": reasons or [], "warnings": warnings or []}


def build_candidate_rule_summary(result: dict[str, Any]) -> str:
    created = [item for item in result["proposal_results"] if item["outcome"] == "created"]
    skipped = [item for item in result["proposal_results"] if item["outcome"] != "created"]
    sections: list[str] = ["【候选规则】"]
    if created:
        for position, item in enumerate(created, start=1):
            rule = item["rule"]
            assert isinstance(rule, RuleCard)
            sections.append(
                "\n".join(
                    [
                        f"候选规则 {position}",
                        f"规则：{rule.rule_summary}",
                        f"适用于：{'、'.join(rule.applicable_scenarios) or '当前已验证场景'}",
                        f"暂不适用于：{adaptation_exclusions(rule.adaptation_notes)}",
                        "为什么提出：已有帖子证据与账号适配判断支持。",
                        f"帖子证据：{'；'.join(rule.examples)}",
                        "账号适配依据：已通过当前账号资料核对。",
                        f"风险或限制：{'；'.join(rule.risks) if rule.risks else '单篇内容形成，仍需更多样本验证。'}",
                        "与现有规则的关系：已完成精确重复和账号明确边界检查；近似或语义冲突仍需人工确认。",
                        "当前状态：待确认",
                    ]
                )
            )
    else:
        sections.append("当前没有可保存的候选规则。")
    if skipped:
        lines = ["【未创建的提案】"]
        for item in skipped:
            lines.extend(item["reasons"] or item["warnings"] or ["该提案未保存。"])
        sections.append("\n".join(f"- {line}" for line in lines))
    sections.append("【下一步】\n候选规则尚未生效，需要后续确认、测试或拒绝。")
    return "\n\n".join(sections)


def matches_observed_evidence(value: str, values: list[Any]) -> bool:
    return any(value == str(item).strip() or value in str(item) or str(item) in value for item in values if text(item))


def basis_matches_assessments(basis: list[str], assessments: list[dict[str, Any]]) -> bool:
    sources: list[Any] = []
    for assessment in assessments:
        sources.extend([assessment.get("reason", ""), assessment.get("adaptation_guidance", "")])
        sources.extend(assessment.get("profile_evidence", []))
    return bool(basis) and all(any(item == str(source).strip() or item in str(source) for source in sources if text(source)) for item in basis)


def expected_dimensions_for_type(rule_type: str) -> set[str]:
    return {
        "title": {"标题"},
        "structure": {"正文结构"},
        "topic": {"选题"},
        "cover": {"封面与图片"},
        "script": {"正文结构", "视频与视觉", "音频与字幕"},
        "operation": NON_COMMENT_DIMENSIONS,
    }.get(rule_type, set())


def has_adaptation_boundary(proposal: dict[str, Any]) -> bool:
    if proposal["limitations"] or proposal["not_applicable_when"]:
        return True
    return any(any(marker in basis for marker in ("调整", "改写", "避免", "不照搬", "边界")) for basis in proposal["account_fit_basis"])


def is_negative_rule(rule_text: str, risks: list[str]) -> bool:
    return any(marker in rule_text for marker in NEGATIVE_MARKERS) or bool(risks and any(marker in " ".join(risks) for marker in NEGATIVE_MARKERS))


def requires_video(proposal: dict[str, Any]) -> bool:
    return any("视频" in value for value in proposal["scope"] + proposal["applicable_when"])


def duplicate_key(rule_text: str, rule_type: str, scope: list[str]) -> tuple[str, str, tuple[str, ...]]:
    return normalize_text(rule_text), rule_type, tuple(sorted({normalize_text(item) for item in scope if text(item)}))


def normalize_text(value: str) -> str:
    return PUNCTUATION.sub("", value).casefold()


def stable_id(prefix: str, *parts: Any) -> str:
    source = "|".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(source.encode('utf-8')).hexdigest()[:16]}"


def available_rule_id(base_id: str, existing_rules: list[RuleCard]) -> str:
    existing_ids = {rule.id for rule in existing_rules}
    if base_id not in existing_ids:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}-{suffix}"


def evidence_type_for_dimension(dimension: str) -> str:
    return {
        "选题": "topic",
        "标题": "title",
        "正文结构": "structure",
        "封面与图片": "cover_content",
        "视频与视觉": "video_content",
        "音频与字幕": "audio_content",
        "评论": "comment_text",
    }.get(dimension, "observable_content")


def content_type_labels(content_type: str) -> list[str]:
    return {"image": ["图文"], "video": ["视频"], "mixed": ["图文", "视频"]}.get(content_type, [])


def build_adaptation_notes(proposal: dict[str, Any]) -> str:
    parts = list(proposal["limitations"])
    if proposal["not_applicable_when"]:
        parts.append("暂不适用于：" + "、".join(proposal["not_applicable_when"]))
    return "；".join(parts) or "单篇内容形成的候选规则，需要更多样本和人工确认。"


def adaptation_exclusions(notes: str) -> str:
    marker = "暂不适用于："
    return notes.split(marker, 1)[1] if marker in notes else "需结合具体内容判断"


def unique_texts(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if text(value)))


def ensure_text_list(value: Any, field_name: str) -> None:
    if not isinstance(value, list) or any(not text(item) for item in value):
        raise CandidateProposalError(f"{field_name} 必须是文本列表。")


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def short_text(value: str) -> str:
    return value[:24] + ("…" if len(value) > 24 else "")
