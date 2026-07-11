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
NEGATIVE_MARKERS = ("避免", "不要", "不使用", "禁止", "风险", "不建议", "不应", "不能", "删除")
POSITIVE_MARKERS = ("使用", "采用", "保留", "增加", "强化", "突出", "照搬")
PUNCTUATION = re.compile(r"[\s\.,;:!?，。；：！？、()（）\[\]【】'\"“”‘’<>《》]", re.UNICODE)
GENERIC_TEXT_FRAGMENTS = {"人", "新人", "新手", "标题", "正文", "内容", "结构", "方法", "汇报", "表达", "账号", "用户", "视频", "图片", "评论", "适配"}
AMBIGUOUS_DIRECTION_PATTERNS = ("不要避免", "不应禁止", "并非不建议", "不建议避免", "不能不使用")
EXPLICIT_NEGATIVE_PATTERNS = ("避免使用", "不要使用", "禁止使用", "不建议使用", "不应使用", "不能使用", "避免采用", "不要采用", "禁止采用", "不建议采用", "不应采用", "不能采用", "避免照搬", "不要照搬", "禁止照搬", "不建议照搬", "不应照搬", "不能照搬", "删除", "存在风险，应避免")
VIDEO_REQUIREMENT_PATTERNS = ("使用视频", "采用视频", "视频形式", "视频内容", "制作视频", "以视频呈现", "需要视频")
VIDEO_NEGATION_PATTERNS = ("不要使用视频", "避免视频", "非视频", "无需视频")
INCOMPLETE_FRAGMENT_ENDINGS = ("如何", "怎么", "为什么", "为何", "怎样", "哪些", "什么", "是否", "能否", "可以吗", "怎么办", "需要", "应该", "通过", "使用", "采用", "包括", "例如", "比如", "以及", "并且", "但是", "因为", "所以", "准备")
TRANSITION_MARKERS = ("但", "但是", "不过", "然而", "仍", "仍然", "可以", "可")


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
    rules_for_deduplication = list(existing_rules)
    for index, proposal in enumerate(proposals, start=1):
        try:
            validate_proposal_evidence(proposal, saved_judgments, assessment_by_dimension)
            validate_classification_direction(proposal, assessment_by_dimension)
            validate_profile_boundaries(proposal, profile)
        except CandidateProposalError as exc:
            result["proposal_results"].append(proposal_result(index, "rejected", reasons=[str(exc)]))
            continue
        duplicate = find_exact_duplicate(proposal, rules_for_deduplication)
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
        result["proposal_results"].append(proposal_result(index, "created", rule=rule, proposal=proposal, warnings=warnings))
        rules_for_deduplication.append(rule)

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
        seen_evidence: set[tuple[str, str]] = set()
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"dimension", "observable_fact"}:
                raise CandidateProposalError("帖子证据必须包含维度和可见事实。")
            if not text(item["dimension"]) or not text(item["observable_fact"]):
                raise CandidateProposalError("帖子证据不能为空。")
            evidence_key = (normalize_text(item["dimension"]), normalize_text(item["observable_fact"]))
            if evidence_key in seen_evidence:
                raise CandidateProposalError("同一条规则提案中不能重复提交相同帖子证据。")
            seen_evidence.add(evidence_key)
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
    used_assessments = [assessments[str(item["dimension"])] for item in proposal["evidence"]]
    classifications = {item["classification"] for item in used_assessments}
    rule_text = str(proposal["rule_text"])
    direction = classify_rule_direction(rule_text, proposal["risk_notes"])
    if "adaptable" in classifications and not has_adaptation_boundary(proposal, used_assessments):
        raise CandidateProposalError("需要改造的内容必须说明调整边界，不能作为无条件规则保存。")
    if "not_recommended" in classifications and (direction != "negative" or not proposal["risk_notes"]):
        raise CandidateProposalError("不建议直接使用的内容只能形成禁止或边界规则。")
    if "risky" in classifications and direction != "negative":
        raise CandidateProposalError("存在风险的内容只能形成风险提醒或避免规则。")


def validate_profile_boundaries(proposal: dict[str, Any], profile: CreatorProfile) -> None:
    rule_text = str(proposal["rule_text"])
    if has_ambiguous_video_requirement(proposal):
        raise CandidateProposalError("该提案对视频形式的要求相互矛盾，请明确是否需要视频内容。")
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


