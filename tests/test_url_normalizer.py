import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.capture.browser.url_normalizer import normalize_xhs_url  # noqa: E402


class UrlNormalizerTests(unittest.TestCase):
    def test_normalizes_full_note_url_and_removes_tracking_query(self) -> None:
        result = normalize_xhs_url(
            "https://www.xiaohongshu.com/explore/abc123?channel_type=explore_feed&debug_param=redacted"
        )

        self.assertEqual(result.url_type, "note")
        self.assertEqual(result.note_id, "abc123")
        self.assertEqual(result.normalized_url, "https://www.xiaohongshu.com/explore/abc123")
        self.assertEqual(result.canonical_url, "https://www.xiaohongshu.com/explore/abc123")

    def test_marks_short_link_without_network_expansion(self) -> None:
        result = normalize_xhs_url("https://xhslink.com/a/AbCd?foo=bar")

        self.assertEqual(result.url_type, "short")
        self.assertEqual(result.normalized_url, "https://xhslink.com/a/AbCd")
        self.assertEqual(result.canonical_url, "https://xhslink.com/a/AbCd")
        self.assertIsNone(result.note_id)


if __name__ == "__main__":
    unittest.main()
