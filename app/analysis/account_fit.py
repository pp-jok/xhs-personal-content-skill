from __future__ import annotations

from typing import Any

from app.analysis.outcome import build_analysis_outcome
from app.models.core import BenchmarkAnalysis, CaptureRecord, CreatorProfile, now_iso


PROFILE_GAP_FIELDS = {
    "positioning": "账号定位",
    "target_audience": "目标受众",
    "content_style": "内容风格",
    "goals": "运营目标",
    "content_formats": "内容形式",
}

DIMENSION_REQUIREMENTS = {
    "选题": ("positioning", "target_audience"),
    "标题": ("positioning",),
    "正文结构": ("positioning", "content_style"),
    "封面与图片": ("content_style", "content_formats"),
    "视频与视觉": ("content_style", "content_formats"),
    "音频与字幕": ("content_style", "content_formats"),
    "评论": ("target_audience",),
}


def assess_account_fit(
    capture: CaptureRecord,
    analysis: BenchmarkAnalysis,
    profile: CreatorProfile | None,
) -> dict[str, Any]:
    """Assess only dimensions already supported by saved post evidence."""
    if profile is None:
        return insufficient_profile_result()

    analysis_outcome = build_analysis_outcome(capture, analysis)
    profile_gaps = build_profile_gaps(profile)
    assessments = [
        build_assessment(capture, judgment, profile)
        for judgment in analysis_outcome["analysis_judgments"]
    ]
    status_category = choose_status_category(assessments)
    conflicts: list[str] = []
    decision_readiness = build_decision_readiness(assessments, status_category, conflicts)

    return {
        "status_category": status_category,
        "assessments": assessments,
        "profile_gaps": profile_gaps,
        "conflicts": conflicts,
        "overall_summary": build_overall_summary(assessments, status_category),
        "decision_readiness": decision_readiness,
        "source_profile_id": profile.id,
        "source_profile_version": profile.version,
        "active_rule_ids": [],
        "assessed_at": now_iso(),
    }


def build_assessment(
    capture: CaptureRecord,
    judgment: dict[str, Any],
    profile: CreatorProfile,
) -> dict[str, Any]:
    element = str(judgment["dimension"])
    post_evidence = [str(value) for value in judgment.get("evidence", []) if str(value).strip()]
    required_fields = DIMENSION_REQUIREMENTS.get(element, ("positioning",))
    missing_fields = [field for field in required_fields if not profile_field_values(profile, field)]
    profile_evidence = profile_evidence_for(profile, required_fields)

    if missing_fields:
        return assessment(
            element=element,
            classification="insufficient_information",
            post_evidence=post_evidence,
            profile_evidence=profile_evidence,
            reason=f"账号资料缺少{join_labels(missing_fields)}，无法可靠判断{element}是否适合当前账号。",
            adaptation_guidance=f"补充{join_labels(missing_fields)}后再判断这一部分。",
            confidence="low",
        )

    forbidden_expression = find_forbidden_expression(capture, element, profile.forbidden_expressions)
    if forbidden_expression:
        return assessment(
            element=element,
            classification="not_recommended",
            post_evidence=post_evidence,
            profile_evidence=profile_evidence + [f"账号禁用表达：{forbidden_expression}"],
            reason=f"该元素包含账号已明确不使用的表达“{forbidden_expression}”。",
            adaptation_guidance="保留内容结构，但删除或改写这类表达。",
            confidence="high",
        )

    if has_explicit_style_conflict(capture, element, profile.content_style):
        return assessment(
            element=element,
            classification="adaptable",
            post_evidence=post_evidence,
            profile_evidence=profile_evidence,
            reason="内容方法可参考，但当前表达强度与账号已声明的风格不一致。",
            adaptation_guidance="保留方法和结构，改为账号现有的克制、具体表达。",
            confidence="medium",
        )

    if has_explicit_boundary_risk(capture, element, profile.content_style):
        return assessment(
            element=element,
            classification="risky",
            post_evidence=post_evidence,
            profile_evidence=profile_evidence,
            reason="该元素包含绝对承诺，与账号已声明的克制表达边界不一致。",
            adaptation_guidance="删除绝对承诺，改为可验证的具体说明。",
            confidence="high",
        )

    if has_format_mismatch(capture, element, profile.content_formats):
        return assessment(
            element=element,
            classification="adaptable",
            post_evidence=post_evidence,
            profile_evidence=profile_evidence,
            reason="当前帖子形式与账号常用内容形式不同。",
            adaptation_guidance="保留可验证的方法，改写为账号常用内容形式。",
            confidence="medium",
        )

    return assessment(
        element=element,
        classification="directly_borrowable",
        post_evidence=post_evidence,
        profile_evidence=profile_evidence,
        reason="已有帖子证据与账号资料之间没有发现明确冲突。",
        adaptation_guidance="可以借鉴结构或方法，不等于照搬原文。",
        confidence="medium",
    )


