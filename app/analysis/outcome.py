from __future__ import annotations

from typing import Any

from app.models.core import BenchmarkAnalysis, CaptureRecord


METRIC_LABELS = {
    "likes": "点赞",
    "collects": "收藏",
    "comments": "评论",
    "shares": "分享",
}

MISSING_FIELD_LABELS = {
    "title": "没有获取到标题",
    "body": "没有获取到正文",
    "author": "没有获取到作者信息",
    "published_at": "没有获取到发布时间",
    "images": "没有图片内容证据，无法分析封面和视觉表达",
    "image.content": "没有图片内容证据，无法分析封面和视觉表达",
    "video": "没有视频结构或媒体信息",
    "video.keyframes": "没有视频帧或字幕，无法分析视频画面表达",
    "video.subtitles": "没有视频帧或字幕，无法分析视频画面表达",
    "audio.transcript": "没有音频或字幕转写，无法分析语音和音频表达",
    "comments": "没有评论正文，无法分析用户反馈和异议",
}

ANALYSIS_DIMENSIONS = (
    ("选题", "topic_analysis", "topic"),
    ("标题", "title_analysis", "title"),
    ("正文结构", "structure_analysis", "structure"),
    ("封面与图片", "cover_analysis", "cover"),
    ("视频与视觉", "visual_analysis", "video"),
    ("音频与字幕", "audio_analysis", "audio"),
    ("评论", "comment_analysis", "comments"),
    ("互动表现", "engagement_analysis", "engagement"),
)

FOCUS_DIMENSION_ALIASES = {
    "title": "title",
    "标题": "title",
    "标题角度": "title",
    "标题结构": "title",
    "structure": "structure",
    "正文": "structure",
    "正文结构": "structure",
    "内容结构": "structure",
    "cover": "cover",
    "image": "cover",
    "封面": "cover",
    "封面表达": "cover",
    "visual": "video",
    "视觉": "video",
    "video": "video",
    "视频": "video",
    "镜头": "video",
    "audio": "audio",
    "音频": "audio",
    "字幕": "audio",
    "comments": "comments",
    "comment": "comments",
    "评论": "comments",
    "engagement": "engagement",
    "metrics": "engagement",
    "互动": "engagement",
    "数据表现": "engagement",
}

DIMENSION_LABEL_BY_KEY = {key: label for label, _, key in ANALYSIS_DIMENSIONS}
LIMITATION_MARKERS = ("无法", "不能", "不确定", "缺少", "没有", "只", "仅", "需要", "保持不确定", "不判断", "PR-3A")


def build_analysis_outcome(
    capture: CaptureRecord,
    analysis: BenchmarkAnalysis,
    requested_focus: list[str] | None = None,
) -> dict[str, Any]:
    observed_facts = build_observed_facts(capture)
    information_gaps = build_information_gaps(capture)
    dimension_limitations = build_dimension_limitations(capture)
    analysis_judgments = build_analysis_judgments(capture=capture, analysis=analysis)
    requested_focus_values = requested_focus or []
    status_category = choose_status_category(analysis_judgments, requested_focus_values)
    decision_readiness = build_decision_readiness(
        capture=capture,
        status_category=status_category,
        dimension_limitations=dimension_limitations,
        requested_focus=requested_focus_values,
        analysis_judgments=analysis_judgments,
    )
    return {
        "status_category": status_category,
        "observed_facts": observed_facts,
        "analysis_judgments": analysis_judgments,
        "information_gaps": information_gaps,
        "dimension_limitations": dimension_limitations,
        "decision_readiness": decision_readiness,
        "user_summary": build_user_summary(
            status_category=status_category,
            observed_facts=observed_facts,
            analysis_judgments=analysis_judgments,
            information_gaps=information_gaps,
            decision_readiness=decision_readiness,
        ),
        "technical_details": {
            "capture_id": capture.id,
            "analysis_id": analysis.id,
            "capture_status": capture.capture_status,
            "content_type": capture.content_type,
            "available_fields": list(capture.available_fields),
            "missing_fields": list(capture.missing_fields),
            "requested_focus": list(requested_focus or []),
            "candidate_rule_ids": list(analysis.candidate_rule_ids),
        },
    }


