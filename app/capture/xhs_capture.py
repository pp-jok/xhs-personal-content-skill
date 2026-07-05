from __future__ import annotations

from typing import Any

from app.capture.capture_errors import CaptureInputError
from app.capture.browser import BrowserCaptureResult
from app.capture.capture_result import NormalizedCaptureInput
from app.models.core import CaptureRecord, ContentInboxItem, now_iso


REQUIRED_VISIBLE_FIELDS = ("title", "body")
METRIC_FIELDS = ("likes", "collects", "comments", "shares")


def build_capture_record(
    inbox_item: ContentInboxItem,
    manual_data: dict[str, Any] | None = None,
    capture_id: str | None = None,
) -> CaptureRecord:
    if manual_data is None:
        return CaptureRecord(
            id=capture_id or f"capture-from-{inbox_item.id}",
            inbox_item_id=inbox_item.id,
            source_url=inbox_item.source_url,
            canonical_url=inbox_item.source_url,
            capture_method="browser_authorized",
            capture_status="failed",
            content_type="unknown",
            metrics={field: None for field in METRIC_FIELDS},
            available_fields=[],
            missing_fields=["title", "body", "author", "metrics", "images", "video", "comments"],
            warnings=["未提供可见页面内容；本地工具不会绕过登录、验证码、风控或访问限制。"],
            diagnostics={"page_reachable": False, "error_code": "cdp_url_missing"},
            confidence=0.0,
            created_from="capture-xhs-link",
        )

    normalized = normalize_manual_capture(manual_data)
    available_fields = collect_available_fields(normalized)
    missing_fields = collect_missing_fields(normalized)
    status = "success" if not missing_fields else "partial"
    warnings = list(manual_data.get("warnings", [])) if isinstance(manual_data.get("warnings", []), list) else []
    if missing_fields:
        warnings.append("采集结果不完整，缺失字段已记录。")

    return CaptureRecord(
        id=capture_id or f"capture-from-{inbox_item.id}",
        inbox_item_id=inbox_item.id,
        source_url=inbox_item.source_url,
        canonical_url=inbox_item.source_url,
        capture_method="manual",
        capture_status=status,
        captured_at=now_iso(),
        title=normalized.title,
        body=normalized.body,
        content_type=normalized.content_type,
        author=normalized.author,
        metrics=normalized.metrics,
        images=normalized.images,
        video=normalized.video,
        comments=normalized.comments,
        available_fields=available_fields,
        missing_fields=missing_fields,
        warnings=warnings,
        raw_snapshot_path=normalized.raw_snapshot_path,
        diagnostics={},
        confidence=0.9 if status == "success" else 0.6,
        source_type="user_visible_manual_capture",
        created_from="capture-xhs-link",
    )


def build_browser_capture_record(
    inbox_item: ContentInboxItem,
    browser_result: BrowserCaptureResult,
    capture_id: str | None = None,
) -> CaptureRecord:
    return CaptureRecord(
        id=capture_id or f"capture-from-{inbox_item.id}",
        inbox_item_id=inbox_item.id,
        source_url=browser_result.source_url or inbox_item.source_url,
        canonical_url=browser_result.canonical_url,
        capture_method="browser_authorized",
        capture_status=browser_result.capture_status,
        captured_at=now_iso(),
        published_at=browser_result.published_at,
        title=browser_result.title,
        body=browser_result.body,
        content_type=browser_result.content_type,
        author=browser_result.author,
        metrics=browser_result.metrics,
        images=browser_result.images,
        video=browser_result.video,
        comments=browser_result.comments,
        available_fields=browser_result.available_fields,
        missing_fields=browser_result.missing_fields,
        warnings=browser_result.warnings,
        raw_snapshot_path=browser_result.raw_snapshot_path,
        diagnostics=browser_result.diagnostics,
        confidence=0.85 if browser_result.capture_status == "success" else 0.45,
        source_type="browser_authorized_capture",
        created_from="capture-xhs-link",
    )


def normalize_manual_capture(data: dict[str, Any]) -> NormalizedCaptureInput:
    if not isinstance(data, dict):
        raise CaptureInputError("manual capture file must contain a JSON object")
    metrics = data.get("metrics", {})
    if metrics is None:
        metrics = {}
    if not isinstance(metrics, dict):
        raise CaptureInputError("manual capture metrics must be an object")

    return NormalizedCaptureInput(
        title=text_or_empty(data.get("title")),
        body=text_or_empty(data.get("body")),
        content_type=normalize_content_type(data.get("content_type")),
        author=dict_or_empty(data.get("author")),
        metrics={field: metrics.get(field) for field in METRIC_FIELDS},
        images=list_of_dicts(data.get("images"), "images"),
        video=dict_or_empty(data.get("video")),
        comments=list_of_dicts(data.get("comments"), "comments"),
        raw_snapshot_path=text_or_empty(data.get("raw_snapshot_path")),
    )


def collect_available_fields(data: NormalizedCaptureInput) -> list[str]:
    fields: list[str] = []
    if data.title:
        fields.append("title")
    if data.body:
        fields.append("body")
    if data.author:
        fields.append("author")
    for key, value in data.metrics.items():
        if value is not None:
            fields.append(f"metrics.{key}")
    if data.images:
        fields.append("images")
    if data.video:
        fields.append("video")
    if data.comments:
        fields.append("comments")
    return fields


def collect_missing_fields(data: NormalizedCaptureInput) -> list[str]:
    missing = [field for field in REQUIRED_VISIBLE_FIELDS if not getattr(data, field)]
    if not data.author:
        missing.append("author")
    for key, value in data.metrics.items():
        if value is None:
            missing.append(f"metrics.{key}")
    if data.content_type in ("image", "mixed") and not data.images:
        missing.append("images")
    if data.content_type in ("video", "mixed") and not data.video:
        missing.append("video")
    return missing


def normalize_content_type(value: Any) -> str:
    if value in {"image", "video", "mixed"}:
        return str(value)
    return "unknown"


def text_or_empty(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_of_dicts(value: Any, field_name: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CaptureInputError(f"manual capture {field_name} must be a list of objects")
    return value
