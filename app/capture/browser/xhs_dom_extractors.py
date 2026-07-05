from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.capture.browser.capture_diagnostics import CaptureDiagnostics


METRIC_FIELDS = ("likes", "collects", "comments", "shares")


@dataclass
class BrowserCaptureResult:
    source_url: str
    canonical_url: str
    capture_status: str
    title: str = ""
    body: str = ""
    content_type: str = "unknown"
    author: dict[str, Any] = field(default_factory=dict)
    published_at: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)
    video: dict[str, Any] = field(default_factory=dict)
    comments: list[dict[str, Any]] = field(default_factory=list)
    available_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_snapshot_path: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


class XhsVisibleContentParser(HTMLParser):
    def __init__(self, comment_limit: int = 30) -> None:
        super().__init__(convert_charrefs=True)
        self.comment_limit = comment_limit
        self.current_field: str | None = None
        self.current_metric: str | None = None
        self.title = ""
        self.body_parts: list[str] = []
        self.author_name = ""
        self.published_at: str | None = None
        self.metrics: dict[str, Any] = {field: None for field in METRIC_FIELDS}
        self.images: list[dict[str, Any]] = []
        self.video: dict[str, Any] = {}
        self.comments: list[dict[str, Any]] = []
        self.login_required = False
        self.captcha_detected = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "meta":
            self._read_meta(attr)
            return
        if "data-xhs-login-required" in attr:
            self.login_required = True
        if "data-xhs-captcha" in attr:
            self.captcha_detected = True
        if "data-xhs-title" in attr:
            self.current_field = "title"
        elif "data-xhs-body" in attr:
            self.current_field = "body"
        elif "data-xhs-author" in attr:
            self.current_field = "author"
        elif "data-xhs-comment" in attr and len(self.comments) < self.comment_limit:
            self.current_field = "comment"
        elif "data-xhs-metric" in attr:
            self.current_metric = attr["data-xhs-metric"]
            self.current_field = "metric"
        elif tag == "time" and "data-xhs-published-at" in attr:
            self.published_at = attr.get("datetime") or attr.get("title") or None
            self.current_field = "published_at" if not self.published_at else None
        elif tag == "img" and "data-xhs-image" in attr:
            self.images.append(
                {
                    "remote_url": attr.get("src", ""),
                    "alt": attr.get("alt", ""),
                    "width": parse_int(attr.get("width")),
                    "height": parse_int(attr.get("height")),
                    "download_status": "not_attempted",
                }
            )
        elif tag == "video" and "data-xhs-video" in attr:
            self.video = {
                "src": attr.get("src", ""),
                "poster": attr.get("poster", ""),
                "download_status": "not_attempted",
            }

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "article", "a", "p", "span", "time"}:
            self.current_field = None
            self.current_metric = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self.current_field == "title" and not self.title:
            self.title = text
        elif self.current_field == "body":
            if text not in self.body_parts:
                self.body_parts.append(text)
        elif self.current_field == "author" and not self.author_name:
            self.author_name = text
        elif self.current_field == "published_at" and not self.published_at:
            self.published_at = text
        elif self.current_field == "comment" and len(self.comments) < self.comment_limit:
            self.comments.append({"content": text})
        elif self.current_field == "metric" and self.current_metric in METRIC_FIELDS:
            self.metrics[self.current_metric] = parse_metric(text)

    def _read_meta(self, attr: dict[str, str]) -> None:
        name = attr.get("name") or attr.get("property")
        content = attr.get("content", "").strip()
        if not content:
            return
        if name == "og:title" and not self.title:
            self.title = content
        elif name == "description" and not self.body_parts:
            self.body_parts.append(content)


