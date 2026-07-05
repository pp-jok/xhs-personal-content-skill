import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import (  # noqa: E402
    BenchmarkAccount,
    BenchmarkAnalysis,
    BenchmarkPost,
    ContentQualityReview,
    ContentDraft,
    CaptureRecord,
    ContentInboxItem,
    CreatorProfile,
    CustomTag,
    MODEL_TYPES,
    OwnPost,
    PublishTask,
    ReviewRecord,
    RuleCard,
    RuleEvidence,
    TopicItem,
    ValidationError,
)
from app.repositories import JsonRepository, NotFoundError  # noqa: E402


EXAMPLE_TO_MODEL = {
    "creator-profile.json": CreatorProfile,
    "benchmark-account.json": BenchmarkAccount,
    "benchmark-analysis.json": BenchmarkAnalysis,
    "benchmark-post.json": BenchmarkPost,
    "content-inbox-item.json": ContentInboxItem,
    "capture-record.json": CaptureRecord,
    "custom-tag.json": CustomTag,
    "rule-card.json": RuleCard,
    "rule-evidence.json": RuleEvidence,
    "topic-item.json": TopicItem,
    "content-draft.json": ContentDraft,
    "content-quality-review.json": ContentQualityReview,
    "publish-task.json": PublishTask,
    "own-post.json": OwnPost,
    "review-record.json": ReviewRecord,
}


class ModelTests(unittest.TestCase):
    def test_all_example_files_load_into_models(self) -> None:
        examples_dir = PROJECT_ROOT / "data" / "examples"

        for file_name, model_type in EXAMPLE_TO_MODEL.items():
            with self.subTest(file_name=file_name):
                with (examples_dir / file_name).open("r", encoding="utf-8") as file:
                    data = json.load(file)

                model = model_type.from_dict(data)

                self.assertEqual(model.id, data["id"])
                self.assertEqual(model.to_dict()["id"], data["id"])

    def test_custom_tag_rejects_invalid_scope(self) -> None:
        with self.assertRaises(ValidationError):
            CustomTag(
                id="tag-invalid",
                name="错误范围",
                type="usage",
                description="用于验证无效范围会被拒绝。",
                scope=["creator_profile"],
                weight=3,
            )

    def test_benchmark_post_requires_structured_analysis(self) -> None:
        with self.assertRaises(ValidationError):
            BenchmarkPost(
                id="post-invalid",
                account_id="account-001",
                title="标题",
                content_type="图文",
                raw_content="正文",
                ai_analysis="not-an-object",
            )

    def test_models_accept_partial_input_metadata(self) -> None:
        profile = CreatorProfile(
            id="creator-partial",
            name="测试账号",
            platform="小红书",
            positioning="职场表达",
            target_audience=["职场新人"],
            content_style=["真实"],
            forbidden_expressions=[],
            goals=["提升收藏"],
            content_formats=["图文"],
            publish_frequency="待补充",
            notes="用户只提供了基础定位。",
            missing_fields=["forbidden_expressions"],
            confidence=0.6,
            source_type="user_input",
            source_note="来自一次简短对话",
            user_reason="先保存，后续补充",
            created_from="phase7-partial-intake",
        )

        data = profile.to_dict()

        self.assertEqual(data["missing_fields"], ["forbidden_expressions"])
        self.assertEqual(data["confidence"], 0.6)
        self.assertEqual(data["source_type"], "user_input")

    def test_collection_names_are_unique(self) -> None:
        self.assertEqual(len(MODEL_TYPES), 15)
        self.assertEqual(MODEL_TYPES["creator-profiles"], CreatorProfile)
        self.assertEqual(MODEL_TYPES["benchmark-analyses"], BenchmarkAnalysis)
        self.assertEqual(MODEL_TYPES["content-inbox"], ContentInboxItem)
        self.assertEqual(MODEL_TYPES["content-quality-reviews"], ContentQualityReview)
        self.assertEqual(MODEL_TYPES["capture-records"], CaptureRecord)
        self.assertEqual(MODEL_TYPES["rule-evidence"], RuleEvidence)
        self.assertEqual(MODEL_TYPES["review-records"], ReviewRecord)

    def test_content_quality_review_rejects_score_out_of_range(self) -> None:
        with self.assertRaises(ValidationError):
            ContentQualityReview(
                id="quality-invalid",
                draft_id="draft-001",
                review_type="pre_publish",
                account_fit_score=6,
                publishability_score=3,
                title_score=3,
                cover_score=3,
                structure_score=3,
                tone_score=3,
            )

    def test_rule_card_accepts_lifecycle_fields(self) -> None:
        rule = RuleCard(
            id="rule-lifecycle",
            name="标题具体对象规则",
            type="title",
            source_ids=["benchmark-post-001"],
            applicable_scenarios=["图文标题"],
            rule_summary="标题优先包含具体对象。",
            examples=["给职场新人看的汇报模板"],
            risks=["对象过宽会变泛。"],
            adaptation_notes="适合当前账号的新手表达内容。",
            status="approved",
            strength="medium",
            validation_count=2,
            success_count=1,
            failure_count=1,
            applicable_content_types=["image"],
            applicable_audiences=["职场新人"],
            conflicts_with=["rule-other"],
            supersedes=[],
        )

        self.assertEqual(rule.status, "approved")
        self.assertEqual(rule.strength, "medium")
        self.assertEqual(rule.validation_count, 2)

    def test_rule_evidence_requires_observable_fact(self) -> None:
        with self.assertRaises(ValidationError):
            RuleEvidence(
                id="evidence-invalid",
                rule_id="rule-001",
                source_type="benchmark_post",
                source_id="benchmark-post-001",
                source_fragment="标题",
                evidence_type="content_structure",
                observable_fact="",
                inference="标题具体。",
            )

    def test_benchmark_analysis_rejects_invalid_template(self) -> None:
        with self.assertRaises(ValidationError):
            BenchmarkAnalysis(
                id="analysis-invalid",
                capture_id="capture-001",
                analysis_template="unknown",
                observable_facts={"title": "标题"},
                topic_analysis={},
                title_analysis={},
                cover_analysis={},
                structure_analysis={},
                visual_analysis={},
                audio_analysis={},
                comment_analysis={},
                engagement_analysis={},
                account_fit={},
                transferable_elements=[],
                non_transferable_elements=[],
                candidate_rule_ids=[],
                derived_topic_ids=[],
                uncertainties=[],
            )

    def test_content_inbox_item_rejects_invalid_status(self) -> None:
        with self.assertRaises(ValidationError):
            ContentInboxItem(
                id="inbox-invalid",
                source_url="https://www.xiaohongshu.com/explore/test",
                user_intent="学习标题",
                status="unknown",
            )

    def test_capture_record_accepts_partial_success_with_missing_fields(self) -> None:
        record = CaptureRecord(
            id="capture-001",
            inbox_item_id="inbox-001",
            source_url="https://www.xiaohongshu.com/explore/test",
            canonical_url="https://www.xiaohongshu.com/explore/test",
            capture_method="manual",
            capture_status="partial",
            published_at="2026-07-05T12:00:00+08:00",
            title="可见标题",
            body="可见正文",
            content_type="unknown",
            author={"name": "可见作者"},
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            images=[],
            video={},
            comments=[],
            available_fields=["title", "body"],
            missing_fields=["metrics.likes", "images"],
            warnings=["用户未提供完整截图。"],
            diagnostics={"page_reachable": True},
        )

        self.assertEqual(record.capture_status, "partial")
        self.assertEqual(record.metrics["likes"], None)
        self.assertIn("metrics.likes", record.missing_fields)
        self.assertEqual(record.canonical_url, "https://www.xiaohongshu.com/explore/test")
        self.assertTrue(record.diagnostics["page_reachable"])


