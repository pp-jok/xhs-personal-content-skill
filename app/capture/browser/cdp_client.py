from __future__ import annotations

import json
from pathlib import Path

from app.capture.browser.capture_diagnostics import CaptureDiagnostics
from app.capture.browser.url_normalizer import normalize_xhs_url
from app.capture.browser.xhs_dom_extractors import BrowserCaptureResult, METRIC_FIELDS
from app.capture.browser.xhs_page_reader import read_xhs_page


DEFAULT_CDP_URL = "http://127.0.0.1:9222"


def capture_xhs_link_with_browser(
    source_url: str,
    cdp_url: str | None,
    output_dir: Path,
    comment_limit: int = 30,
) -> BrowserCaptureResult:
    normalized = normalize_xhs_url(source_url)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return failed_browser_result(
            source_url=source_url,
            canonical_url=normalized.canonical_url,
            output_dir=output_dir,
            error_code="playwright_unavailable",
            error_message=str(exc),
        )

    target_cdp_url = cdp_url or DEFAULT_CDP_URL
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(target_cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = find_matching_page(context.pages, normalized.canonical_url)
            if page is None:
                page = context.new_page()
                page.goto(source_url, wait_until="domcontentloaded", timeout=30000)
            else:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            return read_xhs_page(page, source_url=source_url, output_dir=output_dir, comment_limit=comment_limit)
    except Exception as exc:
        error_code = "browser_capture_failed"
        if "connect" in str(exc).lower():
            error_code = "cdp_connection_failed"
        if "timeout" in str(exc).lower():
            error_code = "page_unreachable"
        if "PlaywrightError" in globals() and isinstance(exc, PlaywrightError):
            error_code = error_code
        return failed_browser_result(
            source_url=source_url,
            canonical_url=normalized.canonical_url,
            output_dir=output_dir,
            error_code=error_code,
            error_message=str(exc),
        )


def find_matching_page(pages: list, canonical_url: str):
    for page in pages:
        current_url = str(getattr(page, "url", "") or "")
        if not current_url:
            continue
        if normalize_xhs_url(current_url).canonical_url == canonical_url:
            return page
    return None


def failed_browser_result(
    source_url: str,
    canonical_url: str,
    output_dir: Path,
    error_code: str,
    error_message: str,
) -> BrowserCaptureResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = CaptureDiagnostics(
        page_reachable=False,
        selectors_failed=["title", "body", "author", "metrics", "images", "video", "comments"],
        error_code=error_code,
        error_message=error_message,
    ).to_dict()
    (output_dir / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    return BrowserCaptureResult(
        source_url=source_url,
        canonical_url=canonical_url,
        capture_status="failed",
        metrics={field: None for field in METRIC_FIELDS},
        missing_fields=["title", "body", "author", "metrics", "images", "video", "comments"],
        warnings=[f"{error_code}: {error_message}"],
        diagnostics=diagnostics,
    )