def build_observed_facts(capture: CaptureRecord) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = [{"field": "采集状态", "value": capture.capture_status}]
    if capture.content_type and capture.content_type != "unknown":
        facts.append({"field": "内容类型", "value": content_type_label(capture.content_type)})
    if capture.title:
        facts.append({"field": "标题", "value": capture.title})
    if capture.body:
        facts.append({"field": "正文", "value": summarize_text(capture.body)})
    if capture.author:
        name = capture.author.get("name") or capture.author.get("nickname")
        if name:
            facts.append({"field": "作者", "value": str(name)})
    if capture.published_at:
        facts.append({"field": "发布时间", "value": capture.published_at})
    visible_metrics = visible_metric_values(capture.metrics)
    if visible_metrics:
        facts.append({"field": "可见互动指标", "value": visible_metrics})
    if capture.images:
        facts.append({"field": "图片结构", "value": f"{len(capture.images)} 张图片可见或已保存"})
    if capture.video:
        facts.append({"field": "视频结构", "value": "已采集到视频结构或媒体信息"})
    visible_comments = visible_comment_texts(capture.comments)
    if visible_comments:
        facts.append({"field": "可见评论", "value": visible_comments})
    return facts


def build_analysis_judgments(capture: CaptureRecord, analysis: BenchmarkAnalysis) -> list[dict[str, Any]]:
    judgments: list[dict[str, Any]] = []
    for label, field_name, evidence_key in ANALYSIS_DIMENSIONS:
        analysis_field = getattr(analysis, field_name)
        if not isinstance(analysis_field, dict):
            continue
        inference = str(analysis_field.get("inference") or "").strip()
        evidence = evidence_for_dimension(capture, analysis_field.get("observable"), evidence_key)
        if not evidence:
            continue
        if not is_usable_inference(evidence_key, inference, evidence):
            continue
        judgments.append(
            {
                "dimension": label,
                "judgment": inference,
                "evidence": evidence,
                "confidence": confidence_label(analysis.confidence),
            }
        )
    return judgments


def build_information_gaps(capture: CaptureRecord) -> list[str]:
    gaps: list[str] = []
    if not capture.title:
        add_unique(gaps, MISSING_FIELD_LABELS["title"])
    if not capture.body:
        add_unique(gaps, MISSING_FIELD_LABELS["body"])
    if not visible_metric_values(capture.metrics):
        add_unique(gaps, "没有获取到完整互动数据")
    if capture.content_type in {"image", "mixed"}:
        if not capture.images:
            add_unique(gaps, "没有图片结构证据，无法分析封面和视觉表达")
        elif not has_image_content_evidence(capture):
            add_unique(gaps, MISSING_FIELD_LABELS["image.content"])
    if capture.content_type in {"video", "mixed"}:
        if not capture.video:
            add_unique(gaps, MISSING_FIELD_LABELS["video"])
        else:
            if not has_video_content_evidence(capture):
                add_unique(gaps, MISSING_FIELD_LABELS["video.keyframes"])
            if not has_audio_content_evidence(capture):
                add_unique(gaps, MISSING_FIELD_LABELS["audio.transcript"])
    if not visible_comment_texts(capture.comments):
        add_unique(gaps, MISSING_FIELD_LABELS["comments"])
    for field in capture.missing_fields:
        if field.startswith("metrics."):
            add_unique(gaps, "没有获取到完整互动数据")
        elif field in MISSING_FIELD_LABELS:
            add_unique(gaps, MISSING_FIELD_LABELS[field])
    return gaps


