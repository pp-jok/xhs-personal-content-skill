import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.capture.browser.cdp_client import capture_xhs_link_with_browser  # noqa: E402


@unittest.skipUnless(os.environ.get("RUN_BROWSER_INTEGRATION") == "1", "set RUN_BROWSER_INTEGRATION=1 to run")
class BrowserCaptureIntegrationTests(unittest.TestCase):
    def test_cdp_capture_reads_local_html_fixture_without_online_platform(self) -> None:
        cdp_url = os.environ.get("XHS_CAPTURE_CDP_URL", "http://127.0.0.1:9222")
        fixture = PROJECT_ROOT / "tests" / "fixtures" / "xhs" / "image_note.html"
        with tempfile.TemporaryDirectory() as temp_dir:
            result = capture_xhs_link_with_browser(
                source_url=fixture.resolve().as_uri(),
                cdp_url=cdp_url,
                output_dir=Path(temp_dir),
            )

            self.assertEqual(result.capture_status, "success")
            self.assertEqual(result.title, "新手如何做清晰表达")
            self.assertTrue((Path(temp_dir) / "page.html").exists())


if __name__ == "__main__":
    unittest.main()
