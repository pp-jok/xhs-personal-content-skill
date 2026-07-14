import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.assets.lifecycle import (  # noqa: E402
    ContentAssetLifecycleError,
    activate_content_asset,
    deprecate_content_asset,
)
from app.models.core import ContentAsset, ContentAssetEvidence, ContentMechanism, CreatorProfile, DecisionRequest, ProvenanceRecord  # noqa: E402
from app.repositories import JsonRepository  # noqa: E402


def make_asset(**overrides: object) -> ContentAsset:
    data: dict[str, object] = {
        "id": "asset-opening",
        "status": "candidate",
        "asset_type": "opening_template",
        "name": "任务结果优先开场",
        "description": "用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
        "template": "先说明结果：{{result}}。再说明过程：{{process}}。",
        "variables": ["result", "process"],
        "applicable_scope": ["AI 内容运营"],
        "exclusions": ["纯工具安装教程"],
        "usage_notes": ["先填具体结果，再填过程证据。"],
        "limitations": ["不能夸大时间和收益"],
        "examples": ["先说明 10 分钟完成选题库，再说明工具流程。"],
        "creator_profile_id": "creator-main",
        "source_mechanism_ids": ["mechanism-result-framing"],
        "selected_observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"],
        "account_fit_reason": "提案认为这适合当前账号的 AI 内容运营判断定位。",
        "confidence_level": "medium",
        "confidence": 0.6,
        "created_from": "propose-asset-from-mechanism",
        "created_by": "codex",
    }
    data.update(overrides)
    return ContentAsset.from_dict(data)


def make_mechanism() -> ContentMechanism:
    return ContentMechanism.from_dict(
        {
            "id": "mechanism-result-framing",
            "name": "结果前置表达机制",
            "description": "先呈现用户可获得的内容运营结果，再解释工具和过程。",
            "status": "candidate",
            "confidence_level": "medium",
            "confidence": 0.6,
            "source_refs": [{"source_type": "external_analysis", "source_id": "external-001"}],
            "evidence_summary": {"observed_facts": ["标题先展示结果承诺，再说明使用的工具和流程"]},
            "problem": "复杂工具内容容易让用户只看到工具名。",
            "solution": "先讲结果，再解释工具如何实现。",
            "pattern": ["结果承诺", "过程说明"],
            "applicable_scope": ["AI 内容运营"],
            "limitations": ["不能夸大时间承诺"],
        }
    )


class FailingUpdateRepository:
    def __init__(self, asset: ContentAsset) -> None:
        self.asset = asset
        self.update_called = False

    def read(self, asset_id: str) -> ContentAsset:
        if asset_id != self.asset.id:
            raise FileNotFoundError("missing")
        return self.asset

    def update(self, record_id: str, changes: dict[str, object], changed_by: str = "system", change_note: str = "update") -> ContentAsset:
        self.update_called = True
        raise OSError("disk failed")

    def update_if_version(
        self,
        record_id: str,
        *,
        expected_version: int,
        changes=None,
        update_fn=None,
        changed_by: str = "system",
        change_note: str = "update",
    ) -> ContentAsset:
        self.update_called = True
        raise OSError("disk failed")


class RacingRepository:
    def __init__(self, first: ContentAsset, latest: ContentAsset) -> None:
        self.first = first
        self.latest = latest
        self.update_called = False

    def read(self, asset_id: str) -> ContentAsset:
        return self.first

    def update(self, record_id: str, changes: dict[str, object], changed_by: str = "system", change_note: str = "update") -> ContentAsset:
        self.update_called = True
        data = self.latest.to_dict()
        data.update(changes)
        data["version"] = self.latest.version + 1
        self.latest = ContentAsset.from_dict(data)
        return self.latest

    def update_if_version(
        self,
        record_id: str,
        *,
        expected_version: int,
        changes=None,
        update_fn=None,
        changed_by: str = "system",
        change_note: str = "update",
    ) -> ContentAsset:
        if self.latest.version != expected_version:
            raise ContentAssetLifecycleError("版本冲突：内容资产已变化，请重新查看后再操作。")
        self.update_called = True
        data = self.latest.to_dict()
        if changes:
            data.update(changes)
        if update_fn:
            data = update_fn(data)
        data["version"] = self.latest.version + 1
        self.latest = ContentAsset.from_dict(data)
        return self.latest


