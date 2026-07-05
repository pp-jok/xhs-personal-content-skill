from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class CaptureDiagnostics:
    page_reachable: bool = True
    login_required: bool = False
    captcha_detected: bool = False
    dom_version: str = "xhs-web-unknown"
    selectors_succeeded: list[str] = field(default_factory=list)
    selectors_failed: list[str] = field(default_factory=list)
    media_download_status: str = "not_attempted"
    comment_limit: int = 30
    error_code: str | None = None
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
