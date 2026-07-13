import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.mechanisms.intake import import_mechanism_candidate  # noqa: E402
from app.models.core import ContentMechanism, ValidationError  # noqa: E402
from app.repositories import JsonRepository  # noqa: E402


def valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "mechanism-result-framing",
        "name": "复杂工具结果化表达",
        "description": "把复杂工具能力先翻译成用户可感知的运营结果。",
        "status": "candidate",
        "confidence_level": "medium",
        "source_refs": [
            {"source_type": "benchmark_analysis", "source_id": "analysis-001"},
            {"source_type": "capture_record", "source_id": "capture-001"},
        ],
        "evidence_summary": {
            "observed_facts": ["标题同时出现工具名和可见结果"],
            "inferences": ["内容把工具组合包装成结果"],
            "user_stated_preferences": [],
            "missing_information": [],
            "limitations": [],
            "source_coverage": {"title": "present", "body": "present"},
        },
        "problem": "复杂工具内容容易让用户只看到工具名。",
        "solution": "先讲结果，再解释工具如何实现。",
        "pattern": ["工具组合", "结果承诺", "流程证据"],
        "applicable_scope": ["AI工具内容"],
        "limitations": ["不能夸大时间承诺"],
    }
    payload.update(overrides)
    return payload


class ContentMechanismModelTests(unittest.TestCase):
    def test_content_mechanism_round_trips(self) -> None:
        result = import_mechanism_candidate(valid_payload())
        self.assertEqual(result.status_category, "created")
        self.assertIsNotNone(result.mechanism)

        data = result.mechanism.to_dict()
        restored = ContentMechanism.from_dict(data)

        self.assertEqual(restored.id, "mechanism-result-framing")
        self.assertEqual(restored.status, "candidate")
        self.assertEqual(restored.confidence_level, "medium")
        self.assertEqual(restored.confidence, 0.6)
        self.assertEqual(restored.evidence_summary["observed_facts"], ["标题同时出现工具名和可见结果"])

    def test_content_mechanism_allows_model_statuses_but_validates_confidence_level(self) -> None:
        for status in ("candidate", "active", "deprecated"):
            with self.subTest(status=status):
                mechanism = ContentMechanism.from_dict(
                    {
                        **valid_payload(),
                        "status": status,
                        "confidence_level": "low",
                        "confidence": 0.4,
                    }
                )
                self.assertEqual(mechanism.status, status)

        with self.assertRaises(ValidationError):
            ContentMechanism.from_dict({**valid_payload(), "confidence_level": "certain"})

    def test_content_mechanism_requires_structured_evidence_summary(self) -> None:
        with self.assertRaises(ValidationError):
            ContentMechanism.from_dict({**valid_payload(), "evidence_summary": "标题很好"})
        with self.assertRaises(ValidationError):
            ContentMechanism.from_dict({**valid_payload(), "evidence_summary": {}})

    def test_content_mechanism_rejects_invalid_source_ref_shape(self) -> None:
        with self.assertRaises(ValidationError):
            ContentMechanism.from_dict(
                {
                    **valid_payload(),
                    "source_refs": [{"source_type": "benchmark_analysis", "source_id": ""}],
                }
            )


class ContentMechanismIntakeTests(unittest.TestCase):
    def test_full_input_creates_candidate_mechanism(self) -> None:
        result = import_mechanism_candidate(valid_payload())

        self.assertTrue(result.created)
        self.assertEqual(result.status_category, "created")
        self.assertEqual(result.mechanism.status, "candidate")
        self.assertEqual(result.mechanism.confidence_level, "medium")
        self.assertEqual(result.machine_summary["source_refs"], valid_payload()["source_refs"])

    def test_partial_input_with_missing_information_is_limited_created(self) -> None:
        result = import_mechanism_candidate(
            valid_payload(
                id="mechanism-limited",
                source_refs=[],
                evidence_summary={
                    "observed_facts": ["封面强调 10 分钟完成一个看得见的结果"],
                    "inferences": ["可能适合结果化包装"],
                    "missing_information": ["未获取评论区", "未获取完整视频关键帧"],
                    "limitations": ["不能确认真实用户需求"],
                },
                solution="",
                pattern=[],
                confidence_level="high",
            )
        )

        self.assertTrue(result.created)
        self.assertEqual(result.status_category, "limited_created")
        self.assertEqual(result.mechanism.status, "candidate")
        self.assertEqual(result.mechanism.confidence_level, "low")
        self.assertIn("未获取评论区", result.missing_information)
        self.assertIn("不会影响正式生成", result.user_summary)

    def test_inference_only_input_does_not_create_mechanism(self) -> None:
        result = import_mechanism_candidate(
            valid_payload(
                id="mechanism-inference-only",
                evidence_summary={
                    "observed_facts": [],
                    "inferences": ["这个内容应该很适合学习"],
                    "user_stated_preferences": [],
                    "missing_information": [],
                    "limitations": [],
                },
            )
        )

        self.assertFalse(result.created)
        self.assertEqual(result.status_category, "not_enough_evidence")
        self.assertIsNone(result.mechanism)
        self.assertIn("至少一条可观察事实", result.user_summary)

    def test_user_opinion_only_input_does_not_create_mechanism(self) -> None:
        result = import_mechanism_candidate(
            valid_payload(
                id="mechanism-opinion-only",
                evidence_summary={
                    "observed_facts": [],
                    "inferences": [],
                    "user_stated_preferences": ["这个标题挺好，适合学"],
                    "missing_information": [],
                    "limitations": [],
                },
            )
        )

        self.assertFalse(result.created)
        self.assertEqual(result.status_category, "not_enough_evidence")
        self.assertIsNone(result.mechanism)

    def test_invalid_status_is_rejected_before_write(self) -> None:
        result = import_mechanism_candidate(valid_payload(status="active"))

        self.assertFalse(result.created)
        self.assertEqual(result.status_category, "invalid_input")
        self.assertIsNone(result.mechanism)

    def test_invalid_input_with_empty_problem_and_solution_is_rejected(self) -> None:
        result = import_mechanism_candidate(
            valid_payload(
                name="机制",
                description="这是一个机制",
                evidence_summary={"observed_facts": ["很好"]},
                problem="",
                solution="",
                pattern=[],
            )
        )

        self.assertFalse(result.created)
        self.assertEqual(result.status_category, "invalid_input")

    def test_service_result_is_json_serializable(self) -> None:
        result = import_mechanism_candidate(valid_payload())

        json.dumps(result.to_output(), ensure_ascii=False)

    def test_repository_can_save_only_content_mechanism(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = import_mechanism_candidate(valid_payload())
            JsonRepository(Path(temp_dir), ContentMechanism).create(result.mechanism)

            saved = JsonRepository(Path(temp_dir), ContentMechanism).read("mechanism-result-framing")
            self.assertEqual(saved.status, "candidate")
            self.assertEqual(saved.created_by, "codex")