class JsonRepositoryTests(unittest.TestCase):
    def test_crud_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), CreatorProfile)
            profile = CreatorProfile(
                id="creator-main",
                name="主账号",
                platform="小红书",
                positioning="学习与生活记录",
                target_audience=["需要简单执行方案的人"],
                content_style=["真诚", "具体"],
                forbidden_expressions=["夸大承诺"],
                goals=["提升关注"],
                content_formats=["图文"],
                publish_frequency="每周 3 篇",
                notes="测试账号档案。",
            )

            repo.create(profile)
            loaded = repo.read("creator-main")
            updated = repo.update("creator-main", {"publish_frequency": "每周 4 篇"})
            all_items = repo.list_all()
            repo.delete("creator-main")

            self.assertEqual(loaded.name, "主账号")
            self.assertEqual(updated.publish_frequency, "每周 4 篇")
            self.assertEqual(len(all_items), 1)
            with self.assertRaises(NotFoundError):
                repo.read("creator-main")

    def test_create_rejects_duplicate_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), CustomTag)
            tag = CustomTag(
                id="tag-001",
                name="适合选题",
                type="usage",
                description="用于选题。",
                scope=["benchmark_post", "topic_item"],
                weight=4,
            )

            repo.create(tag)

            with self.assertRaises(FileExistsError):
                repo.create(tag)

    def test_record_id_cannot_escape_collection_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), TopicItem)

            with self.assertRaises(ValueError):
                repo.read("../topic-001")


if __name__ == "__main__":
    unittest.main()
