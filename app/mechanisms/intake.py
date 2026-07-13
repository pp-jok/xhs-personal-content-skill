from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Literal, get_args

from app.models.core import (
    CONTENT_MECHANISM_CONFIDENCE_SCORES,
    ContentMechanism,
    ContentMechanismConfidenceLevel,
    ContentMechanismSourceType,
)


MechanismIntakeStatus = Literal["created", "limited_created", "not_enough_evidence", "invalid_input"]

EVIDENCE_LIST_FIELDS = (
    "observed_facts",
    "inferences",
    "user_stated_preferences",
    "missing_information",
    "limitations",
)
ALLOWED_SOURCE_TYPES = set(get_args(ContentMechanismSourceType))
ALLOWED_CONFIDENCE_LEVELS = set(CONTENT_MECHANISM_CONFIDENCE_SCORES)
GENERIC_SUBJECTIVE_FACTS = {
    "很好",
    "有价值",
    "适合学习",
    "不错",
    "很棒",
    "值得借鉴",
    "效果很好",
    "内容优质",
    "适合学",
    "值得学",
    "有用",
    "这个标题挺好",
}
FACT_NORMALIZATION_TABLE = str.maketrans(
    {
        "。": "",
        "，": "",
        ",": "",
        ".": "",
        "！": "",
        "!": "",
        "？": "",
        "?": "",
        "；": "",
        ";": "",
        "：": "",
        ":": "",
        "“": "",
        "”": "",
        "\"": "",
        "'": "",
        " ": "",
    }
)


@dataclass(frozen=True)
class MechanismIntakeResult:
    status_category: MechanismIntakeStatus
    created: bool
    mechanism: ContentMechanism | None
    missing_information: list[str]
    limitations: list[str]
    user_summary: str
    machine_summary: dict[str, Any]

    def to_output(self) -> dict[str, Any]:
        mechanism_id = self.mechanism.id if self.mechanism else ""
        mechanism_status = self.mechanism.status if self.mechanism else ""
        confidence_level = self.mechanism.confidence_level if self.mechanism else ""
        return {
            "mechanism_id": mechanism_id,
            "status_category": self.status_category,
            "mechanism_status": mechanism_status,
            "confidence_level": confidence_level,
            "missing_information": self.missing_information,
            "limitations": self.limitations,
            "user_summary": self.user_summary,
            "machine_summary": self.machine_summary,
        }


def import_mechanism_candidate(payload: dict[str, Any]) -> MechanismIntakeResult:
    if not isinstance(payload, dict):
        return invalid_result("输入格式不符合机制导入要求，暂未保存。请提供一个机制候选对象。")

    try:
        normalized = normalize_payload(payload)
    except ValueError as exc:
        return invalid_result(f"输入格式不符合机制导入要求，暂未保存。{exc}")

    observed_facts = normalized["evidence_summary"]["observed_facts"]
    if not observed_facts:
        return no_evidence_result()
    if all_observed_facts_are_generic_subjective(observed_facts):
        return no_evidence_result()

    status_category = classify_status(normalized)
    confidence_level = choose_confidence_level(normalized, status_category)
    normalized["confidence_level"] = confidence_level
    normalized["confidence"] = CONTENT_MECHANISM_CONFIDENCE_SCORES[confidence_level]
    normalized["status"] = "candidate"
    mechanism = ContentMechanism.from_dict(normalized)
    missing_information = list(mechanism.evidence_summary["missing_information"])
    limitations = combined_limitations(mechanism)
    return MechanismIntakeResult(
        status_category=status_category,
        created=True,
        mechanism=mechanism,
        missing_information=missing_information,
        limitations=limitations,
        user_summary=build_success_summary(
            mechanism=mechanism,
            status_category=status_category,
            missing_information=missing_information,
            limitations=limitations,
        ),
        machine_summary=build_machine_summary(
            mechanism=mechanism,
            status_category=status_category,
            missing_information=missing_information,
            limitations=limitations,
        ),
    )


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    name = normalize_required_text(payload.get("name"), "名称不能为空。")
    description = normalize_required_text(payload.get("description"), "描述不能为空。")
    status = normalize_text(payload.get("status", "candidate"))
    if status != "candidate":
        raise ValueError("当前只能导入候选机制。")

    confidence_level = normalize_text(payload.get("confidence_level", payload.get("confidence", ""))) or "low"
    if confidence_level not in ALLOWED_CONFIDENCE_LEVELS:
        raise ValueError("置信度只能是低、中、高三档。")

    evidence_summary = normalize_evidence_summary(payload.get("evidence_summary"))
    source_refs = normalize_source_refs(payload.get("source_refs", []))
    problem = normalize_text(payload.get("problem", ""))
    solution = normalize_text(payload.get("solution", ""))
    if not problem and not solution:
        raise ValueError("问题或解决方式至少需要填写一项。")

    normalized = {
        "id": normalize_text(payload.get("id", "")) or build_mechanism_id(name, evidence_summary["observed_facts"]),
        "name": name,
        "description": description,
        "created_by": "codex",
        "status": "candidate",
        "confidence_level": confidence_level,
        "source_refs": source_refs,
        "evidence_summary": evidence_summary,
        "problem": problem,
        "solution": solution,
        "pattern": normalize_string_list(payload.get("pattern", []), "pattern"),
        "applicable_scope": normalize_string_list(payload.get("applicable_scope", []), "applicable_scope"),
        "limitations": normalize_string_list(payload.get("limitations", []), "limitations"),
    }
    return normalized


