import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.main import main  # noqa: E402


class RealSampleValidationTests(unittest.TestCase):
    def test_validate_real_sample_creates_report_and_review_form(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            self._copy_template("creator_profile.template.json", workspace / "creator_profile.json")
            self._copy_template("benchmark_account.template.json", workspace / "benchmark_account.json")
            self._copy_template("benchmark_post.template.json", workspace / "benchmark_post.json")
            self._copy_template("custom_tags.template.json", workspace / "custom_tags.json")
            self._copy_template("weekly_publish_plan.template.json", workspace / "weekly_publish_plan.json")
            self._copy_template("validation_feedback.template.json", workspace / "validation_feedback.json")

            output = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "validate-real-sample",
                    "--workspace",
                    str(workspace),
                ]
            )

            report_path = workspace / "reports" / "validation_report.md"
            review_path = workspace / "reports" / "human_review_form.md"
            report_text = report_path.read_text(encoding="utf-8")

            self.assertTrue(output["ok"])
            self.assertTrue(report_path.exists())
            self.assertTrue(review_path.exists())
            self.assertIn("creator_profiles: 1", report_text)
            self.assertIn("benchmark_accounts: 1", report_text)
            self.assertIn("rule_cards: 1", report_text)
            self.assertIn("创建发布任务: 成功", report_text)
            self.assertEqual(output["result"]["generated_counts"]["publish_tasks"], 1)

    def test_validate_real_sample_requires_minimum_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = self._run_cli(
                [
                    "--prompts-dir",
                    str(PROJECT_ROOT / "prompts"),
                    "validate-real-sample",
                    "--workspace",
                    temp_dir,
                ],
                expected_code=1,
            )

            self.assertFalse(output["ok"])
            self.assertIn("creator_profile.json", output["error"])

    def _copy_template(self, template_name: str, target: Path) -> None:
        shutil.copyfile(PROJECT_ROOT / "data" / "templates" / template_name, target)

    def _run_cli(self, args: list[str], expected_code: int = 0) -> dict:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(args)
        self.assertEqual(code, expected_code)
        return json.loads(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