def proposal_result(
    index: int,
    outcome: str,
    rule: RuleCard | None = None,
    proposal: dict[str, Any] | None = None,
    reasons: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    display = {
        "account_fit_basis": list(proposal["account_fit_basis"]),
        "not_applicable_when": list(proposal["not_applicable_when"]),
        "limitations": list(proposal["limitations"]),
        "risk_notes": list(proposal["risk_notes"]),
    } if proposal else {}
    return {
        "index": index,
        "outcome": outcome,
        "rule": rule,
        "duplicate_rule_id": "",
        "display": display,
        "reasons": reasons or [],
        "warnings": warnings or [],
    }


def build_candidate_rule_summary(result: dict[str, Any]) -> str:
    created = [item for item in result["proposal_results"] if item["outcome"] == "created"]
    skipped = [item for item in result["proposal_results"] if item["outcome"] != "created"]
    sections: list[str] = ["【候选规则】"]
    if created:
        for position, item in enumerate(created, start=1):
            rule = item["rule"]
            assert isinstance(rule, RuleCard)
            display = item["display"]
            limits = unique_texts(display["limitations"] + display["risk_notes"])
            relationship = "；".join(item["warnings"]) or "已完成精确重复和账号明确边界检查；近似或语义冲突仍需人工确认。"
            sections.append(
                "\n".join(
                    [
                        f"候选规则 {position}",
                        f"规则：{rule.rule_summary}",
                        f"适用于：{'、'.join(rule.applicable_scenarios) or '当前已验证场景'}",
                        f"暂不适用于：{'、'.join(display['not_applicable_when']) or adaptation_exclusions(rule.adaptation_notes)}",
                        "为什么提出：已有帖子证据与账号适配判断支持。",
                        f"帖子证据：{'；'.join(rule.examples)}",
                        "账号适配依据：\n" + "\n".join(f"- {basis}" for basis in display["account_fit_basis"]),
                        f"风险或限制：{'；'.join(limits) if limits else '单篇内容形成，仍需更多样本验证。'}",
                        f"与现有规则的关系：{relationship}",
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
    return matches_saved_text_fragment(value, values, minimum_length=6)


def basis_matches_assessments(basis: list[str], assessments: list[dict[str, Any]]) -> bool:
    sources: list[Any] = []
    for assessment in assessments:
        sources.extend([assessment.get("reason", ""), assessment.get("adaptation_guidance", "")])
        sources.extend(assessment.get("profile_evidence", []))
    return bool(basis) and all(matches_saved_text_fragment(item, sources, minimum_length=6) for item in basis)


def matches_saved_text_fragment(proposed: str, saved_values: list[Any], *, minimum_length: int) -> bool:
    candidate = proposed.strip()
    effective = PUNCTUATION.sub("", candidate)
    if not effective or effective.isdigit() or effective in GENERIC_TEXT_FRAGMENTS:
        return False
    if effective.isascii() and effective.isalnum():
        if len(effective) < 12:
            return False
    elif len(effective) < minimum_length:
        return False
    for saved in saved_values:
        if not text(saved):
            continue
        saved_text = str(saved).strip()
        if candidate == saved_text:
            return True
        if candidate in saved_text and not has_incomplete_fragment_ending(candidate):
            return True
    return False


def has_incomplete_fragment_ending(value: str) -> bool:
    return any(value.endswith(ending) for ending in INCOMPLETE_FRAGMENT_ENDINGS)


def expected_dimensions_for_type(rule_type: str) -> set[str]:
    return {
        "title": {"标题"},
        "structure": {"正文结构"},
        "topic": {"选题"},
        "cover": {"封面与图片"},
        "script": {"正文结构", "视频与视觉", "音频与字幕"},
        "operation": NON_COMMENT_DIMENSIONS,
    }.get(rule_type, set())


def has_adaptation_boundary(proposal: dict[str, Any], assessments: list[dict[str, Any]]) -> bool:
    guidance = [str(item.get("adaptation_guidance", "")) for item in assessments if text(item.get("adaptation_guidance", ""))]
    if not guidance:
        return False
    has_guidance_basis = any(matches_saved_text_fragment(basis, guidance, minimum_length=6) for basis in proposal["account_fit_basis"])
    boundary_values = proposal["limitations"] + proposal["not_applicable_when"] + [str(proposal["rule_text"])]
    return has_guidance_basis and any(matches_saved_text_fragment(value, guidance, minimum_length=6) for value in boundary_values)


def is_negative_rule(rule_text: str, risks: list[str]) -> bool:
    return classify_rule_direction(rule_text, risks) == "negative"


def is_explicitly_positive_rule(rule_text: str) -> bool:
    return classify_rule_direction(rule_text, []) == "positive"


def has_negative_marker(value: str) -> bool:
    return any(marker in value for marker in NEGATIVE_MARKERS)


def classify_rule_direction(rule_text: str, risk_notes: list[str]) -> str:
    del risk_notes  # Risk notes explain the boundary; rule text determines the proposed direction.
    normalized = re.sub(r"\s+", "", rule_text)
    if any(pattern in normalized for pattern in AMBIGUOUS_DIRECTION_PATTERNS):
        return "ambiguous"
    if has_mixed_negative_then_positive_clause(normalized):
        return "ambiguous"
    if any(pattern in normalized for pattern in EXPLICIT_NEGATIVE_PATTERNS):
        return "negative"
    has_positive_action = any(marker in normalized for marker in POSITIVE_MARKERS + ("应该", "应当", "推荐"))
    if ("风险" in normalized and has_positive_action) or (any(marker in normalized for marker in TRANSITION_MARKERS + ("可控",)) and has_positive_action and has_negative_marker(normalized)):
        return "ambiguous"
    if has_negative_marker(normalized):
        return "negative"
    return "positive"


def has_mixed_negative_then_positive_clause(value: str) -> bool:
    for marker in TRANSITION_MARKERS:
        if marker not in value:
            continue
        before, after = value.split(marker, 1)
        if any(pattern in before for pattern in EXPLICIT_NEGATIVE_PATTERNS) and any(action in after for action in POSITIVE_MARKERS + ("应该", "应当", "推荐")):
            return True
    return False


def requires_video(proposal: dict[str, Any]) -> bool:
    for value in proposal["scope"] + proposal["applicable_when"]:
        normalized = re.sub(r"\s+", "", value)
        _, requires_video_content = video_requirement_parts(normalized)
        if not requires_video_content:
            continue
        return True
    return False


def has_ambiguous_video_requirement(proposal: dict[str, Any]) -> bool:
    return any(
        has_negation and requires_video_content
        for value in proposal["scope"] + proposal["applicable_when"]
        for has_negation, requires_video_content in [video_requirement_parts(re.sub(r"\s+", "", value))]
    )


def video_requirement_parts(value: str) -> tuple[bool, bool]:
    has_negation = any(pattern in value for pattern in VIDEO_NEGATION_PATTERNS)
    remainder = value
    for pattern in VIDEO_NEGATION_PATTERNS:
        remainder = remainder.replace(pattern, "")
    return has_negation, any(pattern in remainder for pattern in VIDEO_REQUIREMENT_PATTERNS)


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
