from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedCaptureInput:
    title: str = ""
    body: str = ""
    content_type: str = "unknown"
    author: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)
    video: dict[str, Any] = field(default_factory=dict)
    comments: list[dict[str, Any]] = field(default_factory=list)
    raw_snapshot_path: str = ""
