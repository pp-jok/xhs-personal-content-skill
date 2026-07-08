from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.core import (
    BenchmarkPost,
    ContentDraft,
    CreatorProfile,
    CustomTag,
    PublishTask,
    RuleCard,
    TopicItem,
)
from app.repositories import JsonRepository
from app.services.mock_prompt_service import MockPromptService
from app.services.prompt_contracts import load_contracts


@dataclass(frozen=True)
class BenchmarkToPublishResult:
    benchmark_post: BenchmarkPost
    rule_cards: list[RuleCard]
    topics: list[TopicItem]
    draft: ContentDraft
    publish_task: PublishTask
    warnings: list[str]


class BenchmarkToPublishWorkflow:
    def __init__(self, data_dir: Path | str, prompts_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        contracts = load_contracts(prompts_dir)
        self.prompt_service = MockPromptService(contracts)
        self.creator_profiles = JsonRepository(self.data_dir, CreatorProfile)
        self.benchmark_posts = JsonRepository(self.data_dir, BenchmarkPost)
        self.custom_tags = JsonRepository(self.data_dir, CustomTag)
        self.rule_cards = JsonRepository(self.data_dir, RuleCard)
        self.topics = JsonRepository(self.data_dir, TopicItem)
        self.drafts = JsonRepository(self.data_dir, ContentDraft)
        self.publish_tasks = JsonRepository(self.data_dir, PublishTask)

    def run(
        self,
        creator_profile_id: str,
        benchmark_post_id: str,
        planned_publish_time: str,
        topic_count: int = 1,
    ) -> BenchmarkToPublishResult:
        creator = self.creator_profiles.read(creator_profile_id)
        post = self.benchmark_posts.read(benchmark_post_id)
        tags = self.custom_tags.list_all()
        warnings: list[str] = []

        analysis = self.prompt_service.run(
            "analyze_benchmark_post",
            {
                "creator_profile": creator.to_dict(),
                "benchmark_post": post.to_dict(),
                "custom_tags": [tag.to_dict() for tag in tags],
            },
        )
        warnings.extend(analysis.get("warnings", []))

        post = self.benchmark_posts.update(
            post.id,
            {
                "ai_analysis": analysis["ai_analysis"],
                "borrowable_points": analysis["borrowable_points"],
                "non_borrowable_points": analysis["non_borrowable_points"],
                "rule_card_candidates": analysis["rule_card_candidates"],
            },
        )

        extracted = self.prompt_service.run(
            "extract_rule_card",
            {
                "creator_profile": creator.to_dict(),
                "benchmark_post_id": post.id,
                "analysis_result": analysis,
            },
        )
        warnings.extend(extracted.get("warnings", []))
        saved_rule_cards = self._save_rule_cards(post.id, extracted["rule_cards"])

        generated_topics = self.prompt_service.run(
            "generate_topic_pool",
            {
                "creator_profile": creator.to_dict(),
                "custom_tags": [tag.to_dict() for tag in tags],
                "rule_cards": [rule.to_dict() for rule in saved_rule_cards],
                "reference_posts": [post.to_dict()],
                "topic_count": topic_count,
            },
        )
        warnings.extend(generated_topics.get("warnings", []))
        saved_topics = self._save_topics(post.id, generated_topics["topics"])

        draft_payload = self.prompt_service.run(
            "generate_content_draft",
            {
                "creator_profile": creator.to_dict(),
                "topic": saved_topics[0].to_dict(),
                "rule_cards": [rule.to_dict() for rule in saved_rule_cards],
                "custom_tags": [tag.to_dict() for tag in tags],
            },
        )
        warnings.extend(draft_payload.get("warnings", []))
        draft = self._save_draft(post.id, draft_payload["draft"])

        publish_payload = self.prompt_service.run(
            "generate_publish_task",
            {
                "creator_profile": creator.to_dict(),
                "content_draft": draft.to_dict(),
                "planned_publish_time": planned_publish_time,
            },
        )
        warnings.extend(publish_payload.get("warnings", []))
        publish_task = self._save_publish_task(post.id, publish_payload["publish_task"])

        return BenchmarkToPublishResult(
            benchmark_post=post,
            rule_cards=saved_rule_cards,
            topics=saved_topics,
            draft=draft,
            publish_task=publish_task,
            warnings=warnings,
        )

    def _save_rule_cards(self, post_id: str, rule_cards: list[dict[str, Any]]) -> list[RuleCard]:
        saved = []
        for index, rule_data in enumerate(rule_cards, start=1):
            data = dict(rule_data)
            data["id"] = f"rule-card-from-{post_id}-{index}"
            data["created_by"] = "codex"
            data["status"] = "candidate"
            saved.append(self.rule_cards.upsert(RuleCard.from_dict(data), changed_by="codex", change_note="run-workflow rule generation"))
        return saved

    def _save_topics(self, post_id: str, topics: list[dict[str, Any]]) -> list[TopicItem]:
        saved = []
        for index, topic_data in enumerate(topics, start=1):
            data = dict(topic_data)
            data["id"] = f"topic-from-{post_id}-{index}"
            data["status"] = "idea"
            saved.append(self.topics.upsert(TopicItem.from_dict(data)))
        return saved

    def _save_draft(self, post_id: str, draft_data: dict[str, Any]) -> ContentDraft:
        data = dict(draft_data)
        data["id"] = f"draft-from-{post_id}-1"
        data["status"] = "draft"
        return self.drafts.upsert(ContentDraft.from_dict(data))

    def _save_publish_task(self, post_id: str, publish_task_data: dict[str, Any]) -> PublishTask:
        data = dict(publish_task_data)
        data["id"] = f"publish-task-from-{post_id}-1"
        data["result_metrics"] = {}
        data["review_summary"] = ""
        return self.publish_tasks.upsert(PublishTask.from_dict(data))