class ContentAssetLifecycleTests(unittest.TestCase):
    def test_activate_candidate_asset_updates_only_lifecycle_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            repo = JsonRepository(workspace, ContentAsset)
            asset = repo.create(make_asset())
            before = asset.to_dict()

            result = activate_content_asset(repo, asset_id=asset.id, expected_version=asset.version, actor="user")

            saved = repo.read(asset.id)
            self.assertEqual(result.previous_status, "candidate")
            self.assertEqual(result.new_status, "active")
            self.assertEqual(saved.status, "active")
            self.assertEqual(saved.version, before["version"] + 1)
            self.assertNotEqual(saved.updated_at, before["updated_at"])
            for field in (
                "id",
                "created_at",
                "created_by",
                "asset_type",
                "name",
                "description",
                "template",
                "variables",
                "applicable_scope",
                "exclusions",
                "usage_notes",
                "limitations",
                "examples",
                "creator_profile_id",
                "source_mechanism_ids",
                "selected_observed_facts",
                "account_fit_reason",
                "confidence_level",
                "confidence",
                "created_from",
            ):
                self.assertEqual(saved.to_dict()[field], before[field])
            self.assertFalse(hasattr(saved, "activated_by"))
            self.assertIn("已激活 1 个内容资产", result.user_summary)
            self.assertIn("开头模板", result.user_summary)
            self.assertIn("原状态：候选", result.user_summary)
            self.assertIn("新状态：已激活", result.user_summary)
            self.assertIn("版本：1 → 2", result.user_summary)
            self.assertIn("仍未自动进入生成上下文", result.user_summary)
            for forbidden in (asset.id, "active", "candidate", "ContentAsset", "GenerationContext", ".json", "/Users/"):
                self.assertNotIn(forbidden, result.user_summary)
            self.assertEqual(
                result.machine_summary,
                {
                    "asset_id": asset.id,
                    "asset_type": "opening_template",
                    "previous_status": "candidate",
                    "new_status": "active",
                    "previous_version": 1,
                    "new_version": 2,
                    "actor": "user",
                    "operation": "activate",
                    "generation_context_connected": False,
                    "decision_request_created": False,
                },
            )
            json.dumps(result.machine_summary, ensure_ascii=False)
            self.assertEqual(JsonRepository(workspace, DecisionRequest).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ProvenanceRecord).list_all(), [])
            self.assertEqual(JsonRepository(workspace, ContentAssetEvidence).list_all(), [])

    def test_deprecate_candidate_and_active_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            repo = JsonRepository(workspace, ContentAsset)
            candidate = repo.create(make_asset(id="asset-candidate"))
            active = repo.create(make_asset(id="asset-active", status="active"))

            candidate_result = deprecate_content_asset(repo, asset_id=candidate.id, expected_version=1, actor="user")
            active_result = deprecate_content_asset(repo, asset_id=active.id, expected_version=1, actor="user")

            self.assertEqual(repo.read(candidate.id).status, "deprecated")
            self.assertEqual(repo.read(active.id).status, "deprecated")
            self.assertEqual(candidate_result.previous_status, "candidate")
            self.assertEqual(active_result.previous_status, "active")
            self.assertIn("历史记录仍保留", active_result.user_summary)
            self.assertIn("不能用于未来显式生成引用", active_result.user_summary)

    def test_illegal_transitions_and_version_conflicts_are_zero_write(self) -> None:
        cases = [
            ("active", activate_content_asset, "当前状态不能执行该操作"),
            ("deprecated", activate_content_asset, "当前状态不能执行该操作"),
            ("deprecated", deprecate_content_asset, "当前状态不能执行该操作"),
        ]
        for status, operation, expected_message in cases:
            with self.subTest(status=status, operation=operation.__name__):
                with tempfile.TemporaryDirectory() as temp_dir:
                    repo = JsonRepository(Path(temp_dir), ContentAsset)
                    asset = repo.create(make_asset(status=status))
                    before = asset.to_dict()

                    with self.assertRaises(ContentAssetLifecycleError) as context:
                        operation(repo, asset_id=asset.id, expected_version=asset.version, actor="user")

                    self.assertIn(expected_message, str(context.exception))
                    self.assertEqual(repo.read(asset.id).to_dict(), before)

        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), ContentAsset)
            asset = repo.create(make_asset())
            before = asset.to_dict()

            with self.assertRaises(ContentAssetLifecycleError) as stale:
                activate_content_asset(repo, asset_id=asset.id, expected_version=asset.version + 1, actor="user")

            self.assertIn("版本冲突", str(stale.exception))
            self.assertEqual(repo.read(asset.id).to_dict(), before)

    def test_invalid_inputs_and_malformed_stored_asset_are_zero_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            repo = JsonRepository(workspace, ContentAsset)
            valid = repo.create(make_asset())
            before = valid.to_dict()

            for kwargs in (
                {"asset_id": "", "expected_version": 1, "actor": "user"},
                {"asset_id": "   ", "expected_version": 1, "actor": "user"},
                {"asset_id": "bad/path", "expected_version": 1, "actor": "user"},
                {"asset_id": valid.id, "expected_version": True, "actor": "user"},
                {"asset_id": valid.id, "expected_version": False, "actor": "user"},
                {"asset_id": valid.id, "expected_version": 0, "actor": "user"},
                {"asset_id": valid.id, "expected_version": -1, "actor": "user"},
                {"asset_id": valid.id, "expected_version": 1.0, "actor": "user"},
                {"asset_id": valid.id, "expected_version": "1", "actor": "user"},
                {"asset_id": valid.id, "expected_version": None, "actor": "user"},
                {"asset_id": valid.id, "expected_version": 1, "actor": "   "},
                {"asset_id": valid.id, "expected_version": 1, "actor": "x" * 257},
            ):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(ContentAssetLifecycleError):
                        activate_content_asset(repo, **kwargs)
                    self.assertEqual(repo.read(valid.id).to_dict(), before)

            with self.assertRaises(ContentAssetLifecycleError) as missing:
                activate_content_asset(repo, asset_id="missing-asset", expected_version=1, actor="user")
            self.assertIn("内容资产不存在", str(missing.exception))

            malformed_path = workspace / ContentAsset.collection_name / "asset-malformed.json"
            malformed = valid.to_dict()
            malformed["id"] = "asset-malformed"
            malformed["status"] = "broken"
            malformed_path.write_text(json.dumps(malformed, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ContentAssetLifecycleError) as invalid:
                activate_content_asset(repo, asset_id="asset-malformed", expected_version=1, actor="user")
            self.assertIn("内容资产数据无效", str(invalid.exception))
            self.assertEqual(repo.read(valid.id).to_dict(), before)

            accepted = activate_content_asset(repo, asset_id=valid.id, expected_version=1, actor="  " + ("x" * 256) + "  ")
            self.assertEqual(accepted.machine_summary["actor"], "x" * 256)

    def test_repository_update_failure_keeps_original_and_retains_cause(self) -> None:
        asset = make_asset()
        repo = FailingUpdateRepository(asset)

        with self.assertRaises(ContentAssetLifecycleError) as context:
            activate_content_asset(repo, asset_id=asset.id, expected_version=asset.version, actor="user")

        self.assertTrue(repo.update_called)
        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertEqual(asset.status, "candidate")
        self.assertEqual(asset.version, 1)

    def test_lifecycle_rejects_stale_version_at_repository_write_boundary(self) -> None:
        first = make_asset(version=1)
        latest = ContentAsset.from_dict({**first.to_dict(), "version": 2, "status": "candidate"})
        repo = RacingRepository(first, latest)

        with self.assertRaises(ContentAssetLifecycleError) as context:
            activate_content_asset(repo, asset_id=first.id, expected_version=1, actor="user")

        self.assertIn("版本冲突", str(context.exception))
        self.assertFalse(repo.update_called)
        self.assertEqual(repo.latest.status, "candidate")
        self.assertEqual(repo.latest.version, 2)


if __name__ == "__main__":
    unittest.main()