def normalize_evidence_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("证据摘要必须是结构化对象。")
    normalized: dict[str, Any] = {}
    for field_name in EVIDENCE_LIST_FIELDS:
        normalized[field_name] = normalize_string_list(value.get(field_name, []), field_name)
    source_coverage = value.get("source_coverage", {})
    if source_coverage is None:
        source_coverage = {}
    if not isinstance(source_coverage, dict):
        raise ValueError("source_coverage 必须是对象。")
    normalized["source_coverage"] = normalize_source_coverage(source_coverage)
    return normalized


def normalize_source_coverage(value: dict[Any, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("source_coverage 的字段名必须是非空文本。")
        if not isinstance(item, str) or not item.strip():
            raise ValueError("source_coverage 的字段值必须是非空文本。")
        normalized[key.strip()] = item.strip()
    return normalized


def normalize_source_refs(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("来源引用必须是列表。")
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"source_type", "source_id"}:
            raise ValueError("来源引用需要包含来源类型和来源 ID。")
        source_type = normalize_text(item.get("source_type", ""))
        source_id = normalize_text(item.get("source_id", ""))
        if source_type not in ALLOWED_SOURCE_TYPES or not source_id:
            raise ValueError("来源引用无法识别。")
        refs.append({"source_type": source_type, "source_id": source_id})
    return refs


def normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} 必须是文本列表。")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} 必须是文本列表。")
        cleaned = item.strip()
        if cleaned:
            result.append(cleaned)
    return result


def normalize_required_text(value: Any, message: str) -> str:
    text = normalize_text(value)
    if not text:
        raise ValueError(message)
    return text


def normalize_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def build_mechanism_id(name: str, observed_facts: list[str]) -> str:
    seed = name + "|" + "|".join(observed_facts)
    return "mechanism-" + sha1(seed.encode("utf-8")).hexdigest()[:12]


def all_observed_facts_are_generic_subjective(observed_facts: list[str]) -> bool:
    return all(normalize_fact_for_subjective_check(item) in GENERIC_SUBJECTIVE_FACTS for item in observed_facts)


def normalize_fact_for_subjective_check(value: str) -> str:
    return value.strip().translate(FACT_NORMALIZATION_TABLE)


def classify_status(normalized: dict[str, Any]) -> MechanismIntakeStatus:
    evidence = normalized["evidence_summary"]
    if (
        not normalized["source_refs"]
        or len(normalized["source_refs"]) == 1
        or not normalized["problem"]
        or not normalized["solution"]
        or not normalized["pattern"]
        or evidence["missing_information"]
        or evidence["limitations"]
    ):
        return "limited_created"
    return "created"


def choose_confidence_level(
    normalized: dict[str, Any],
    status_category: MechanismIntakeStatus,
) -> ContentMechanismConfidenceLevel:
    requested = normalized["confidence_level"]
    facts = normalized["evidence_summary"]["observed_facts"]
    missing_information = normalized["evidence_summary"]["missing_information"]
    evidence_limitations = normalized["evidence_summary"]["limitations"]
    source_refs = normalized["source_refs"]
    if not source_refs:
        return "low"
    if requested == "high" and (len(facts) <= 1 or missing_information or evidence_limitations):
        return "medium" if source_refs else "low"
    if status_category == "limited_created" and requested == "high":
        return "medium"
    return requested


def combined_limitations(mechanism: ContentMechanism) -> list[str]:
    result: list[str] = []
    for item in mechanism.evidence_summary.get("limitations", []):
        if item not in result:
            result.append(item)
    for item in mechanism.limitations:
        if item not in result:
            result.append(item)
    return result


def build_success_summary(
    mechanism: ContentMechanism,
    status_category: MechanismIntakeStatus,
    missing_information: list[str],
    limitations: list[str],
) -> str:
    if status_category == "created":
        return f"已保存候选内容机制「{mechanism.name}」。证据相对完整，但它目前只作为机制知识，不会影响正式生成。"
    parts = [f"已保存候选内容机制「{mechanism.name}」，但证据还不完整。"]
    if missing_information:
        parts.append("缺少：" + "、".join(missing_information) + "。")
    elif limitations:
        parts.append("限制：" + "、".join(limitations) + "。")
    parts.append("它目前只作为机制知识，不会影响正式生成。")
    return "".join(parts)


def build_machine_summary(
    mechanism: ContentMechanism,
    status_category: MechanismIntakeStatus,
    missing_information: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "mechanism_id": mechanism.id,
        "status_category": status_category,
        "mechanism_status": mechanism.status,
        "confidence_level": mechanism.confidence_level,
        "confidence": mechanism.confidence,
        "source_refs": mechanism.source_refs,
        "missing_information": missing_information,
        "limitations": limitations,
    }


def no_evidence_result() -> MechanismIntakeResult:
    summary = "信息不足，暂不生成内容机制。需要至少一条可观察事实，不能只依赖推断或喜好。"
    return MechanismIntakeResult(
        status_category="not_enough_evidence",
        created=False,
        mechanism=None,
        missing_information=[],
        limitations=[],
        user_summary=summary,
        machine_summary={"status_category": "not_enough_evidence", "created": False},
    )


def invalid_result(summary: str) -> MechanismIntakeResult:
    return MechanismIntakeResult(
        status_category="invalid_input",
        created=False,
        mechanism=None,
        missing_information=[],
        limitations=[],
        user_summary=summary,
        machine_summary={"status_category": "invalid_input", "created": False},
    )
