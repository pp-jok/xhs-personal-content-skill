from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
import re
from typing import Any, Callable

from app.models.core import (
    CONTENT_MECHANISM_CONFIDENCE_SCORES,
    ContentAsset,
    ContentAssetEvidence,
    ContentMechanism,
    CreatorProfile,
    ProvenanceRecord,
    ValidationError,
)


ASSET_TYPES = {
    "title_pattern",
    "cover_structure",
    "opening_template",
    "body_structure",
    "cta_template",
    "comparison_framework",
    "case_framework",
    "image_text_structure",
    "topic_framework",
}
CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
REQUIRED_FIELDS = {
    "asset_type",
    "name",
    "description",
    "template",
    "variables",
    "applicable_scope",
    "selected_observed_facts",
    "account_fit_reason",
    "limitations",
}
OPTIONAL_FIELDS = {"exclusions", "usage_notes", "examples", "confidence_level"}
BLOCKING_DUPLICATE_STATUSES = {"candidate", "active"}
GENERIC_TEXT = {"很好", "有价值", "推荐", "通用模板", "通用内容", "适合账号", "值得使用", "值得借鉴"}
WHITESPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[\s\.,;:!?，。；：！？、()（）\[\]【】'\"“”‘’<>《》]", re.UNICODE)


class MechanismAssetProposalError(ValueError):
    """Raised before mechanism asset proposal writes are considered successful."""


@dataclass
class MechanismAssetProposalResult:
    created: bool
    asset: ContentAsset
    asset_evidence: list[ContentAssetEvidence]
    provenance_records: list[ProvenanceRecord]
    warnings: list[str] = field(default_factory=list)
    duplicate_check: dict[str, Any] = field(default_factory=dict)
    user_summary: str = ""
    machine_summary: dict[str, Any] = field(default_factory=dict)


def propose_asset_from_mechanism(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    proposal_payload: dict[str, Any],
    existing_assets: list[ContentAsset],
    existing_provenance: list[ProvenanceRecord],
) -> MechanismAssetProposalResult:
    if mechanism.status == "deprecated":
        raise MechanismAssetProposalError("该内容机制已废弃，不能继续转为候选内容资产。")
    if mechanism.status not in {"candidate", "active"}:
        raise MechanismAssetProposalError("该内容机制当前状态不支持转为候选内容资产。")

    proposal = validate_proposal_payload(proposal_payload, mechanism)
    duplicates = find_exact_duplicates(proposal, profile, existing_assets)
    blocking = sorted((item for item in duplicates if item.status in BLOCKING_DUPLICATE_STATUSES), key=lambda item: item.id)
    historical = sorted((item for item in duplicates if item.status == "deprecated"), key=lambda item: item.id)
    warnings: list[str] = []
    duplicate_check = {"status": "none", "existing_asset_id": ""}
    if blocking:
        raise MechanismAssetProposalError("已有相同候选或生效内容资产，本次不重复保存。")
    if historical:
        warnings.append("相同内容资产曾被废弃；本次将作为新的候选资产保留。")
        duplicate_check = {
            "status": "deprecated_history",
            "existing_asset_id": historical[0].id,
            "existing_asset_ids": [item.id for item in historical],
        }

    same_source = find_same_source_candidate(mechanism, profile, proposal["asset_type"], existing_assets, existing_provenance)
    if same_source:
        raise MechanismAssetProposalError("同一机制和账号已经存在同类型候选内容资产，本次不重复保存。")

    asset = build_content_asset(mechanism, profile, proposal, existing_assets)
    evidence = build_asset_evidence(asset, mechanism, proposal)
    provenance = build_provenance_records(asset, mechanism, profile)
    for item in [asset, *evidence, *provenance]:
        item.validate()

    machine_summary = {
        "mechanism_id": mechanism.id,
        "mechanism_version": mechanism.version,
        "mechanism_status": mechanism.status,
        "profile_id": profile.id,
        "profile_version": profile.version,
        "asset_id": asset.id,
        "asset_status": asset.status,
        "asset_type": asset.asset_type,
        "evidence_ids": [item.id for item in evidence],
        "provenance_ids": [item.id for item in provenance],
        "selected_observed_facts": list(proposal["selected_observed_facts"]),
        "variables": list(proposal["variables"]),
        "applicable_scope": list(proposal["applicable_scope"]),
        "exclusions": list(proposal["exclusions"]),
        "limitations": list(proposal["limitations"]),
        "confidence_level": proposal["confidence_level"],
        "duplicate_check": duplicate_check,
        "warnings": warnings,
        "generation_context_connected": False,
        "decision_request_created": False,
    }
    return MechanismAssetProposalResult(
        created=True,
        asset=asset,
        asset_evidence=evidence,
        provenance_records=provenance,
        warnings=warnings,
        duplicate_check=duplicate_check,
        user_summary=build_user_summary(asset, proposal, warnings),
        machine_summary=machine_summary,
    )


def validate_proposal_payload(payload: dict[str, Any], mechanism: ContentMechanism) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MechanismAssetProposalError("内容资产提案必须是一个 JSON object。")
    unknown = set(payload) - REQUIRED_FIELDS - OPTIONAL_FIELDS
    missing = REQUIRED_FIELDS - set(payload)
    if unknown or missing:
        raise MechanismAssetProposalError("内容资产提案字段不完整或包含不支持字段。")

    asset_type = text(payload["asset_type"])
    if asset_type not in ASSET_TYPES:
        raise MechanismAssetProposalError("内容资产类型不受支持。")
    name = required_text(payload["name"], "资产名称不能为空。")
    description = required_text(payload["description"], "资产描述不能为空。")
    template = required_text(payload["template"], "模板不能为空。")
    if normalized_text(name) in {normalized_text(item) for item in GENERIC_TEXT}:
        raise MechanismAssetProposalError("资产名称过于空泛，不能保存。")
    if normalized_text(description) in {normalized_text(item) for item in GENERIC_TEXT}:
        raise MechanismAssetProposalError("资产描述过于空泛，不能保存。")
    if normalized_text(template) in {normalized_text(item) for item in GENERIC_TEXT}:
        raise MechanismAssetProposalError("模板内容过于空泛，不能保存。")

    variables = unique_required_list(payload["variables"], "variables")
    applicable_scope = unique_required_list(payload["applicable_scope"], "applicable_scope")
    selected = required_selected_facts(payload["selected_observed_facts"], mechanism)
    confidence_level = text(payload.get("confidence_level")) or mechanism.confidence_level
    if confidence_level not in CONFIDENCE_ORDER:
        raise MechanismAssetProposalError("置信度级别不受支持。")
    if CONFIDENCE_ORDER[confidence_level] > CONFIDENCE_ORDER[mechanism.confidence_level]:
        raise MechanismAssetProposalError("资产置信度不能高于来源机制。")

    proposal = {
        "asset_type": asset_type,
        "name": name,
        "description": description,
        "template": template,
        "variables": variables,
        "applicable_scope": applicable_scope,
        "exclusions": optional_text_list(payload.get("exclusions", []), "exclusions"),
        "usage_notes": optional_text_list(payload.get("usage_notes", []), "usage_notes"),
        "limitations": optional_text_list(payload["limitations"], "limitations"),
        "examples": optional_text_list(payload.get("examples", []), "examples"),
        "selected_observed_facts": selected,
        "account_fit_reason": required_text(payload["account_fit_reason"], "账号适配理由不能为空。"),
        "confidence_level": confidence_level,
    }
    # Reuse model validation for placeholder and template contract checks.
    try:
        ContentAsset(
            id="asset-contract-check",
            asset_type=proposal["asset_type"],
            name=proposal["name"],
            description=proposal["description"],
            template=proposal["template"],
            variables=list(proposal["variables"]),
            applicable_scope=list(proposal["applicable_scope"]),
            exclusions=list(proposal["exclusions"]),
            usage_notes=list(proposal["usage_notes"]),
            limitations=list(proposal["limitations"]),
            examples=list(proposal["examples"]),
            creator_profile_id="creator-contract-check",
            source_mechanism_ids=["mechanism-contract-check"],
            selected_observed_facts=list(proposal["selected_observed_facts"]),
            account_fit_reason=proposal["account_fit_reason"],
            confidence_level=proposal["confidence_level"],
            confidence=CONTENT_MECHANISM_CONFIDENCE_SCORES[proposal["confidence_level"]],
            created_from="propose-asset-from-mechanism",
            created_by="codex",
        )
    except ValidationError as exc:
        raise MechanismAssetProposalError("内容资产提案格式不符合要求。") from exc
    return proposal


def required_selected_facts(value: Any, mechanism: ContentMechanism) -> list[str]:
    selected = optional_text_list(value, "selected_observed_facts")
    if not selected:
        raise MechanismAssetProposalError("selected_observed_facts 不能为空。")
    if len(selected) > 3:
        raise MechanismAssetProposalError("每次最多选择 3 条机制事实。")
    if len(selected) != len(set(selected)):
        raise MechanismAssetProposalError("selected_observed_facts 不能重复。")
    facts = {str(fact).strip(): index for index, fact in enumerate(mechanism.evidence_summary.get("observed_facts", []))}
    for fact in selected:
        if fact not in facts:
            raise MechanismAssetProposalError("资产证据必须完全来自机制中的可观察事实。")
    return selected


def build_content_asset(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    proposal: dict[str, Any],
    existing_assets: list[ContentAsset],
) -> ContentAsset:
    base_id = stable_id("asset-mechanism", mechanism.id, profile.id, proposal["asset_type"], proposal["template"])
    asset_id = available_asset_id(base_id, existing_assets)
    return ContentAsset(
        id=asset_id,
        status="candidate",
        asset_type=proposal["asset_type"],
        name=proposal["name"],
        description=proposal["description"],
        template=proposal["template"],
        variables=list(proposal["variables"]),
        applicable_scope=list(proposal["applicable_scope"]),
        exclusions=list(proposal["exclusions"]),
        usage_notes=list(proposal["usage_notes"]),
        limitations=list(proposal["limitations"]),
        examples=list(proposal["examples"]),
        creator_profile_id=profile.id,
        source_mechanism_ids=[mechanism.id],
        selected_observed_facts=list(proposal["selected_observed_facts"]),
        account_fit_reason=proposal["account_fit_reason"],
        confidence_level=proposal["confidence_level"],
        confidence=CONTENT_MECHANISM_CONFIDENCE_SCORES[proposal["confidence_level"]],
        source_type="content_mechanism",
        source_note=mechanism.id,
        created_from="propose-asset-from-mechanism",
        created_by="codex",
    )


def build_asset_evidence(
    asset: ContentAsset,
    mechanism: ContentMechanism,
    proposal: dict[str, Any],
) -> list[ContentAssetEvidence]:
    index_by_fact = {str(fact).strip(): index for index, fact in enumerate(mechanism.evidence_summary.get("observed_facts", []))}
    return [
        ContentAssetEvidence(
            id=stable_id("asset-evidence", asset.id, str(position), fact),
            asset_id=asset.id,
            source_type="content_mechanism",
            source_id=mechanism.id,
            source_version=mechanism.version,
            source_fragment=f"evidence_summary.observed_facts[{index_by_fact[fact]}]",
            evidence_text=fact,
            confidence_level=proposal["confidence_level"],
            confidence=CONTENT_MECHANISM_CONFIDENCE_SCORES[proposal["confidence_level"]],
            source_note=mechanism.name,
            created_from="propose-asset-from-mechanism",
            created_by="codex",
        )
        for position, fact in enumerate(proposal["selected_observed_facts"], start=1)
    ]


def build_provenance_records(
    asset: ContentAsset,
    mechanism: ContentMechanism,
    profile: CreatorProfile,
) -> list[ProvenanceRecord]:
    return [
        ProvenanceRecord(
            id=f"provenance-{asset.id}-mechanism",
            target_object_type="content_asset",
            target_object_id=asset.id,
            source_object_type="content_mechanism",
            source_object_id=mechanism.id,
            source_version=mechanism.version,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-asset-from-mechanism",
            note="候选内容资产基于已保存的内容机制。",
            created_by="codex",
            source_type="content_mechanism",
            source_note=mechanism.id,
            created_from="propose-asset-from-mechanism",
        ),
        ProvenanceRecord(
            id=f"provenance-{asset.id}-profile",
            target_object_type="content_asset",
            target_object_id=asset.id,
            source_object_type="creator_profile",
            source_object_id=profile.id,
            source_version=profile.version,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-asset-from-mechanism",
            note="候选内容资产已核对指定账号档案。",
            created_by="codex",
            source_type="creator_profile",
            source_note=profile.id,
            created_from="propose-asset-from-mechanism",
        ),
    ]


def persist_mechanism_asset_proposal(
    result: MechanismAssetProposalResult,
    *,
    create_asset: Callable[[ContentAsset], ContentAsset],
    create_evidence: Callable[[ContentAssetEvidence], ContentAssetEvidence],
    create_provenance: Callable[[ProvenanceRecord], ProvenanceRecord],
    delete_asset: Callable[[str], None],
    delete_evidence: Callable[[str], None],
    delete_provenance: Callable[[str], None],
) -> MechanismAssetProposalResult:
    created_assets: list[str] = []
    created_evidence: list[str] = []
    created_provenance: list[str] = []
    try:
        create_asset(result.asset)
        created_assets.append(result.asset.id)
        for evidence in result.asset_evidence:
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
            except Exception as rollback_exc:  # pragma: no cover - repository-specific.
                rollback_errors.append(str(rollback_exc))
        for record_id in reversed(created_evidence):
            try:
                delete_evidence(record_id)
            except Exception as rollback_exc:  # pragma: no cover
                rollback_errors.append(str(rollback_exc))
        for record_id in reversed(created_assets):
            try:
                delete_asset(record_id)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if rollback_errors:
            raise MechanismAssetProposalError("候选内容资产写入失败，且回滚失败；需要人工检查本地数据。") from exc
        raise MechanismAssetProposalError("候选内容资产写入失败，已回滚本次创建内容。") from exc
    return result


def find_exact_duplicates(
    proposal: dict[str, Any],
    profile: CreatorProfile,
    existing_assets: list[ContentAsset],
) -> list[ContentAsset]:
    key = duplicate_key(proposal["asset_type"], proposal["template"], proposal["applicable_scope"], profile.id)
    return [
        asset
        for asset in existing_assets
        if key == duplicate_key(asset.asset_type, asset.template, asset.applicable_scope, asset.creator_profile_id)
    ]


def find_same_source_candidate(
    mechanism: ContentMechanism,
    profile: CreatorProfile,
    asset_type: str,
    existing_assets: list[ContentAsset],
    existing_provenance: list[ProvenanceRecord],
) -> ContentAsset | None:
    provenance_sources: dict[str, set[tuple[str, str]]] = {}
    for item in existing_provenance:
        if item.target_object_type != "content_asset":
            continue
        provenance_sources.setdefault(item.target_object_id, set()).add((item.source_object_type, item.source_object_id))
    for asset in existing_assets:
        if asset.status != "candidate" or asset.asset_type != asset_type:
            continue
        if asset.creator_profile_id == profile.id and mechanism.id in asset.source_mechanism_ids:
            return asset
        sources = provenance_sources.get(asset.id, set())
        if ("content_mechanism", mechanism.id) in sources and ("creator_profile", profile.id) in sources:
            return asset
    return None


def build_user_summary(asset: ContentAsset, proposal: dict[str, Any], warnings: list[str]) -> str:
    history = "；".join(warnings) if warnings else "未发现相同的候选或生效内容资产；近义模板仍需人工判断。"
    return "\n".join(
        [
            "已创建 1 个候选内容资产，但尚未进入内容生成。",
            f"类型：{asset_type_label(asset.asset_type)}",
            f"用途：{asset.description}",
            f"模板概述：{short_text(asset.template, 80)}",
            f"可替换变量：{'、'.join(asset.variables)}",
            f"适用范围：{'、'.join(asset.applicable_scope)}",
            f"不适用范围：{'、'.join(asset.exclusions) or '暂未补充'}",
            f"提案中的账号适配理由：{proposal['account_fit_reason']}",
            f"使用的机制事实：{'；'.join(asset.selected_observed_facts)}",
            f"使用限制：{'；'.join(asset.limitations) or '暂未补充'}",
            f"历史检查：{history}",
            "当前没有可执行的自动激活或决策步骤；后续需要独立实现资产生命周期或显式引用能力。",
        ]
    )


def asset_type_label(asset_type: str) -> str:
    return {
        "title_pattern": "标题公式",
        "cover_structure": "封面结构",
        "opening_template": "开头模板",
        "body_structure": "正文结构",
        "cta_template": "行动引导模板",
        "comparison_framework": "对比表达框架",
        "case_framework": "案例讲述框架",
        "image_text_structure": "图文页结构",
        "topic_framework": "选题框架",
    }[asset_type]


def duplicate_key(asset_type: str, template: str, scope: list[str], profile_id: str) -> tuple[str, str, tuple[str, ...], str]:
    normalized_scope = tuple(sorted({normalized_text(item) for item in scope if normalized_text(item)}))
    return asset_type, normalize_template(template), normalized_scope, profile_id


def normalize_template(template: str) -> str:
    return WHITESPACE_RE.sub(" ", "\n".join(line.rstrip() for line in template.strip().splitlines())).strip()


def normalized_text(value: str) -> str:
    return PUNCTUATION_RE.sub("", value.strip()).casefold()


def unique_required_list(value: Any, field_name: str) -> list[str]:
    items = optional_text_list(value, field_name)
    if not items:
        raise MechanismAssetProposalError(f"{field_name} 不能为空。")
    return items


def optional_text_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise MechanismAssetProposalError(f"{field_name} 必须是文本列表。")
    cleaned: list[str] = []
    for item in value:
        item_text = text(item)
        if not item_text:
            raise MechanismAssetProposalError(f"{field_name} 不能包含空内容。")
        if item_text not in cleaned:
            cleaned.append(item_text)
    if len(cleaned) != len(value):
        raise MechanismAssetProposalError(f"{field_name} 不能重复。")
    return cleaned


def required_text(value: Any, message: str) -> str:
    value_text = text(value)
    if not value_text:
        raise MechanismAssetProposalError(message)
    return value_text


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def stable_id(*parts: str) -> str:
    digest = sha1("::".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"{parts[0]}-{digest}"


def available_asset_id(base_id: str, existing_assets: list[ContentAsset]) -> str:
    used = {asset.id for asset in existing_assets}
    if base_id not in used:
        return base_id
    index = 2
    while f"{base_id}-{index}" in used:
        index += 1
    return f"{base_id}-{index}"


def short_text(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit].rstrip() + "..."
