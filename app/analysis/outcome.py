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


def build_analysis_outcome(
    capture: CaptureRecord,
    analysis: BenchmarkAnalysis,
    requested_focus: list[str] | None = None,
) -> dict[str, Any]:
    observed_facts = build_observed_facts(capture)
    information_gaps = build_information_gaps(capture)
    dimension_limitations = build_dimension_limitations(capture)
    analysis_judgments = build_analysis_judgments(capture)
    status_category = choose_status_category(capture, analysis_judgments, information_gaps, requested_focus or [])
    decision_readiness = build_decision_readiness(capture, status_category, dimension_limitations)
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


def build_analysis_judgments(capture: CaptureRecord) -> list[dict[str, Any]]:
    judgments: list[dict[str, Any]] = []
    if capture.title:
        title_judgment = "标题围绕具体对象或问题展开。"
        if any(token in capture.title for token in ("如何", "区别", "方法", "新手", "为什么")):
            title_judgment = "标题包含明确问题或对象，具备进入内容的理由。"
        judgments.append(
            {
                "dimension": "标题",
                "judgment": title_judgment,
                "evidence": [capture.title],
                "confidence": "medium",
            }
        )
    if capture.body:
        evidence = summarize_text(capture.body)
        confidence = "medium" if len(capture.body) <= 120 else "low"
        judgments.append(
            {
                "dimension": "正文结构",
                "judgment": "正文可以有限判断为围绕问题和做法展开。" if capture.body else "",
                "evidence": [evidence],
                "confidence": confidence,
            }
        )
    comments = visible_comment_texts(capture.comments)
    if comments:
        judgments.append(
            {
                "dimension": "评论",
                "judgment": "可见评论可作为有限的用户需求线索，但不能代表全部评论观点。",
                "evidence": comments[:3],
                "confidence": "low",
            }
        )
    metrics = visible_metric_values(capture.metrics)
    if metrics:
        judgments.append(
            {
                "dimension": "互动表现",
                "judgment": "可见互动数据只能作为有限参考，不能解释为表现好坏或因果原因。",
                "evidence": [format_metrics(metrics)],
                "confidence": "low",
            }
        )
    return [item for item in judgments if item["judgment"]]


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
        else:
            add_unique(gaps, MISSING_FIELD_LABELS["image.content"])
    if capture.content_type in {"video", "mixed"}:
        if not capture.video:
            add_unique(gaps, MISSING_FIELD_LABELS["video"])
        else:
            add_unique(gaps, MISSING_FIELD_LABELS["video.keyframes"])
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
    if capture.content_type in {"image", "mixed"}:
        limitations.append(
            {
                "dimension": "封面与图片",
                "reason": "当前只有图片数量、路径、链接或替代文本，没有图片内容证据",
                "impact": "无法判断封面文字、构图、人物、产品、环境和视觉风格",
            }
        )
    if capture.content_type in {"video", "mixed"}:
        limitations.append(
            {
                "dimension": "视频画面",
                "reason": "当前没有视频关键帧或可见字幕证据",
                "impact": "无法判断前几秒画面、镜头变化、字幕和剪辑节奏",
            }
        )
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
    capture: CaptureRecord,
    judgments: list[dict[str, Any]],
    information_gaps: list[str],
    requested_focus: list[str],
) -> str:
    has_core_text = bool(capture.title or capture.body)
    if not has_core_text:
        return "insufficient"
    if not capture.title or not capture.body:
        return "partial"
    if not judgments:
        return "insufficient"
    focus_gaps = gaps_for_requested_focus(information_gaps, requested_focus)
    if focus_gaps:
        return "partial"
    return "partial" if information_gaps or capture.capture_status != "success" else "complete"


def build_decision_readiness(
    capture: CaptureRecord,
    status_category: str,
    dimension_limitations: list[dict[str, str]],
) -> dict[str, Any]:
    if status_category == "insufficient":
        reason = "缺少标题和正文，当前无法进行有效内容拆解。"
        if capture.title or capture.body:
            reason = "核心内容证据不足，当前只能保留已看到的事实。"
        return {"can_decide_benchmark_value": False, "reason": reason}
    limited_dimensions = "、".join(item["dimension"] for item in dimension_limitations[:3])
    if status_category == "complete":
        return {
            "can_decide_benchmark_value": True,
            "reason": "标题、正文和主要可见证据足够进入是否值得对标的人工判断。",
        }
    reason = "标题或正文证据可用于初步判断选题和结构"
    if limited_dimensions:
        reason += f"；{limited_dimensions}仍有证据限制"
    reason += "。"
    return {"can_decide_benchmark_value": True, "reason": reason}


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
