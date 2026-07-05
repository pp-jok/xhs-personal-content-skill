import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "xhs"
sys.path.insert(0, str(PROJECT_ROOT))

from app.capture.browser.xhs_dom_extractors import extract_visible_content  # noqa: E402


class XhsDomExtractorTests(unittest.TestCase):
    def test_extracts_visible_image_note_fields_and_saves_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html = (FIXTURES / "image_note.html").read_text(encoding="utf-8")
            result = extract_visible_content(
                html=html,
                source_url="https://www.xiaohongshu.com/explore/abc123",
                canonical_url="https://www.xiaohongshu.com/explore/abc123",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "success")
            self.assertEqual(result.title, "新手如何做清晰表达")
            self.assertEqual(result.body, "先讲对象，再讲问题，最后给一个具体做法。")
            self.assertEqual(result.content_type, "image")
            self.assertEqual(result.author["name"], "可见账号")
            self.assertEqual(result.published_at, "2026-07-05T12:00:00+08:00")
            self.assertEqual(result.metrics["likes"], 12)
            self.assertEqual(len(result.images), 2)
            self.assertEqual(len(result.comments), 2)
            self.assertTrue((Path(temp_dir) / "page.html").exists())
            self.assertIn("title", result.diagnostics["selectors_succeeded"])

    def test_extracts_video_media_information(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html = (FIXTURES / "video_note.html").read_text(encoding="utf-8")
            result = extract_visible_content(
                html=html,
                source_url="https://www.xiaohongshu.com/explore/video123",
                canonical_url="https://www.xiaohongshu.com/explore/video123",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "success")
            self.assertEqual(result.content_type, "video")
            self.assertEqual(result.video["src"], "https://example.test/video.mp4")
            self.assertEqual(result.video["poster"], "https://example.test/poster.jpg")

    def test_detects_login_required_without_fabricating_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html = (FIXTURES / "login_required.html").read_text(encoding="utf-8")
            result = extract_visible_content(
                html=html,
                source_url="https://www.xiaohongshu.com/explore/login",
                canonical_url="https://www.xiaohongshu.com/explore/login",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "failed")
            self.assertTrue(result.diagnostics["login_required"])
            self.assertEqual(result.title, "")
            self.assertIn("title", result.missing_fields)

    def test_detects_captcha_without_bypass_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html = (FIXTURES / "captcha.html").read_text(encoding="utf-8")
            result = extract_visible_content(
                html=html,
                source_url="https://www.xiaohongshu.com/explore/captcha",
                canonical_url="https://www.xiaohongshu.com/explore/captcha",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "failed")
            self.assertTrue(result.diagnostics["captcha_detected"])
            self.assertIn("captcha_detected", result.warnings[0])

    def test_records_selector_failures_for_changed_dom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            html = (FIXTURES / "structure_changed.html").read_text(encoding="utf-8")
            result = extract_visible_content(
                html=html,
                source_url="https://www.xiaohongshu.com/explore/changed",
                canonical_url="https://www.xiaohongshu.com/explore/changed",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "failed")
            self.assertIn("title", result.diagnostics["selectors_failed"])
            self.assertIn("body", result.diagnostics["selectors_failed"])
            self.assertTrue((Path(temp_dir) / "page.html").exists())


if __name__ == "__main__":
    unittest.main()
