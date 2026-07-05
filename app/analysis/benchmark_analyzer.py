from __future__ import annotations

from app.analysis.analysis_templates import FALLBACK_TEMPLATE, IMAGE_TEMPLATE, VIDEO_TEMPLATE
from app.models.core import BenchmarkAnalysis, CaptureRecord


def analyze_capture(capture: CaptureRecord) -> BenchmarkAnalysis:
    template = choose_analysis_template(capture)
    uncertainties = list(capture.missing_fields)
    observable_facts = {
        "title": capture.title,
        "body": capture.body,
        "content_type": capture.content_type,
        "author": capture.author,
        "metrics": capture.metrics,
        "comments": capture.comments,
        "images": capture.images,
        "video": capture.video,
    }
    title_has_result = any(token in capture.title for token in ("如何", "区别", "方法", "结果", "新手"))
    has_comments = bool(capture.comments)
    candidate_rule_id = f"candidate-rule-from-{capture.id}-1"

    return BenchmarkAnalysis(
        id=f"analysis-from-{capture.id}",
        capture_id=capture.id,
        analysis_template=template,
        observable_facts=observable_facts,
        topic_analysis={
            "observable": {
                "title": capture.title,
                "body_excerpt": capture.body[:80],
            },
            "inference": "内容围绕一个具体问题给出解释或方法。" if capture.body else "正文不足，无法稳定判断选题承诺。",
        },
        title_analysis={
            "observable": capture.title,
            "inference": "标题有明确问题或结果感。" if title_has_result else "标题结果感不明显，需要人工判断。",
            "risk": "不能仅凭标题判断互动表现原因。",
        },
        cover_analysis={
            "observable": [image.get("alt", "") for image in capture.images],
            "inference": "图文首图可能承担点击理由。" if capture.images else "缺少图片，无法判断封面。",
        },
        structure_analysis={
            "observable": capture.body,
            "inference": "结构接近“对象/问题/做法”。" if capture.body else "正文不足，无法判断结构。",
        },
        visual_analysis={
            "observable": capture.images or capture.video,
            "inference": "需要结合图片序列或视频关键帧进一步判断。",
        },
        audio_analysis={
            "observable": capture.video,
            "inference": "Phase 9 不做音频转写，音频判断保持不确定。" if capture.content_type == "video" else "非视频内容，无音频分析。",
        },
        comment_analysis={
            "observable": capture.comments,
            "inference": "评论可作为真实需求线索。" if has_comments else "缺少评论，无法判断用户异议和衍生需求。",
        },
        engagement_analysis={
            "observable": capture.metrics,
            "inference": "公开互动数据只能作为表现参考，不能解释为确定原因。",
        },
        account_fit={
            "observable": {
                "requested_focus": capture.available_fields,
            },
            "inference": "需要结合账号档案判断是否适配。",
        },
        transferable_elements=[
            item
            for item in [
                "标题围绕具体问题" if capture.title else "",
                "正文提供可转述结构" if capture.body else "",
                "评论可用于衍生选题" if has_comments else "",
            ]
            if item
        ],
        non_transferable_elements=[
            "公开互动数据不能直接当作爆款原因",
            "缺失字段对应的判断不能直接迁移",
        ],
        candidate_rule_ids=[candidate_rule_id],
        derived_topic_ids=[],
        uncertainties=uncertainties,
        confidence=0.65 if uncertainties else 0.85,
        source_type="capture_record",
        source_note=capture.id,
        created_from="analyze-captured-post",
    )


def choose_analysis_template(capture: CaptureRecord) -> str:
    if capture.content_type == "video":
        return VIDEO_TEMPLATE
    if capture.content_type in {"image", "mixed"}:
        return IMAGE_TEMPLATE
    return FALLBACK_TEMPLATE
