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


if __name__ == "__main__":
    unittest.main()
