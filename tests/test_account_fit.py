import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analysis.account_fit import assess_account_fit, build_account_fit_summary  # noqa: E402
from app.models.core import BenchmarkAnalysis, CaptureRecord, CreatorProfile  # noqa: E402


class AccountFitAssessmentTests(unittest.TestCase):
    def test_complete_profile_assesses_title_and_structure_with_user_safe_summary(self) -> None:
        capture = make_capture()
        analysis = make_analysis(capture)
        analysis.candidate_rule_ids = ["candidate-rule-hidden"]

        result = assess_account_fit(capture, analysis, make_profile())
        summary = build_account_fit_summary(result)

        self.assertEqual(result["status_category"], "complete")
        self.assertEqual({item["element"] for item in result["assessments"]}, {"标题", "正文结构"})
        for assessment in result["assessments"]:
            self.assertTrue(assessment["post_evidence"])
            self.assertTrue(assessment["profile_evidence"])
        self.assertTrue(result["decision_readiness"]["can_decide_reference_value"])
        for section in (
            "【帖子中看到的内容】",
            "【与你账号的匹配判断】",
            "【需要调整的地方】",
            "【不建议直接使用的部分】",
            "【信息不足】",
            "【是否值得作为你的参考】",
        ):
            self.assertIn(section, summary)
        self.assertNotIn("account_fit", summary)
        self.assertNotIn("directly_borrowable", summary)
        self.assertNotIn("creator-main", summary)
        self.assertNotIn("candidate-rule-hidden", summary)
        self.assertNotIn("rule-", summary)

    def test_missing_profile_returns_insufficient_without_inventing_preference(self) -> None:
        result = assess_account_fit(make_capture(), make_analysis(make_capture()), None)

        self.assertEqual(result["status_category"], "insufficient")
        self.assertFalse(result["assessments"])
        self.assertIn("账号档案", " ".join(result["profile_gaps"]))
        self.assertFalse(result["decision_readiness"]["can_decide_reference_value"])

    def test_partial_profile_keeps_positioning_judgment_and_marks_style_gap(self) -> None:
        capture = make_capture()
        profile = make_profile(target_audience=[], content_style=[])

        result = assess_account_fit(capture, make_analysis(capture), profile)

        by_element = {item["element"]: item for item in result["assessments"]}
        self.assertEqual(result["status_category"], "partial")
        self.assertNotEqual(by_element["标题"]["classification"], "insufficient_information")
        self.assertEqual(by_element["正文结构"]["classification"], "insufficient_information")
        self.assertIn("内容风格", " ".join(result["profile_gaps"]))

    def test_title_only_analysis_does_not_claim_whole_post_is_ready(self) -> None:
        capture = make_capture(body="")
        analysis = BenchmarkAnalysis(
            id="analysis-title-only",
            capture_id=capture.id,
            title_analysis={"observable": capture.title, "inference": "标题提出具体练习问题。"},
        )

        result = assess_account_fit(capture, analysis, make_profile())

        self.assertEqual([item["element"] for item in result["assessments"]], ["标题"])
        self.assertFalse(result["decision_readiness"]["can_decide_reference_value"])
        self.assertIn("标题", result["decision_readiness"]["reason"])
        self.assertNotIn("整篇", result["overall_summary"])

    def test_explicit_style_conflict_is_adaptable(self) -> None:
        capture = make_capture(body="用强刺激口吻强调问题，再给出步骤。")
        profile = make_profile(content_style=["克制表达"])

        result = assess_account_fit(capture, make_analysis(capture), profile)

        structure = next(item for item in result["assessments"] if item["element"] == "正文结构")
        self.assertEqual(structure["classification"], "adaptable")
        self.assertTrue(structure["adaptation_guidance"])

    def test_forbidden_expression_limits_only_matching_element(self) -> None:
        capture = make_capture(title="保证三天学会表达")
        profile = make_profile(forbidden_expressions=["保证"])

        result = assess_account_fit(capture, make_analysis(capture), profile)

        by_element = {item["element"]: item for item in result["assessments"]}
        self.assertEqual(by_element["标题"]["classification"], "not_recommended")
        self.assertNotEqual(by_element["正文结构"]["classification"], "not_recommended")

    def test_explicit_absolute_promise_is_risky_only_with_profile_style_boundary(self) -> None:
        capture = make_capture(title="百分之百解决表达问题")
        profile = make_profile(content_style=["克制表达"])

        result = assess_account_fit(capture, make_analysis(capture), profile)

        title = next(item for item in result["assessments"] if item["element"] == "标题")
        self.assertEqual(title["classification"], "risky")
        self.assertTrue(title["profile_evidence"])

    def test_notes_do_not_replace_missing_core_profile_fields(self) -> None:
        capture = make_capture()
        profile = make_profile(content_style=[], notes="账号应保持克制表达。")

        result = assess_account_fit(capture, make_analysis(capture), profile)

        structure = next(item for item in result["assessments"] if item["element"] == "正文结构")
        self.assertEqual(structure["classification"], "insufficient_information")
        self.assertIn("内容风格", " ".join(result["profile_gaps"]))

    def test_visual_inference_without_capture_content_does_not_create_visual_assessment(self) -> None:
        capture = make_capture(images=[{"remote_url": "https://example.test/image.jpg", "path": "capture/image.jpg", "alt": "首图"}])
        analysis = make_analysis(capture)
        analysis.cover_analysis = {
            "observable": {"content_text": "不受采集支持的封面文字"},
            "inference": "封面采用方法型表达。",
        }

        result = assess_account_fit(capture, analysis, make_profile())

        self.assertNotIn("封面与图片", [item["element"] for item in result["assessments"]])

    def test_metrics_do_not_change_account_fit_classification(self) -> None:
        capture = make_capture(metrics={"likes": 99999, "collects": 88888})
        low_capture = make_capture(metrics={"likes": 1, "collects": 0})

        high_result = assess_account_fit(capture, make_analysis(capture), make_profile())
        low_result = assess_account_fit(low_capture, make_analysis(low_capture), make_profile())

        self.assertEqual(
            [(item["element"], item["classification"]) for item in high_result["assessments"]],
            [(item["element"], item["classification"]) for item in low_result["assessments"]],
        )
        self.assertNotIn("表现好", build_account_fit_summary(high_result))


