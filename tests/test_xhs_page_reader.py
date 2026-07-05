import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "xhs"
sys.path.insert(0, str(PROJECT_ROOT))

from app.capture.browser.xhs_page_reader import read_xhs_page  # noqa: E402


class FakeResponse:
    ok = False
    status = 403

    def body(self) -> bytes:
        return b""


class FakeRequest:
    def get(self, url: str, timeout: int):
        return FakeResponse()


class FakePage:
    url = "https://www.xiaohongshu.com/explore/abc123"
    request = FakeRequest()

    def content(self) -> str:
        return (FIXTURES / "image_note.html").read_text(encoding="utf-8")

    def screenshot(self, path: str, full_page: bool) -> None:
        Path(path).write_bytes(b"fake screenshot")


class FakeHydrationPage(FakePage):
    def content(self) -> str:
        return """
        <script>
        window.__INITIAL_STATE__ = {"note":{"noteDetailMap":{"note123":{"comments":[],"note":{
          "noteId":"note123",
          "type":"normal",
          "title":"图片标题",
          "desc":"图片正文",
          "user":{"nickname":"作者"},
          "interactInfo":{"likedCount":"1","collectedCount":"1","commentCount":"0","shareCount":"0"},
          "imageList":[{"url":"https://media.example/image.jpg"}]
        }}}}};
        </script>
        """


class XhsPageReaderTests(unittest.TestCase):
    def test_records_media_download_failure_without_failing_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_xhs_page(
                FakePage(),
                source_url="https://www.xiaohongshu.com/explore/abc123",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "success")
            self.assertEqual(result.images[0]["download_status"], "failed")
            self.assertEqual(result.diagnostics["media_download_status"], "failed")
            self.assertTrue((Path(temp_dir) / "diagnostics.json").exists())

    def test_preserves_sensitive_media_skip_status_for_hydration_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_xhs_page(
                FakeHydrationPage(),
                source_url="https://www.xiaohongshu.com/explore/note123",
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "success")
            self.assertEqual(result.images[0]["remote_url"], "<redacted>")
            self.assertEqual(result.images[0]["download_status"], "skipped_sensitive_url")


if __name__ == "__main__":
    unittest.main()
