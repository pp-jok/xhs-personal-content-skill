from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse, urlunparse


SHORT_LINK_HOSTS = {"xhslink.com", "www.xhslink.com", "xhsurl.com", "www.xhsurl.com"}
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com"}


@dataclass(frozen=True)
class NormalizedUrl:
    input_url: str
    normalized_url: str
    canonical_url: str
    url_type: str
    note_id: str | None = None
    redirect_chain: list[str] = field(default_factory=list)


def normalize_xhs_url(raw_url: str, final_url: str | None = None) -> NormalizedUrl:
    input_url = raw_url.strip()
    target = (final_url or input_url).strip()
    parsed = urlparse(target)
    scheme = parsed.scheme or "https"
    host = parsed.netloc.lower()
    path = normalize_path(parsed.path)

    if host in SHORT_LINK_HOSTS:
        normalized = urlunparse((scheme, host, path, "", "", ""))
        return NormalizedUrl(
            input_url=input_url,
            normalized_url=normalized,
            canonical_url=normalized,
            url_type="short",
            redirect_chain=[input_url, target] if final_url and final_url != input_url else [],
        )

    note_id = extract_note_id(path, parsed.query)
    if host in XHS_HOSTS and note_id:
        canonical = f"https://www.xiaohongshu.com/explore/{note_id}"
        return NormalizedUrl(
            input_url=input_url,
            normalized_url=canonical,
            canonical_url=canonical,
            url_type="note",
            note_id=note_id,
            redirect_chain=[input_url, target] if final_url and final_url != input_url else [],
        )

    if host in XHS_HOSTS and "/user/profile/" in path:
        normalized = urlunparse(("https", "www.xiaohongshu.com", path, "", "", ""))
        return NormalizedUrl(input_url=input_url, normalized_url=normalized, canonical_url=normalized, url_type="profile")

    normalized = urlunparse((scheme, host, path, "", "", ""))
    return NormalizedUrl(input_url=input_url, normalized_url=normalized, canonical_url=normalized, url_type="unknown")


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = "/" + path.strip("/")
    return normalized if normalized != "/" else "/"


def extract_note_id(path: str, query: str) -> str | None:
    parts = [part for part in path.split("/") if part]
    if "explore" in parts:
        index = parts.index("explore")
        if index + 1 < len(parts):
            return parts[index + 1]
    if "discovery" in parts and "item" in parts:
        item_index = parts.index("item")
        if item_index + 1 < len(parts):
            return parts[item_index + 1]
    params = parse_qs(query)
    for key in ("note_id", "noteId", "id"):
        values = params.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return None