def insufficient_profile_result() -> dict[str, Any]:
    return {
        "status_category": "insufficient",
        "assessments": [],
        "profile_gaps": ["尚未找到账号档案，无法判断内容是否适合当前账号。"],
        "conflicts": [],
        "overall_summary": "缺少当前账号资料，暂不形成账号适配判断。",
        "decision_readiness": {
            "can_decide_reference_value": False,
            "reason": "需要先补充账号定位、目标受众和内容风格。",
        },
        "source_profile_id": "",
        "source_profile_version": 0,
        "active_rule_ids": [],
        "assessed_at": now_iso(),
    }


def build_profile_gaps(profile: CreatorProfile) -> list[str]:
    return [f"尚未记录{label}。" for field, label in PROFILE_GAP_FIELDS.items() if not profile_field_values(profile, field)]


def profile_field_values(profile: CreatorProfile, field: str) -> list[str]:
    value = getattr(profile, field)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def profile_evidence_for(profile: CreatorProfile, fields: tuple[str, ...]) -> list[str]:
    evidence: list[str] = []
    for field in fields:
        values = profile_field_values(profile, field)
        if values:
            evidence.append(f"{PROFILE_GAP_FIELDS[field]}：{'、'.join(values)}")
    return evidence


def find_forbidden_expression(
    capture: CaptureRecord,
    element: str,
    forbidden_expressions: list[str],
) -> str:
    if element == "标题":
        source_text = capture.title
    elif element == "选题":
        source_text = f"{capture.title}\n{capture.body}"
    elif element == "正文结构":
        source_text = capture.body
    else:
        return ""
    return next((value for value in forbidden_expressions if value and value in source_text), "")


def has_explicit_style_conflict(capture: CaptureRecord, element: str, content_style: list[str]) -> bool:
    if element not in {"选题", "标题", "正文结构"}:
        return False
    text = f"{capture.title}\n{capture.body}"
    style_text = " ".join(content_style)
    restrained_style = any(marker in style_text for marker in ("克制", "真诚", "专业", "避免夸张"))
    strong_style = any(marker in text for marker in ("强刺激", "夸张", "煽动"))
    return restrained_style and strong_style


def has_format_mismatch(capture: CaptureRecord, element: str, content_formats: list[str]) -> bool:
    if element not in {"封面与图片", "视频与视觉", "音频与字幕"}:
        return False
    content_format = {"image": "图文", "video": "视频"}.get(capture.content_type)
    return bool(content_format and content_formats and content_format not in content_formats)


def has_explicit_boundary_risk(capture: CaptureRecord, element: str, content_style: list[str]) -> bool:
    if element not in {"选题", "标题", "正文结构"}:
        return False
    style_text = " ".join(content_style)
    has_boundary = any(marker in style_text for marker in ("克制", "真诚", "专业", "避免夸张"))
    source_text = capture.title if element == "标题" else f"{capture.title}\n{capture.body}"
    return has_boundary and any(marker in source_text for marker in ("百分之百", "一定", "必然"))