def make_capture(**changes: object) -> CaptureRecord:
    data = {
        "id": "capture-account-fit",
        "inbox_item_id": "inbox-account-fit",
        "source_url": "https://www.xiaohongshu.com/explore/account-fit",
        "capture_status": "success",
        "title": "新手如何练习清晰表达",
        "body": "先说明对象，再给出三个可以当天完成的练习步骤。",
        "content_type": "image",
        "metrics": {},
    }
    data.update(changes)
    return CaptureRecord(**data)


def make_analysis(capture: CaptureRecord) -> BenchmarkAnalysis:
    return BenchmarkAnalysis(
        id=f"analysis-from-{capture.id}",
        capture_id=capture.id,
        title_analysis={"observable": capture.title, "inference": "标题提出具体练习问题。"},
        structure_analysis={"observable": capture.body, "inference": "正文按对象、步骤展开。"},
    )


def make_profile(**changes: object) -> CreatorProfile:
    data = {
        "id": "creator-main",
        "name": "主账号",
        "positioning": "帮助职场新人提升表达能力",
        "target_audience": ["职场新人"],
        "content_style": ["具体、真诚"],
        "forbidden_expressions": [],
        "goals": ["建立信任"],
        "content_formats": ["图文"],
        "publish_frequency": "每周 3 次",
        "notes": "先给出可执行建议。",
    }
    data.update(changes)
    return CreatorProfile(**data)


if __name__ == "__main__":
    unittest.main()
