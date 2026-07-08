import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import BenchmarkPost, CreatorProfile, CustomTag  # noqa: E402
from app.repositories import JsonRepository  # noqa: E402
from app.workflows import BenchmarkToPublishWorkflow  # noqa: E402


class RecordingWorkflowPromptService:
    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped
        self.payloads: dict[str, list[dict[str, Any]]] = {}

    def run(self, contract_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.setdefault(contract_id, []).append(payload)
        return self.wrapped.run(contract_id, payload)


class BenchmarkToPublishWorkflowTests(unittest.TestCase):
    def test_workflow_creates_rule_topic_draft_and_publish_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            workflow = BenchmarkToPublishWorkflow(data_dir, PROJECT_ROOT / "prompts")

            result = workflow.run(
                creator_profile_id="creator-main",
                benchmark_post_id="benchmark-post-001",
                planned_publish_time="2026-07-05T20:00:00+08:00",
                topic_count=1,
            )

            self.assertEqual(result.benchmark_post.ai_analysis["structure"], "场景、问题、方法、行动提醒")
            self.assertEqual(result.rule_cards[0].id, "rule-card-from-benchmark-post-001-1")
            self.assertEqual(result.topics[0].id, "topic-from-benchmark-post-001-1")
            self.assertEqual(result.draft.topic_id, "topic-from-benchmark-post-001-1")
            self.assertEqual(result.publish_task.draft_id, "draft-from-benchmark-post-001-1")
            self.assertEqual(result.publish_task.account_id, "creator-main")

            self.assertTrue((data_dir / "rule-cards" / "rule-card-from-benchmark-post-001-1.json").exists())
            self.assertTrue((data_dir / "topic-pool" / "topic-from-benchmark-post-001-1.json").exists())
            self.assertTrue((data_dir / "content-drafts" / "draft-from-benchmark-post-001-1.json").exists())
            self.assertTrue((data_dir / "publish-tasks" / "publish-task-from-benchmark-post-001-1.json").exists())

    def test_workflow_is_repeatable_with_upserts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            workflow = BenchmarkToPublishWorkflow(data_dir, PROJECT_ROOT / "prompts")

            first = workflow.run("creator-main", "benchmark-post-001", "2026-07-05T20:00:00+08:00")
            second = workflow.run("creator-main", "benchmark-post-001", "2026-07-06T20:00:00+08:00")

            self.assertEqual(first.publish_task.id, second.publish_task.id)
            self.assertEqual(second.publish_task.planned_publish_time, "2026-07-06T20:00:00+08:00")

    def test_workflow_does_not_use_new_candidate_rules_in_same_generation_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._seed_data(data_dir)
            workflow = BenchmarkToPublishWorkflow(data_dir, PROJECT_ROOT / "prompts")
            recorder = RecordingWorkflowPromptService(workflow.prompt_service)
            workflow.prompt_service = recorder

            result = workflow.run("creator-main", "benchmark-post-001", "2026-07-05T20:00:00+08:00")

            topic_payload = recorder.payloads["generate_topic_pool"][0]
            draft_payload = recorder.payloads["generate_content_draft"][0]
            self.assertEqual(result.rule_cards[0].status, "candidate")
            self.assertEqual(topic_payload["rule_cards"], [])
            self.assertEqual(draft_payload["rule_cards"], [])
            self.assertIn("候选规则", "\n".join(result.warnings))

    def _seed_data(self, data_dir: Path) -> None:
        JsonRepository(data_dir, CreatorProfile).create(
            CreatorProfile(
                id="creator-main",
                name="主账号",
                platform="小红书",
                positioning="学习与生活记录",
                target_audience=["需要简单执行方案的人"],
                content_style=["真诚", "具体"],
                forbidden_expressions=["夸大承诺"],
                goals=["增加收藏"],
                content_formats=["图文"],
                publish_frequency="每周 3 篇",
                notes="测试账号档案。",
            )
        )
        JsonRepository(data_dir, BenchmarkPost).create(
            BenchmarkPost(
                id="benchmark-post-001",
                account_id="benchmark-account-001",
                title="新手学习计划",
                url="",
                content_type="图文",
                cover_text="新手计划",
                raw_content="把计划拆到每天都能完成的小步骤。",
                metrics={"likes": 10, "saves": 5},
                tags=["tag-usage-topic"],
                ai_analysis={},
                borrowable_points=[],
                non_borrowable_points=[],
                rule_card_candidates=[],
            )
        )
        JsonRepository(data_dir, CustomTag).create(
            CustomTag(
                id="tag-usage-topic",
                name="适合选题",
                type="usage",
                description="用于选题生成。",
                scope=["benchmark_post", "rule_card", "topic_item", "content_draft", "publish_task"],
                weight=4,
            )
        )


if __name__ == "__main__":
    unittest.main()