def assessment(
    *,
    element: str,
    classification: str,
    post_evidence: list[str],
    profile_evidence: list[str],
    reason: str,
    adaptation_guidance: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "element": element,
        "classification": classification,
        "post_evidence": post_evidence,
        "profile_evidence": profile_evidence,
        "reason": reason,
        "adaptation_guidance": adaptation_guidance,
        "confidence": confidence,
    }


def choose_status_category(assessments: list[dict[str, Any]]) -> str:
    if not assessments or all(item["classification"] == "insufficient_information" for item in assessments):
        return "insufficient"
    if any(item["classification"] == "insufficient_information" for item in assessments):
        return "partial"
    return "complete"


def build_decision_readiness(
    assessments: list[dict[str, Any]],
    status_category: str,
    conflicts: list[str],
) -> dict[str, Any]:
    assessed_elements = {item["element"] for item in assessments if item["classification"] != "insufficient_information"}
    has_core_text_evidence = {"标题", "正文结构"}.issubset(assessed_elements)
    if status_category == "complete" and has_core_text_evidence and not conflicts:
        return {
            "can_decide_reference_value": True,
            "reason": "标题和正文结构已有账号适配判断，可供你决定是否作为参考。",
        }
    if assessed_elements:
        element_text = "、".join(sorted(assessed_elements))
        return {
            "can_decide_reference_value": False,
            "reason": f"当前只能判断{element_text}，尚不足以决定整篇内容是否值得作为参考。",
        }
    return {
        "can_decide_reference_value": False,
        "reason": "帖子证据或账号资料不足，暂不建议做参考价值决定。",
    }


def build_overall_summary(assessments: list[dict[str, Any]], status_category: str) -> str:
    if status_category == "insufficient":
        return "当前证据不足，暂不形成账号适配判断。"
    usable_count = sum(item["classification"] != "insufficient_information" for item in assessments)
    return f"已完成 {usable_count} 项有证据支持的账号适配判断。"


def build_account_fit_summary(result: dict[str, Any]) -> str:
    assessments = result.get("assessments", [])
    direct = [item for item in assessments if item["classification"] == "directly_borrowable"]
    adaptable = [item for item in assessments if item["classification"] == "adaptable"]
    not_recommended = [item for item in assessments if item["classification"] == "not_recommended"]
    risky = [item for item in assessments if item["classification"] == "risky"]
    insufficient = [item for item in assessments if item["classification"] == "insufficient_information"]
    gaps = list(result.get("profile_gaps", [])) + list(result.get("conflicts", []))

    return "\n\n".join(
        [
            "【帖子中看到的内容】\n" + summarize_post_evidence(assessments),
            "【与你账号的匹配判断】\n" + summarize_items(direct, "可借鉴结构或方法，不能照搬原文。"),
            "【需要调整的地方】\n" + summarize_items(adaptable, "需要按你的账号表达方式改写。"),
            "【不建议直接使用的部分】\n" + summarize_items(not_recommended + risky, "存在明确表达或边界风险。"),
            "【信息不足】\n" + summarize_information_gaps(insufficient, gaps),
            "【是否值得作为你的参考】\n" + str(result["decision_readiness"]["reason"]),
        ]
    )


def summarize_post_evidence(assessments: list[dict[str, Any]]) -> str:
    if not assessments:
        return "当前没有可用于账号适配的帖子证据。"
    return "\n".join(f"- {item['element']}：{item['post_evidence'][0]}" for item in assessments if item["post_evidence"])


def summarize_items(items: list[dict[str, Any]], default: str) -> str:
    if not items:
        return "- 暂无。"
    return "\n".join(f"- {item['element']}：{item['reason']} {item['adaptation_guidance']}" for item in items)


def summarize_information_gaps(insufficient: list[dict[str, Any]], gaps: list[str]) -> str:
    lines = [f"- {item['element']}：{item['reason']}" for item in insufficient]
    lines.extend(f"- {gap}" for gap in gaps)
    return "\n".join(lines) if lines else "- 暂无明显信息缺口。"


def join_labels(fields: list[str]) -> str:
    return "、".join(PROFILE_GAP_FIELDS[field] for field in fields)
