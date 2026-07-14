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
    ContentAsset,
    ContentAssetEvidence,
    ContentMechanism,
    ContentQualityReview,
    ContentDraft,
    CaptureRecord,
    ContentInboxItem,
    CreatorProfile,
    CURRENT_SCHEMA_VERSION,
    CustomTag,
    MODEL_TYPES,
    DecisionRequest,
    ObjectVersion,
    OwnPost,
    PublishTask,
    ProvenanceRecord,
    ReviewRecord,
    RuleCard,
    RuleEvidence,
    TopicItem,
    ValidationError,
)
from app.repositories import JsonRepository, NotFoundError, RepositoryVersionConflictError  # noqa: E402


EXAMPLE_TO_MODEL = {
    "creator-profile.json": CreatorProfile,
    "benchmark-account.json": BenchmarkAccount,
    "benchmark-analysis.json": BenchmarkAnalysis,
    "benchmark-post.json": BenchmarkPost,
    "content-inbox-item.json": ContentInboxItem,
    "content-mechanism.json": ContentMechanism,
    "capture-record.json": CaptureRecord,
    "custom-tag.json": CustomTag,
    "rule-card.json": RuleCard,
    "rule-evidence.json": RuleEvidence,
    "topic-item.json": TopicItem,
    "content-draft.json": ContentDraft,
    "content-quality-review.json": ContentQualityReview,
    "decision-request.json": DecisionRequest,
    "object-version.json": ObjectVersion,
    "publish-task.json": PublishTask,
    "provenance-record.json": ProvenanceRecord,
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
        self.assertEqual(data["schema_version"], CURRENT_SCHEMA_VERSION)
        self.assertNotEqual(data["schema_version"], (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["provenance_refs"], [])
        self.assertEqual(data["created_by"], "user")

    def test_collection_names_are_unique(self) -> None:
        self.assertEqual(len(MODEL_TYPES), 21)
        self.assertEqual(MODEL_TYPES["creator-profiles"], CreatorProfile)
        self.assertEqual(MODEL_TYPES["benchmark-analyses"], BenchmarkAnalysis)
        self.assertEqual(MODEL_TYPES["content-assets"], ContentAsset)
        self.assertEqual(MODEL_TYPES["content-asset-evidence"], ContentAssetEvidence)
        self.assertEqual(MODEL_TYPES["content-inbox"], ContentInboxItem)
        self.assertEqual(MODEL_TYPES["content-mechanisms"], ContentMechanism)
        self.assertEqual(MODEL_TYPES["content-quality-reviews"], ContentQualityReview)
        self.assertEqual(MODEL_TYPES["capture-records"], CaptureRecord)
        self.assertEqual(MODEL_TYPES["decision-requests"], DecisionRequest)
        self.assertEqual(MODEL_TYPES["object-versions"], ObjectVersion)
        self.assertEqual(MODEL_TYPES["provenance-records"], ProvenanceRecord)
        self.assertEqual(MODEL_TYPES["rule-evidence"], RuleEvidence)
        self.assertEqual(MODEL_TYPES["review-records"], ReviewRecord)

    def test_provenance_record_keeps_actor_and_artifact_nature_separate(self) -> None:
        provenance = ProvenanceRecord(
            id="prov-001",
            target_object_type="rule_card",
            target_object_id="rule-001",
            source_object_type="benchmark_analysis",
            source_object_id="analysis-001",
            source_version=2,
            actor="codex",
            artifact_nature="inference",
            method="manual-review-v1",
            note="Codex 判断来自可见事实，不是用户事实。",
        )

        self.assertEqual(provenance.actor, "codex")
        self.assertEqual(provenance.artifact_nature, "inference")

        with self.assertRaises(ValidationError):
            ProvenanceRecord(
                id="prov-invalid",
                target_object_type="rule_card",
                target_object_id="rule-001",
                source_object_type="benchmark_analysis",
                source_object_id="analysis-001",
                actor="codex",
                artifact_nature="user",
                method="manual-review-v1",
                note="actor and nature cannot be collapsed.",
            )

    def test_content_mechanism_can_source_rule_evidence_and_provenance_without_breaking_old_json(self) -> None:
        old_evidence = RuleEvidence(
            id="evidence-old",
            rule_id="rule-old",
            source_type="benchmark_analysis",
            source_id="analysis-old",
            source_fragment="标题",
            evidence_type="title",
            observable_fact="标题包含明确结果",
            inference="该事实支持标题规则。",
        )
        old_provenance = ProvenanceRecord(
            id="provenance-old",
            target_object_type="rule_card",
            target_object_id="rule-old",
            source_object_type="benchmark_analysis",
            source_object_id="analysis-old",
            source_version=1,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-candidate-rules",
            note="旧来源记录。",
        )

        self.assertEqual(RuleEvidence.from_dict(old_evidence.to_dict()).source_type, "benchmark_analysis")
        self.assertEqual(ProvenanceRecord.from_dict(old_provenance.to_dict()).source_object_type, "benchmark_analysis")

        evidence = RuleEvidence(
            id="evidence-mechanism",
            rule_id="rule-mechanism",
            source_type="content_mechanism",
            source_id="mechanism-001",
            source_fragment="evidence_summary.observed_facts[0]",
            evidence_type="content_mechanism",
            observable_fact="标题先讲用户能完成的任务",
            inference="该机制事实支持候选规则。",
        )
        provenance = ProvenanceRecord(
            id="provenance-mechanism",
            target_object_type="rule_card",
            target_object_id="rule-mechanism",
            source_object_type="content_mechanism",
            source_object_id="mechanism-001",
            source_version=1,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-rule-from-mechanism",
            note="候选规则来自内容机制。",
        )

        self.assertEqual(evidence.source_type, "content_mechanism")
        self.assertEqual(provenance.source_object_type, "content_mechanism")

        asset_provenance = ProvenanceRecord(
            id="provenance-asset",
            target_object_type="content_asset",
            target_object_id="asset-001",
            source_object_type="content_mechanism",
            source_object_id="mechanism-001",
            source_version=1,
            actor="codex",
            artifact_nature="recommendation",
            method="propose-asset-from-mechanism",
            note="候选资产来自内容机制。",
        )
        self.assertEqual(asset_provenance.target_object_type, "content_asset")

    def test_decision_request_status_and_selected_option_are_validated(self) -> None:
        decision = DecisionRequest(
            id="decision-001",
            target_object_type="rule_card",
            target_object_id="rule-001",
            question="是否确认这条规则？",
            options=["确认使用", "暂不使用"],
            option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
            recommendation="确认使用",
            recommendation_reason="证据清晰。",
            impact="确认后用于后续标题生成。",
        )

        self.assertEqual(decision.status, "pending")
        self.assertEqual(decision.options, ["确认使用", "暂不使用"])
        self.assertEqual(decision.option_outcomes["确认使用"], "confirmed")

        with self.assertRaises(ValidationError):
            DecisionRequest(
                id="decision-invalid",
                target_object_type="rule_card",
                target_object_id="rule-001",
                question="是否确认？",
                options=["确认使用", "暂不使用"],
                option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
                recommendation="confirm",
                recommendation_reason="证据清晰。",
                impact="确认后生效。",
                status="confirmed",
                selected_option="other",
            )

    def test_decision_request_enforces_status_invariants(self) -> None:
        valid_resolved = DecisionRequest(
            id="decision-confirmed",
            target_object_type="rule_card",
            target_object_id="rule-001",
            question="是否确认？",
            options=["确认使用", "暂不使用"],
            option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
            recommendation="确认使用",
            recommendation_reason="证据清晰。",
            impact="确认后生效。",
            status="confirmed",
            selected_option="确认使用",
            resolved_at="2026-07-08T00:00:00Z",
            resolved_by="user",
            resulting_state_changes=[{"field": "status", "value": "approved"}],
        )
        self.assertEqual(valid_resolved.status, "confirmed")

        invalid_cases = [
            {"status": "confirmed", "selected_option": "", "resolved_at": None},
            {"status": "pending", "selected_option": "确认使用", "resolved_at": "2026-07-08T00:00:00Z"},
            {"status": "pending", "selected_option": "", "resolved_at": None, "resolved_by": "user"},
            {
                "status": "pending",
                "selected_option": "",
                "resolved_at": None,
                "resulting_state_changes": [{"field": "status"}],
            },
            {"status": "rejected", "selected_option": "确认使用", "resolved_at": "2026-07-08T00:00:00Z"},
            {"status": "confirmed", "selected_option": "确认使用", "resolved_at": "2026-07-08T00:00:00Z", "resolved_by": None},
            {"status": "cancelled", "selected_option": "", "resolved_at": None},
            {"status": "superseded", "selected_option": "", "resolved_at": None},
        ]
        for case in invalid_cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                DecisionRequest(
                    id="decision-bad",
                    target_object_type="rule_card",
                    target_object_id="rule-001",
                    question="是否确认？",
                    options=["确认使用", "暂不使用"],
                    option_outcomes={"确认使用": "confirmed", "暂不使用": "rejected"},
                    recommendation="确认使用",
                    recommendation_reason="证据清晰。",
                    impact="确认后生效。",
                    **case,
                )

    def test_rule_card_default_status_is_candidate(self) -> None:
        rule = RuleCard(
            id="rule-default-status",
            name="默认候选规则",
            type="title",
            source_ids=["analysis-001"],
            applicable_scenarios=["标题"],
            rule_summary="缺少 status 时不能直接进入正式规则。",
            examples=["例子"],
            risks=["风险"],
            adaptation_notes="需要确认。",
        )
        approved = RuleCard(
            id="rule-explicit-approved",
            name="显式正式规则",
            type="title",
            source_ids=["user-feedback"],
            applicable_scenarios=["标题"],
            rule_summary="用户明确确认的长期规则。",
            examples=["例子"],
            risks=["风险"],
            adaptation_notes="已确认。",
            status="approved",
        )

        self.assertEqual(rule.status, "candidate")
        self.assertEqual(approved.status, "approved")

    def test_repository_update_preserves_previous_version_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(temp_dir, RuleCard)
            rule = RuleCard(
                id="rule-versioned",
                name="候选标题规则",
                type="title",
                source_ids=["analysis-001"],
                applicable_scenarios=["标题"],
                rule_summary="标题要像真人经验。",
                examples=["我试过后发现..."],
                risks=["不能夸张承诺"],
                adaptation_notes="适合账号口吻。",
                status="candidate",
            )
            repo.create(rule)

            updated = repo.update("rule-versioned", {"status": "approved"})
            versions = JsonRepository(temp_dir, ObjectVersion).list_all()

            self.assertEqual(updated.version, 2)
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].target_object_type, "rule_card")
            self.assertEqual(versions[0].target_object_id, "rule-versioned")
            self.assertEqual(versions[0].object_version, 1)
            self.assertEqual(versions[0].snapshot["status"], "candidate")

    def test_repository_upsert_preserves_versions_for_versioned_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(temp_dir, CreatorProfile)
            first = CreatorProfile(
                id="creator-versioned",
                name="账号",
                positioning="职场表达",
                target_audience=["职场新人"],
                content_style=["真实"],
                goals=["提升收藏"],
                content_formats=["图文"],
                publish_frequency="每周 3 篇",
                notes="第一版。",
            )
            saved_first = repo.upsert(first, changed_by="user", change_note="首次录入账号档案")
            second = CreatorProfile(
                id="creator-versioned",
                name="账号",
                positioning="职场表达更新",
                target_audience=["职场新人"],
                content_style=["真实"],
                goals=["提升收藏"],
                content_formats=["图文"],
                publish_frequency="每周 3 篇",
                notes="第二版。",
            )
            saved_second = repo.upsert(second, changed_by="user", change_note="用户更新账号定位")
            versions = JsonRepository(temp_dir, ObjectVersion).list_all()

            self.assertEqual(saved_first.version, 1)
            self.assertEqual(saved_second.version, 2)
            self.assertEqual(saved_second.created_at, saved_first.created_at)
            self.assertNotEqual(saved_second.updated_at, saved_first.updated_at)
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].changed_by, "user")
            self.assertEqual(versions[0].change_note, "用户更新账号定位")
            self.assertEqual(versions[0].snapshot["positioning"], "职场表达")

    def test_repository_upsert_versions_rule_and_draft_but_not_non_versioned_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            rule_repo = JsonRepository(temp_dir, RuleCard)
            draft_repo = JsonRepository(temp_dir, ContentDraft)
            tag_repo = JsonRepository(temp_dir, CustomTag)
            rule_repo.upsert(
                RuleCard(
                    id="rule-upsert",
                    name="规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="第一版规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="适合账号。",
                    status="candidate",
                ),
                changed_by="codex",
                change_note="Codex 创建候选规则",
            )
            rule = rule_repo.upsert(
                RuleCard(
                    id="rule-upsert",
                    name="规则",
                    type="title",
                    source_ids=["analysis-001"],
                    applicable_scenarios=["标题"],
                    rule_summary="第二版规则。",
                    examples=["例子"],
                    risks=["风险"],
                    adaptation_notes="适合账号。",
                    status="candidate",
                ),
                changed_by="codex",
                change_note="Codex 更新候选规则",
            )
            draft_repo.upsert(
                ContentDraft(
                    id="draft-upsert",
                    topic_id="topic-001",
                    titles=["标题 A"],
                    cover_titles=["封面 A"],
                    script="第一版脚本",
                    shot_suggestions=["镜头 A"],
                    created_by="codex",
                ),
                changed_by="codex",
                change_note="生成初稿",
            )
            draft = draft_repo.upsert(
                ContentDraft(
                    id="draft-upsert",
                    topic_id="topic-001",
                    titles=["标题 B"],
                    cover_titles=["封面 B"],
                    script="第二版脚本",
                    shot_suggestions=["镜头 B"],
                    created_by="codex",
                ),
                changed_by="codex",
                change_note="重写草稿",
            )
            tag_repo.upsert(CustomTag(id="tag-upsert", name="标签", description="第一版", scope=["rule_card"]))
            tag_repo.upsert(CustomTag(id="tag-upsert", name="标签", description="第二版", scope=["rule_card"]))
            versions = JsonRepository(temp_dir, ObjectVersion).list_all()

            self.assertEqual(rule.version, 2)
            self.assertEqual(draft.version, 2)
            self.assertEqual(len(versions), 2)
            self.assertFalse(any(item.target_object_type == "custom_tag" for item in versions))

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