def build_dimension_limitations(capture: CaptureRecord) -> list[dict[str, str]]:
    limitations: list[dict[str, str]] = []
    if not capture.title:
        limitations.append(
            {
                "dimension": "标题",
                "reason": "当前没有标题原文",
                "impact": "无法判断标题结构、进入理由和表达风格",
            }
        )
    if not capture.body:
        limitations.append(
            {
                "dimension": "正文结构",
                "reason": "当前没有正文或脚本文字",
                "impact": "无法判断内容展开路径、信息密度和行动指导",
            }
        )
    if capture.content_type in {"image", "mixed"} and not has_image_content_evidence(capture):
        limitations.append(
            {
                "dimension": "封面与图片",
                "reason": "当前只有图片数量、路径、链接或替代文本，没有图片内容证据",
                "impact": "无法判断封面文字、构图、人物、产品、环境和视觉风格",
            }
        )
    if capture.content_type in {"video", "mixed"} and not has_video_content_evidence(capture):
        limitations.append(
            {
                "dimension": "视频画面",
                "reason": "当前没有视频关键帧或可见字幕证据",
                "impact": "无法判断前几秒画面、镜头变化、字幕和剪辑节奏",
            }
        )
    if capture.content_type in {"video", "mixed"} and not has_audio_content_evidence(capture):
        limitations.append(
            {
                "dimension": "音频和字幕",
                "reason": "当前没有音频或字幕转写",
                "impact": "无法判断语音、音乐和口播表达",
            }
        )
    if not visible_comment_texts(capture.comments):
        limitations.append(
            {
                "dimension": "评论",
                "reason": "当前没有评论正文",
                "impact": "无法分析用户反馈、异议和衍生需求",
            }
        )
    if not visible_metric_values(capture.metrics):
        limitations.append(
            {
                "dimension": "互动表现",
                "reason": "当前没有完整可见互动数据",
                "impact": "无法判断互动表现；即使有公开指标，也不能推断因果原因",
            }
        )
    return limitations


def choose_status_category(
    judgments: list[dict[str, Any]],
    requested_focus: list[str],
) -> str:
    if not judgments:
        return "insufficient"
    required_dimensions = normalize_requested_focus(requested_focus) or ["title", "structure"]
    fulfilled_dimensions = {dimension_key_for_label(item["dimension"]) for item in judgments}
    fulfilled_required = [dimension for dimension in required_dimensions if dimension in fulfilled_dimensions]
    if len(fulfilled_required) == len(required_dimensions):
        return "complete"
    return "partial" if fulfilled_required else "insufficient"


