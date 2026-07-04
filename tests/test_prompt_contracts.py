import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import ContentDraft, PublishTask, ReviewRecord, RuleCard, TopicItem, ValidationError  # noqa: E402
from app.services.mock_prompt_service import MockPromptService  # noqa: E402
from app.services.prompt_contracts import load_contracts  # noqa: E402


class PromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = load_contracts(PROJECT_ROOT / "prompts")
        self.service = MockPromptService(self.contracts)

    def test_loads_all_phase_two_contracts(self) -> None:
        self.assertEqual(
            set(self.contracts),
            {
                "analyze_benchmark_post",
                "extract_rule_card",
                "generate_topic_pool",
                "generate_content_draft",
                "generate_publish_task",
                "review_own_post",
            },
        )

    def test_contracts_are_json_serializable_objects(self) -> None:
        for path in sorted((PROJECT_ROOT / "prompts").glob("*.json")):
            with self.subTest(path=path.name):
                with path.open("r", encoding="utf-8") as file:
                    data = json.load(file)

                self.assertEqual(data["input_schema"]["type"], "object")
                self.assertEqual(data["output_schema"]["type"], "object")
                self.assertTrue(data["input_schema"]["required"])
                self.assertTrue(data["output_schema"]["required"])

    def test_unknown_contract_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.run("missing_contract", {})

    def test_mock_analysis_can_feed_rule_card_extraction(self) -> None:
        analysis = self.service.run(
            "analyze_benchmark_post",
            {
                "creator_profile": {
                    "id": "creator-main",
                    "positioning": "学习与生活记录",
                    "target_audience": ["需要简单执行方案的人"],
                    "content_style": ["真诚"],
                    "forbidden_expressions": ["夸大承诺"],
                },
                "benchmark_post": {
                    "id": "benchmark-post-001",
                    "title": "新手学习计划",
                    "content_type": "图文",
                    "raw_content": "把计划拆到每天能完成。",
                    "tags": ["tag-usage-topic"],
                },
                "custom_tags": [{"id": "tag-usage-topic", "name": "适合选题", "type": "usage"}],
            },
        )

        extracted = self.service.run(
            "extract_rule_card",
            {
                "creator_profile": {
                    "id": "creator-main",
                    "positioning": "学习与生活记录",
                    "content_style": ["真诚"],
                    "forbidden_expressions": ["夸大承诺"],
                },
                "benchmark_post_id": "benchmark-post-001",
                "analysis_result": analysis,
            },
        )
        rule_data = extracted["rule_cards"][0]
        rule_data.update({"id": "rule-card-001"})

        rule_card = RuleCard.from_dict(rule_data)

        self.assertEqual(rule_card.source_ids, ["benchmark-post-001"])
        self.assertTrue(rule_card.risks)

    def test_mock_generation_outputs_phase_one_models(self) -> None:
        topics = self.service.run(
            "generate_topic_pool",
            {
                "creator_profile": {
                    "id": "creator-main",
                    "positioning": "学习与生活记录",
                    "target_audience": ["需要简单执行方案的人"],
                    "goals": ["增加收藏"],
                    "content_formats": ["图文"],
                },
                "custom_tags": [{"id": "tag-usage-topic", "name": "适合选题", "type": "usage"}],
                "rule_cards": [
                    {
                        "id": "rule-card-001",
                        "name": "场景化开头规则",
                        "rule_summary": "先给出具体场景。",
                        "tags": ["tag-usage-topic"],
                    }
                ],
                "reference_posts": [{"id": "benchmark-post-001", "title": "新手学习计划", "tags": ["tag-usage-topic"]}],
                "topic_count": 1,
            },
        )
        topic_data = topics["topics"][0]
        topic_data.update({"id": "topic-001"})
        topic = TopicItem.from_dict(topic_data)

        draft_result = self.service.run(
            "generate_content_draft",
            {
                "creator_profile": {
                    "id": "creator-main",
                    "positioning": "学习与生活记录",
                    "content_style": ["真诚"],
                    "forbidden_expressions": ["夸大承诺"],
                },
                "topic": topic.to_dict(),
                "rule_cards": [{"id": "rule-card-001", "rule_summary": "先给出具体场景。", "risks": ["避免夸大"]}],
                "custom_tags": [{"id": "tag-usage-topic", "name": "适合选题", "type": "usage"}],
            },
        )
        draft_data = draft_result["draft"]
        draft_data.update({"id": "draft-001"})
        draft = ContentDraft.from_dict(draft_data)

        publish_task_result = self.service.run(
            "generate_publish_task",
            {
                "creator_profile": {"id": "creator-main", "goals": ["增加收藏"], "publish_frequency": "每周 3 篇"},
                "content_draft": draft.to_dict(),
                "planned_publish_time": "2026-07-05T20:00:00+08:00",
            },
        )
        publish_task_data = publish_task_result["publish_task"]
        publish_task_data.update({"id": "publish-task-001", "result_metrics": {}, "review_summary": ""})
        publish_task = PublishTask.from_dict(publish_task_data)

        self.assertEqual(draft.topic_id, "topic-001")
        self.assertEqual(publish_task.account_id, "creator-main")

    def test_mock_review_outputs_review_record(self) -> None:
        result = self.service.run(
            "review_own_post",
            {
                "creator_profile": {"id": "creator-main", "goals": ["增加收藏"], "positioning": "学习与生活记录"},
                "own_post": {
                    "id": "own-post-001",
                    "title": "新手学习计划",
                    "metrics": {"likes": 10, "saves": 5},
                    "tags": ["tag-usage-topic"],
                    "source_topic_id": "topic-001",
                },
                "related_rule_cards": [
                    {"id": "rule-card-001", "name": "场景化开头规则", "rule_summary": "先给出具体场景。"}
                ],
            },
        )
        review_data = result["review_record"]
        review_data.update({"id": "review-001"})
        review = ReviewRecord.from_dict(review_data)

        self.assertEqual(review.own_post_id, "own-post-001")
        self.assertTrue(review.rule_updates)


if __name__ == "__main__":
    unittest.main()