def make_repository_asset(asset_id: str) -> ContentAsset:
    return ContentAsset(
        id=asset_id,
        status="candidate",
        asset_type="opening_template",
        name="任务结果优先开场",
        description="用于先呈现用户可完成的内容运营结果，再解释工具和过程。",
        template="结果：{{result}}\n过程：{{process}}",
        variables=["result", "process"],
        applicable_scope=["AI 内容运营"],
        exclusions=[],
        usage_notes=[],
        limitations=[],
        examples=[],
        creator_profile_id="creator-main",
        source_mechanism_ids=["mechanism-result-framing"],
        selected_observed_facts=["标题先展示结果承诺，再说明使用的工具和流程"],
        account_fit_reason="提案中的账号适配理由。",
        confidence_level="medium",
        confidence=0.6,
    )


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

    def test_update_if_version_updates_only_when_expected_version_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), ContentAsset)
            first = repo.create(make_repository_asset("asset-conditional"))
            sibling = repo.create(make_repository_asset("asset-sibling"))

            updated = repo.update_if_version(
                first.id,
                expected_version=1,
                changes={"status": "active", "id": "malicious-id", "version": 99},
                changed_by="user",
                change_note="activate content asset",
            )

            self.assertEqual(updated.id, first.id)
            self.assertEqual(updated.status, "active")
            self.assertEqual(updated.version, 2)
            self.assertEqual(repo.read(sibling.id).to_dict(), sibling.to_dict())

            with self.assertRaises(RepositoryVersionConflictError):
                repo.update_if_version(first.id, expected_version=1, changes={"status": "deprecated"})
            with self.assertRaises(RepositoryVersionConflictError):
                repo.update_if_version(first.id, expected_version=999, changes={"status": "deprecated"})
            with self.assertRaises(NotFoundError):
                repo.update_if_version("missing-asset", expected_version=1, changes={"status": "active"})

            self.assertFalse((Path(temp_dir) / ContentAsset.collection_name / "missing-asset.json").exists())

    def test_update_if_version_does_not_call_update_fn_on_version_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = JsonRepository(Path(temp_dir), ContentAsset)
            asset = repo.create(make_repository_asset("asset-callback"))
            called = False

            def update_fn(data: dict[str, object]) -> dict[str, object]:
                nonlocal called
                called = True
                return {**data, "status": "active"}

            with self.assertRaises(RepositoryVersionConflictError):
                repo.update_if_version(asset.id, expected_version=2, update_fn=update_fn)

            self.assertFalse(called)
            self.assertEqual(repo.read(asset.id).to_dict(), asset.to_dict())


if __name__ == "__main__":
    unittest.main()