def extract_visible_content(
    html: str,
    source_url: str,
    canonical_url: str,
    output_dir: Path,
    comment_limit: int = 30,
) -> BrowserCaptureResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = output_dir / "page.html"
    snapshot_path.write_text(html, encoding="utf-8")

    parser = XhsVisibleContentParser(comment_limit=comment_limit)
    parser.feed(html)
    hydration = extract_hydration_note(html, comment_limit=comment_limit)
    apply_hydration(parser, hydration)
    body = "\n".join(parser.body_parts).strip()
    diagnostics = CaptureDiagnostics(
        login_required=parser.login_required,
        captcha_detected=parser.captcha_detected,
        comment_limit=comment_limit,
    )
    content_type = infer_content_type(parser.images, parser.video)
    available_fields = collect_available_fields(parser, body)
    missing_fields = collect_missing_fields(parser, body, content_type)
    diagnostics.selectors_succeeded = list(available_fields)
    diagnostics.selectors_failed = missing_fields[:]

    warnings: list[str] = []
    if parser.login_required:
        warnings.append("login_required: 当前页面需要登录，未尝试绕过。")
    if parser.captcha_detected:
        warnings.append("captcha_detected: 当前页面出现验证码或人机验证，未尝试绕过。")
    if missing_fields:
        warnings.append("部分页面字段未采集到，已记录缺失字段和选择器诊断。")

    capture_status = decide_status(parser, body, content_type)
    diagnostics_path = output_dir / "diagnostics.json"
    diagnostics_path.write_text(json.dumps(diagnostics.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    return BrowserCaptureResult(
        source_url=source_url,
        canonical_url=canonical_url,
        capture_status=capture_status,
        title=parser.title,
        body=body,
        content_type=content_type,
        author={"name": parser.author_name} if parser.author_name else {},
        published_at=parser.published_at,
        metrics=parser.metrics,
        images=parser.images,
        video=parser.video,
        comments=parser.comments[:comment_limit],
        available_fields=available_fields,
        missing_fields=missing_fields,
        warnings=warnings,
        raw_snapshot_path=str(snapshot_path),
        diagnostics=diagnostics.to_dict(),
    )


def infer_content_type(images: list[dict[str, Any]], video: dict[str, Any]) -> str:
    if video:
        return "video"
    if images:
        return "image"
    return "unknown"


def decide_status(parser: XhsVisibleContentParser, body: str, content_type: str) -> str:
    if parser.login_required or parser.captcha_detected:
        return "failed"
    has_text = bool(parser.title or body)
    if content_type == "video":
        return "success" if has_text and parser.video else "failed"
    if content_type == "image":
        return "success" if has_text and parser.images else "failed"
    if content_type == "mixed":
        return "success" if has_text and (parser.images or parser.video) else "failed"
    if has_text:
        return "partial"
    return "failed"


def collect_available_fields(parser: XhsVisibleContentParser, body: str) -> list[str]:
    fields: list[str] = []
    if parser.title:
        fields.append("title")
    if body:
        fields.append("body")
    if parser.author_name:
        fields.append("author")
    if parser.published_at:
        fields.append("published_at")
    for key, value in parser.metrics.items():
        if value is not None:
            fields.append(f"metrics.{key}")
    if parser.images:
        fields.append("images")
    if parser.video:
        fields.append("video")
    if parser.comments:
        fields.append("comments")
    return fields


def collect_missing_fields(parser: XhsVisibleContentParser, body: str, content_type: str) -> list[str]:
    missing: list[str] = []
    if not parser.title:
        missing.append("title")
    if not body:
        missing.append("body")
    if not parser.author_name:
        missing.append("author")
    if not parser.published_at:
        missing.append("published_at")
    for key, value in parser.metrics.items():
        if value is None:
            missing.append(f"metrics.{key}")
    if content_type == "image" and not parser.images:
        missing.append("images")
    if content_type == "video" and not parser.video:
        missing.append("video")
    if not parser.comments:
        missing.append("comments")
    return missing


def parse_metric(value: str) -> int | None:
    normalized = value.strip().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", normalized)
    if not match:
        return None
    number = float(match.group(1))
    if "万" in normalized:
        number *= 10000
    return int(number)


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def extract_hydration_note(html: str, comment_limit: int) -> dict[str, Any]:
    note_map = extract_balanced_json_after_key(html, '"noteDetailMap"')
    if note_map is None:
        note_map = extract_balanced_json_after_key(html, "noteDetailMap")
    if not note_map:
        return {}
    try:
        parsed = json.loads(note_map)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict) or not parsed:
        return {}
    first = next(iter(parsed.values()))
    if not isinstance(first, dict):
        return {}
    note = first.get("note")
    if not isinstance(note, dict):
        return {}
    comments = first.get("comments") if isinstance(first.get("comments"), list) else []
    return {"note": note, "comments": comments[:comment_limit]}


def extract_balanced_json_after_key(text: str, key: str) -> str | None:
    key_index = text.find(key)
    if key_index < 0:
        return None
    start = text.find("{", key_index)
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def apply_hydration(parser: XhsVisibleContentParser, hydration: dict[str, Any]) -> None:
    note = hydration.get("note")
    if not isinstance(note, dict):
        return
    parser.title = parser.title or text_value(note.get("title"))
    desc = text_value(note.get("desc"))
    if desc and desc not in parser.body_parts:
        parser.body_parts.append(desc)
    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    nickname = text_value(user.get("nickname")) if isinstance(user, dict) else ""
    if nickname and not parser.author_name:
        parser.author_name = nickname
    if not parser.published_at:
        parser.published_at = normalize_timestamp(note.get("time") or note.get("lastUpdateTime"))
    interact = note.get("interactInfo") if isinstance(note.get("interactInfo"), dict) else {}
    if isinstance(interact, dict):
        parser.metrics["likes"] = parser.metrics["likes"] if parser.metrics["likes"] is not None else parse_metric(str(interact.get("likedCount", "")))
        parser.metrics["collects"] = (
            parser.metrics["collects"] if parser.metrics["collects"] is not None else parse_metric(str(interact.get("collectedCount", "")))
        )
        parser.metrics["comments"] = (
            parser.metrics["comments"] if parser.metrics["comments"] is not None else parse_metric(str(interact.get("commentCount", "")))
        )
        parser.metrics["shares"] = (
            parser.metrics["shares"] if parser.metrics["shares"] is not None else parse_metric(str(interact.get("shareCount", "")))
        )
    image_list = note.get("imageList")
    if isinstance(image_list, list) and not parser.images:
        parser.images = [
            {
                "position": index + 1,
                "remote_url": "<redacted>",
                "alt": "",
                "download_status": "skipped_sensitive_url",
                "source": "hydration_state",
            }
            for index, _item in enumerate(image_list)
        ]
    video = note.get("video")
    if isinstance(video, dict) and not parser.video:
        parser.video = {
            "evidence": "hydration_state",
            "download_status": "skipped_sensitive_url",
            "has_media": bool(video.get("media") or video.get("mediaV2")),
        }
    comments = hydration.get("comments")
    if isinstance(comments, list) and not parser.comments:
        for item in comments[: parser.comment_limit]:
            if isinstance(item, dict):
                content = text_value(item.get("content"))
                if content:
                    parser.comments.append({"content": content})


def text_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
