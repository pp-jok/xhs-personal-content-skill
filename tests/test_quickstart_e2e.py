import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.cli.main import main  # noqa: E402


class QuickstartEndToEndTests(unittest.TestCase):
    def test_quickstart_minimum_flow_from_empty_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "import-json",
                    "creator-profiles",
                    str(PROJECT_ROOT / "data" / "examples" / "creator-profile.json"),
                ]
            )
            self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "import-json",
                    "benchmark-posts",
                    str(PROJECT_ROOT / "data" / "examples" / "benchmark-post.json"),
                ]
            )
            self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "import-json",
                    "custom-tags",
                    str(PROJECT_ROOT / "data" / "examples" / "custom-tag.json"),
                ]
            )

            workflow_output = self._run_cli(
                [
                    "--data-dir",
                    temp_dir,
                    "run-workflow",
                    "--creator-id",
                    "creator-main",
                    "--benchmark-post-id",
                    "benchmark-post-001",
                    "--planned-publish-time",
                    "2026-07-05T20:00:00+08:00",
                    "--topic-count",
                    "1",
                ]
            )
            publish_tasks = self._run_cli(["--data-dir", temp_dir, "list", "publish-tasks"])

            self.assertEqual(workflow_output["result"]["rule_card_ids"], ["rule-card-from-benchmark-post-001-1"])
            self.assertEqual(workflow_output["result"]["topic_ids"], ["topic-from-benchmark-post-001-1"])
            self.assertEqual(workflow_output["result"]["draft_id"], "draft-from-benchmark-post-001-1")
            self.assertEqual(workflow_output["result"]["publish_task_id"], "publish-task-from-benchmark-post-001-1")
            self.assertEqual(len(publish_tasks["result"]), 1)
            self.assertEqual(publish_tasks["result"][0]["planned_publish_time"], "2026-07-05T20:00:00+08:00")

    def _run_cli(self, args: list[str]) -> dict:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(args)
        self.assertEqual(code, 0, buffer.getvalue())
        return json.loads(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
