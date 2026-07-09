from __future__ import annotations

from typing import Any

from app.models.core import CaptureRecord


FIELD_LABELS = {
    "title": "标题",
    "body": "正文",
    "author": "作者",
    "published_at": "发布时间",
    "images": "图片/封面",
    "video": "视频信息",
    "comments": "可见评论",
}

METRIC_FIELDS = {"metrics", "metrics.likes", "metrics.collects", "metrics.comments", "metrics.shares"}


def build_capture_outcome(record: CaptureRecord) -> dict[str, Any]:
    available_content = labels_from_fields(record.available_fields, record)
    missing_content = labels_from_fields(record.missing_fields)
    limitations = build_limitations(record.missing_fields)
    recommended_action = choose_recommended_action(
        capture_status=record.capture_status,
        missing_fields=record.missing_fields,
        warnings=record.warnings,
        diagnostics=record.diagnostics,
        content_type=record.content_type,
    )
    return build_outcome(
        status_category=record.capture_status,
        available_content=available_content,
        missing_content=missing_content,
        limitations=limitations,
        recommended_action=recommended_action,
        technical_details={
            "capture_status": record.capture_status,
            "capture_method": record.capture_method,
            "content_type": record.content_type,
            "error_code": record.diagnostics.get("error_code"),
            "missing_fields": list(record.missing_fields),
        },
    )


def build_capture_error_outcome(error_code: str, error_message: str = "") -> dict[str, Any]:
    diagnostics = {"error_code": error_code, "error_message": error_message}
    recommended_action = choose_recommended_action(
        capture_status="failed",
        missing_fields=["title", "body"],
        warnings=[f"{error_code}: {error_message}"],
        diagnostics=diagnostics,
        content_type="unknown",
    )
    return build_outcome(
        status_category="failed",
        available_content=[],
        missing_content=["标题", "正文"],
        limitations=["无法判断选题角度和内容结构"],
        recommended_action=recommended_action,
        technical_details={"error_code": error_code},
    )


def build_outcome(
    status_category: str,
    available_content: list[str],
    missing_content: list[str],
    limitations: list[str],
    recommended_action: str,
    technical_details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status_category": normalize_status(status_category),
        "available_content": available_content,
        "missing_content": missing_content,
        "limitations": limitations,
        "recommended_action": recommended_action,
        "user_summary": build_user_summary(
            normalize_status(status_category),
            available_content,
            missing_content,
            limitations,
            recommended_action,
        ),
        "technical_details": technical_details,
    }


def normalize_status(status: str) -> str:
    return status if status in {"success", "partial", "failed"} else "failed"


def labels_from_fields(fields: list[str], record: CaptureRecord | None = None) -> list[str]:
    labels: list[str] = []
    for field in fields:
        label = label_for_field(field)
        if label not in labels:
            labels.append(label)
    if record is not None:
        inferred = infer_available_labels(record)
        for label in inferred:
            if label not in labels:
                labels.append(label)
    return labels


def infer_available_labels(record: CaptureRecord) -> list[str]:
    labels: list[str] = []
    if record.title:
        labels.append("标题")
    if record.body:
        labels.append("正文")
    if record.author:
        labels.append("作者")
    if record.published_at:
        labels.append("发布时间")
    if any(value is not None for value in record.metrics.values()):
        labels.append("互动数据")
    if record.images:
        labels.append("图片/封面")
    if record.video:
        labels.append("视频信息")
    if record.comments:
        labels.append("可见评论")
    return labels


def label_for_field(field: str) -> str:
    if field in METRIC_FIELDS or field.startswith("metrics."):
        return "互动数据"
    return FIELD_LABELS.get(field, field)


def build_limitations(missing_fields: list[str]) -> list[str]:
    limitations: list[str] = []
    if has_any(missing_fields, {"title", "body"}):
        limitations.append("无法稳定判断选题角度和内容结构")
    if has_any(missing_fields, {"images", "video"}):
        limitations.append("无法完整判断封面、图片或视频画面")
    if any(field in METRIC_FIELDS or field.startswith("metrics.") for field in missing_fields):
        limitations.append("无法稳定判断互动表现")
    if "comments" in missing_fields:
        limitations.append("无法判断评论里的真实需求和异议")
    return limitations


def choose_recommended_action(
    capture_status: str,
    missing_fields: list[str],
    warnings: list[str],
    diagnostics: dict[str, Any],
    content_type: str,
) -> str:
    text = " ".join(warnings + [str(diagnostics.get("error_message", "")), str(diagnostics.get("error_code", ""))]).lower()
    error_code = str(diagnostics.get("error_code") or "").lower()
    if diagnostics.get("login_required") or "login_required" in text:
        return "在专用 Chrome 中登录后重试。"
    if diagnostics.get("captcha_detected") or "captcha" in text:
        return "完成人工验证后重试。"
    if error_code == "manual_file_invalid":
        return "复制标题和正文，或重新提供一份可读取的手动内容。"
    if error_code == "playwright_unavailable" or "playwright_unavailable" in text:
        return "改用截图、复制文字或手动内容补充这篇素材。"
    if error_code == "cdp_connection_failed":
        return "确认专用 Chrome 已打开后重试。"
    if error_code == "page_unreachable":
        return "确认链接能打开后重试。"
    if error_code:
        return "补一张截图，或复制标题和正文。"
    if capture_status == "failed":
        if has_any(missing_fields, {"title", "body"}):
            return "补一张截图，或复制标题和正文。"
        return "改用截图、复制文字或手动内容补充这篇素材。"
    if content_type in {"image", "mixed"} and "images" in missing_fields:
        return "补一张截图。"
    if content_type in {"video", "mixed"} and "video" in missing_fields:
        return "补充视频页面截图，或复制可见视频信息。"
    if has_any(missing_fields, {"title", "body"}):
        return "复制标题和正文。"
    if any(field in METRIC_FIELDS or field.startswith("metrics.") for field in missing_fields):
        return "当前信息足够继续分析，但无法判断互动表现。"
    if "comments" in missing_fields:
        return "当前信息足够继续分析；如果想分析用户反馈，再补充可见评论。"
    return "可以继续拆解这篇素材是否值得对标。"


def build_user_summary(
    status_category: str,
    available_content: list[str],
    missing_content: list[str],
    limitations: list[str],
    recommended_action: str,
) -> str:
    status_text = {
        "success": "采集成功。",
        "partial": "已获取部分内容，但不是完整采集。",
        "failed": "这次没有采集到足够内容。",
    }[status_category]
    available_text = "、".join(available_content) if available_content else "暂无可用于拆解的正文内容"
    missing_text = "、".join(missing_content) if missing_content else "暂无"
    limitation_text = "；".join(limitations) if limitations else "当前信息可以进入下一步拆解"
    return (
        f"{status_text}\n"
        f"已获取：{available_text}。\n"
        f"还缺：{missing_text}。\n"
        f"影响：{limitation_text}。\n"
        f"下一步：{recommended_action}"
    )


def has_any(values: list[str], candidates: set[str]) -> bool:
    return any(value in candidates for value in values)