def build_decision_readiness(
    capture: CaptureRecord,
    status_category: str,
    dimension_limitations: list[dict[str, str]],
    requested_focus: list[str] | None = None,
    analysis_judgments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requested_dimensions = normalize_requested_focus(requested_focus or [])
    required_dimensions = requested_dimensions or ["title", "structure"]
    fulfilled_dimensions = fulfilled_dimension_keys(analysis_judgments or [])
    fulfilled_required = [dimension for dimension in required_dimensions if dimension in fulfilled_dimensions]
    missing_required = [dimension for dimension in required_dimensions if dimension not in fulfilled_dimensions]
    can_decide_requested_focus = bool(required_dimensions) and not missing_required
    is_default_core = not requested_dimensions
    can_decide_benchmark_value = is_default_core and can_decide_requested_focus

    if requested_dimensions:
        reason = build_requested_focus_reason(fulfilled_required, missing_required)
    else:
        reason = build_default_readiness_reason(fulfilled_required, missing_required, capture)

    return {
        "can_decide_benchmark_value": can_decide_benchmark_value,
        "can_decide_requested_focus": can_decide_requested_focus,
        "reason": reason,
    }


def build_user_summary(
    status_category: str,
    observed_facts: list[dict[str, Any]],
    analysis_judgments: list[dict[str, Any]],
    information_gaps: list[str],
    decision_readiness: dict[str, Any],
) -> str:
    fact_text = summarize_fact_labels(observed_facts)
    judgment_text = summarize_judgments(analysis_judgments)
    gap_text = "\n".join(f"- {gap}" for gap in information_gaps[:4]) if information_gaps else "- 暂无明显信息缺口"
    decision_text = decision_readiness["reason"]
    if status_category == "insufficient":
        decision_text = f"当前证据不足。{decision_text}"
    elif status_category == "partial":
        decision_text = f"目前可以进入初步人工判断，但不是完整采集或完整分析。{decision_text}"
    return (
        "【客观数据】\n"
        f"{fact_text}\n\n"
        "【Codex 判断】\n"
        f"{judgment_text}\n\n"
        "【信息不足】\n"
        f"{gap_text}\n\n"
        "【是否可以继续判断】\n"
        f"{decision_text}"
    )


def summarize_fact_labels(facts: list[dict[str, Any]]) -> str:
    labels = [item["field"] for item in facts if item["field"] != "采集状态"]
    if not labels:
        return "目前只保留了采集状态，没有足够正文内容。"
    return "已获取：" + "、".join(labels) + "。"


def summarize_judgments(judgments: list[dict[str, Any]]) -> str:
    if not judgments:
        return "当前证据不足，暂不形成内容判断。"
    return "\n".join(f"- {item['dimension']}：{item['judgment']}" for item in judgments[:4])


def visible_metric_values(metrics: dict[str, Any]) -> dict[str, Any]:
    return {METRIC_LABELS.get(key, key): value for key, value in metrics.items() if value is not None}


def visible_comment_texts(comments: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for comment in comments:
        text = str(comment.get("content") or comment.get("text") or "").strip()
        if text:
            texts.append(text)
    return texts


def format_metrics(metrics: dict[str, Any]) -> str:
    return "、".join(f"{key}{value}" for key, value in metrics.items())


def summarize_text(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def content_type_label(content_type: str) -> str:
    return {"image": "图文", "video": "视频", "mixed": "图文/视频"}.get(content_type, content_type)


def evidence_for_dimension(capture: CaptureRecord, observable: Any, dimension: str) -> list[str]:
    if dimension == "topic":
        return compact_evidence([capture.title, summarize_text(capture.body) if capture.body else ""])
    if dimension == "title":
        return compact_evidence([capture.title])
    if dimension == "structure":
        return compact_evidence([summarize_text(capture.body) if capture.body else ""])
    if dimension == "cover":
        return image_content_evidence(capture, observable)
    if dimension == "video":
        return video_content_evidence(capture, observable)
    if dimension == "audio":
        return audio_content_evidence(capture, observable)
    if dimension == "comments":
        return visible_comment_texts(capture.comments)[:3]
    if dimension == "engagement":
        metrics = visible_metric_values(capture.metrics)
        return [format_metrics(metrics)] if metrics else []
    return observable_evidence(observable)


def image_content_evidence(capture: CaptureRecord, observable: Any) -> list[str]:
    evidence: list[str] = []
    for image in capture.images:
        for key in ("content_text", "ocr_text", "description", "visible_text"):
            value = str(image.get(key) or "").strip()
            if value:
                evidence.append(value)
    return compact_evidence(evidence)


def video_content_evidence(capture: CaptureRecord, observable: Any) -> list[str]:
    evidence: list[str] = []
    for key in ("keyframes", "subtitles", "visible_text", "description"):
        value = capture.video.get(key)
        if isinstance(value, list):
            evidence.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            evidence.append(str(value).strip())
    return compact_evidence(evidence)


def audio_content_evidence(capture: CaptureRecord, observable: Any) -> list[str]:
    evidence: list[str] = []
    for key in ("transcript", "audio_transcript", "subtitles"):
        value = capture.video.get(key)
        if value:
            evidence.append(str(value).strip())
    return compact_evidence(evidence)


def has_image_content_evidence(capture: CaptureRecord) -> bool:
    return bool(image_content_evidence(capture, None))


def has_video_content_evidence(capture: CaptureRecord) -> bool:
    return bool(video_content_evidence(capture, None))


def has_audio_content_evidence(capture: CaptureRecord) -> bool:
    return bool(audio_content_evidence(capture, None))


def observable_evidence_for_keys(observable: Any, keys: set[str]) -> list[str]:
    if not isinstance(observable, dict):
        return []
    evidence: list[str] = []
    for key in keys:
        value = observable.get(key)
        if isinstance(value, list):
            evidence.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            evidence.append(str(value).strip())
    return evidence


def observable_evidence(observable: Any) -> list[str]:
    if isinstance(observable, str):
        return compact_evidence([observable])
    if isinstance(observable, dict):
        return compact_evidence(str(value) for value in observable.values() if value)
    if isinstance(observable, list):
        return compact_evidence(str(value) for value in observable if value)
    return []


def compact_evidence(values: Any) -> list[str]:
    evidence: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in evidence:
            evidence.append(text)
    return evidence


def is_usable_inference(dimension: str, inference: str, evidence: list[str]) -> bool:
    if not inference:
        return False
    if dimension == "engagement" and evidence:
        return "参考" in inference and not any(marker in inference for marker in ("缺少", "没有", "无法判断", "不足"))
    return is_positive_inference(inference)


def is_positive_inference(inference: str) -> bool:
    if not inference:
        return False
    return not any(marker in inference for marker in LIMITATION_MARKERS)


def confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"


def normalize_requested_focus(requested_focus: list[str]) -> list[str]:
    normalized: list[str] = []
    for focus in requested_focus:
        mapped = FOCUS_DIMENSION_ALIASES.get(focus.strip())
        if mapped and mapped not in normalized:
            normalized.append(mapped)
    return normalized


def dimension_key_for_label(label: str) -> str:
    for dimension_label, _, key in ANALYSIS_DIMENSIONS:
        if label == dimension_label:
            return key
    return ""


def fulfilled_dimension_keys(judgments: list[dict[str, Any]]) -> set[str]:
    return {dimension_key_for_label(item["dimension"]) for item in judgments}


def build_requested_focus_reason(fulfilled_required: list[str], missing_required: list[str]) -> str:
    if not missing_required:
        if fulfilled_required == ["title"]:
            return "标题证据足够，可以判断标题表达。其他未请求维度仍可能存在信息缺口。"
        if fulfilled_required == ["engagement"]:
            return "已有可见互动指标，可进行有限参考，但不能据此判断互动水平或产生原因。"
        labels = join_dimension_labels(fulfilled_required)
        return f"{labels}证据足够，可以判断用户请求的维度。其他未请求维度仍可能存在信息缺口。"
    if not fulfilled_required:
        if "cover" in missing_required:
            return "当前只有图片结构，没有图片内容证据，暂时不能判断封面表达。"
        labels = join_dimension_labels(missing_required)
        return f"{labels}证据不足，暂时不能判断用户请求的维度。"
    fulfilled_text = join_partial_fulfilled_labels(fulfilled_required)
    missing_text = join_dimension_labels(missing_required)
    return f"{fulfilled_text}可以判断，但{missing_text}证据不足，当前只能进行部分判断。"


def build_default_readiness_reason(fulfilled_required: list[str], missing_required: list[str], capture: CaptureRecord) -> str:
    if not missing_required:
        return "标题和正文结构证据足够，可以进入是否值得对标的初步人工判断。"
    if not fulfilled_required:
        if capture.title or capture.body:
            return "核心内容证据不足，当前只能保留已看到的事实。"
        return "缺少标题和正文，当前无法进行有效内容拆解。"
    fulfilled_text = join_partial_fulfilled_labels(fulfilled_required)
    missing_text = join_dimension_labels(missing_required)
    return f"{fulfilled_text}可以判断，但{missing_text}证据不足，当前只能进行部分判断。"


def join_dimension_labels(dimensions: list[str]) -> str:
    return "和".join(DIMENSION_LABEL_BY_KEY.get(dimension, dimension) for dimension in dimensions)


def join_partial_fulfilled_labels(dimensions: list[str]) -> str:
    if dimensions == ["title"]:
        return "标题"
    if dimensions == ["structure"]:
        return "正文结构"
    return join_dimension_labels(dimensions)


def gaps_for_requested_focus(information_gaps: list[str], requested_focus: list[str]) -> list[str]:
    focus_text = " ".join(requested_focus).lower()
    if not focus_text:
        return []
    matched: list[str] = []
    if "title" in focus_text and any("标题" in gap for gap in information_gaps):
        matched.append("title")
    if "structure" in focus_text and any("正文" in gap for gap in information_gaps):
        matched.append("structure")
    if ("cover" in focus_text or "image" in focus_text) and any("图片" in gap for gap in information_gaps):
        matched.append("image")
    if "video" in focus_text and any("视频" in gap for gap in information_gaps):
        matched.append("video")
    if "comment" in focus_text and any("评论" in gap for gap in information_gaps):
        matched.append("comment")
    return matched


def add_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
