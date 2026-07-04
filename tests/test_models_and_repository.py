import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.models.core import (  # noqa: E402
    BenchmarkAccount,
    BenchmarkPost,
    ContentDraft,
    CreatorProfile,
    CustomTag,
    MODEL_TYPES,
    OwnPost,
    PublishTask,
    ReviewRecord,
    RuleCard,
    TopicItem,
    ValidationError,
)
from app.repositories import JsonRepository, NotFoundError  # noqa: E402


EXAMPLE_TO_MODEL = {
    "creator-profile.json": CreatorProfile,
    "benchmark-account.json": BenchmarkAccount,
    "benchmark-post.json": BenchmarkPost,
    "custom-tag.json": CustomTag,
    "rule-card.json": RuleCard,
    "topic-item.json": TopicItem,
    "content-draft.json": ContentDraft,
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

    def test_collection_names_are_unique(self) -> None:
        self.assertEqual(len(MODEL_TYPES), 10)
        self.assertEqual(MODEL_TYPES["creator-profiles"], CreatorProfile)
        self.assertEqual(MODEL_TYPES["review-records"], ReviewRecord)


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
