from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.capture.browser.url_normalizer import normalize_xhs_url
from app.capture.browser.xhs_dom_extractors import BrowserCaptureResult, extract_visible_content


def read_xhs_page(page: Any, source_url: str, output_dir: Path, comment_limit: int = 30) -> BrowserCaptureResult:
    final_url = str(getattr(page, "url", "") or source_url)
    normalized = normalize_xhs_url(source_url, final_url=final_url)
    html = page.content()
    result = extract_visible_content(
        html=html,
        source_url=source_url,
        canonical_url=normalized.canonical_url,
        output_dir=output_dir,
        comment_limit=comment_limit,
    )
    save_visible_images(page, result, output_dir)
    try:
        page.screenshot(path=str(output_dir / "page.png"), full_page=True)
    except Exception as exc:  # pragma: no cover - depends on browser/media state
        result.warnings.append(f"page_screenshot_failed: {exc}")
    rewrite_diagnostics(output_dir, result)
    return result


def save_visible_images(page: Any, result: BrowserCaptureResult, output_dir: Path) -> None:
    if not result.images:
        result.diagnostics["media_download_status"] = "not_attempted"
        return

    image_dir = output_dir / "media" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    successes = 0
    failures = 0
    for index, image in enumerate(result.images, start=1):
        remote_url = str(image.get("remote_url") or "")
        if remote_url == "<redacted>" or image.get("download_status") == "skipped_sensitive_url":
            image["download_status"] = "skipped_sensitive_url"
            continue
        if not remote_url.startswith(("http://", "https://")):
            image["download_status"] = "skipped"
            continue
        try:
            response = page.request.get(remote_url, timeout=10000)
            if not getattr(response, "ok", False):
                failures += 1
                image["download_status"] = "failed"
                image["download_error"] = f"status={getattr(response, 'status', 'unknown')}"
                continue
            target = image_dir / f"image-{index}{guess_extension(remote_url)}"
            target.write_bytes(response.body())
            successes += 1
            image["download_status"] = "success"
            image["local_path"] = str(target)
        except Exception as exc:  # pragma: no cover - browser/network dependent
            failures += 1
            image["download_status"] = "failed"
            image["download_error"] = str(exc)

    if successes and failures:
        result.diagnostics["media_download_status"] = "partial"
    elif successes:
        result.diagnostics["media_download_status"] = "success"
    elif failures:
        result.diagnostics["media_download_status"] = "failed"
    else:
        result.diagnostics["media_download_status"] = "not_attempted"


def rewrite_diagnostics(output_dir: Path, result: BrowserCaptureResult) -> None:
    import json

    (output_dir / "diagnostics.json").write_text(
        json.dumps(result.diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def guess_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    return ".jpg"
