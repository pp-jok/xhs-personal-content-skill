import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analysis.outcome import build_analysis_outcome  # noqa: E402
from app.analysis import analyze_capture  # noqa: E402
from app.models.core import BenchmarkAnalysis, CaptureRecord  # noqa: E402


class AnalysisEvidenceOutcomeTests(unittest.TestCase):
    def test_image_post_with_title_and_body_returns_evidence_first_summary(self) -> None:
        capture = CaptureRecord(
            id="capture-image",
            inbox_item_id="inbox-image",
            source_url="https://www.xiaohongshu.com/explore/image",
            capture_status="partial",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题，最后给一个具体做法。",
            content_type="image",
            author={"name": "可见账号"},
            metrics={"likes": 12, "collects": 8, "comments": 3, "shares": 1},
            images=[{"remote_url": "https://example.test/image.jpg", "path": "capture/image.jpg", "alt": "首图"}],
            comments=[{"content": "这个方法适合新人"}],
            available_fields=["title", "body", "author", "metrics.likes", "images", "comments"],
            missing_fields=["published_at"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        self.assertEqual(outcome["status_category"], "complete")
        self.assertIn("【客观数据】", outcome["user_summary"])
        self.assertIn("【Codex 判断】", outcome["user_summary"])
        self.assertIn("【信息不足】", outcome["user_summary"])
        self.assertTrue(any(item["field"] == "标题" and item["value"] == capture.title for item in outcome["observed_facts"]))
        self.assertTrue(any(item["dimension"] == "标题" and item["evidence"] for item in outcome["analysis_judgments"]))
        summary = outcome["user_summary"]
        self.assertNotIn("candidate-rule", summary)
        self.assertNotIn("account_fit", summary)

    def test_video_structure_does_not_claim_video_semantics(self) -> None:
        capture = CaptureRecord(
            id="capture-video",
            inbox_item_id="inbox-video",
            source_url="https://www.xiaohongshu.com/explore/video",
            capture_status="partial",
            title="新手表达练习方法",
            body="这条内容展示了一个练习步骤。",
            content_type="video",
            video={"duration_seconds": 35, "media_type": "video"},
            available_fields=["title", "body", "video"],
            missing_fields=["video.keyframes", "video.subtitles", "audio.transcript", "comments"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        facts_text = " ".join(str(item) for item in outcome["observed_facts"])
        summary = outcome["user_summary"]
        self.assertIn("视频结构", facts_text)
        self.assertIn("没有视频帧或字幕", summary)
        self.assertNotIn("前 3 秒", summary)
        self.assertNotIn("镜头", summary)
        self.assertNotIn("音乐", summary)
        self.assertNotIn("剪辑节奏", summary)

    def test_image_url_or_alt_is_not_treated_as_understood_cover_content(self) -> None:
        capture = CaptureRecord(
            id="capture-cover",
            inbox_item_id="inbox-cover",
            source_url="https://www.xiaohongshu.com/explore/cover",
            capture_status="partial",
            title="表达能力提升方法",
            body="正文可见。",
            content_type="image",
            images=[{"remote_url": "https://example.test/image.jpg", "path": "/tmp/image.jpg", "alt": "首图"}],
            available_fields=["title", "body", "images"],
            missing_fields=["image.content"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        summary = outcome["user_summary"]
        self.assertIn("没有图片内容证据", summary)
        self.assertNotIn("构图", " ".join(item["judgment"] for item in outcome["analysis_judgments"]))
        self.assertNotIn("人物", summary)
        self.assertNotIn("产品", summary)
        self.assertNotIn("色彩", summary)

    def test_metrics_none_are_not_rendered_as_zero_or_performance_result(self) -> None:
        capture = CaptureRecord(
            id="capture-metrics",
            inbox_item_id="inbox-metrics",
            source_url="https://www.xiaohongshu.com/explore/metrics",
            capture_status="partial",
            title="新手表达方法",
            body="正文可见。",
            content_type="image",
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            available_fields=["title", "body", "metrics"],
            missing_fields=["metrics.likes", "metrics.collects", "metrics.comments", "metrics.shares"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        summary = outcome["user_summary"]
        self.assertNotIn("0", summary)
        self.assertNotIn("表现好", summary)
        self.assertNotIn("表现差", summary)
        self.assertIn("没有获取到完整互动数据", summary)

    def test_missing_title_and_body_is_insufficient_even_when_capture_succeeded(self) -> None:
        capture = CaptureRecord(
            id="capture-empty",
            inbox_item_id="inbox-empty",
            source_url="https://www.xiaohongshu.com/explore/empty",
            capture_status="success",
            content_type="image",
            images=[{"path": "capture/image.jpg"}],
            available_fields=["title", "body", "images"],
            missing_fields=[],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        self.assertEqual(outcome["status_category"], "insufficient")
        self.assertFalse(outcome["decision_readiness"]["can_decide_benchmark_value"])
        self.assertIn("缺少标题和正文", outcome["decision_readiness"]["reason"])

    def test_failed_capture_with_body_keeps_observed_fact_but_not_complete(self) -> None:
        capture = CaptureRecord(
            id="capture-failed-body",
            inbox_item_id="inbox-failed-body",
            source_url="https://www.xiaohongshu.com/explore/failed-body",
            capture_status="failed",
            body="用户手动补充的一段正文。",
            content_type="unknown",
            available_fields=["body"],
            missing_fields=["title"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        self.assertEqual(outcome["status_category"], "partial")
        self.assertTrue(any(item["field"] == "正文" for item in outcome["observed_facts"]))
        self.assertIn("不是完整采集", outcome["user_summary"])

    def test_requested_title_focus_is_complete_when_title_analysis_has_evidence(self) -> None:
        capture = CaptureRecord(
            id="capture-title-focus",
            inbox_item_id="inbox-title-focus",
            source_url="https://www.xiaohongshu.com/explore/title-focus",
            capture_status="partial",
            title="新手如何做清晰表达",
            content_type="image",
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            images=[{"path": "capture/image.jpg"}],
            missing_fields=["image.content", "comments", "metrics.likes"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["标题"])

        self.assertEqual(outcome["status_category"], "complete")
        self.assertTrue(any("图片" in gap for gap in outcome["information_gaps"]))
        self.assertTrue(any("评论" in gap for gap in outcome["information_gaps"]))
        self.assertTrue(any("互动" in gap for gap in outcome["information_gaps"]))

    def test_title_only_focus_readiness_does_not_claim_body_is_enough(self) -> None:
        capture = CaptureRecord(
            id="capture-title-readiness",
            inbox_item_id="inbox-title-readiness",
            source_url="https://www.xiaohongshu.com/explore/title-readiness",
            capture_status="partial",
            title="新手如何做清晰表达",
            content_type="image",
            missing_fields=["body", "image.content", "comments", "metrics.likes"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["标题"])

        self.assertEqual(outcome["status_category"], "complete")
        reason = outcome["decision_readiness"]["reason"]
        self.assertIn("标题证据足够", reason)
        self.assertIn("标题表达", reason)
        self.assertNotIn("正文", reason)
        self.assertNotIn("正文", outcome["user_summary"].split("【是否可以继续判断】", 1)[1])
        self.assertTrue(outcome["decision_readiness"]["can_decide_requested_focus"])

    def test_requested_cover_focus_is_not_complete_without_image_content_evidence(self) -> None:
        capture = CaptureRecord(
            id="capture-cover-focus",
            inbox_item_id="inbox-cover-focus",
            source_url="https://www.xiaohongshu.com/explore/cover-focus",
            capture_status="success",
            title="表达能力提升方法",
            body="正文可见。",
            content_type="image",
            images=[{"remote_url": "https://example.test/image.jpg", "path": "capture/image.jpg"}],
            missing_fields=["image.content"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["封面"])

        self.assertNotEqual(outcome["status_category"], "complete")

    def test_cover_focus_readiness_is_false_without_image_content_evidence(self) -> None:
        capture = CaptureRecord(
            id="capture-cover-readiness",
            inbox_item_id="inbox-cover-readiness",
            source_url="https://www.xiaohongshu.com/explore/cover-readiness",
            capture_status="success",
            title="表达能力提升方法",
            body="正文可见。",
            content_type="image",
            images=[{"remote_url": "https://example.test/image.jpg", "path": "capture/image.jpg"}],
            missing_fields=["image.content"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["封面"])

        self.assertNotEqual(outcome["status_category"], "complete")
        self.assertFalse(outcome["decision_readiness"]["can_decide_benchmark_value"])
        self.assertFalse(outcome["decision_readiness"]["can_decide_requested_focus"])
        self.assertIn("封面", outcome["decision_readiness"]["reason"])
        self.assertIn("图片内容证据", outcome["decision_readiness"]["reason"])

    def test_requested_title_and_structure_is_partial_when_body_is_missing(self) -> None:
        capture = CaptureRecord(
            id="capture-title-only",
            inbox_item_id="inbox-title-only",
            source_url="https://www.xiaohongshu.com/explore/title-only",
            capture_status="partial",
            title="新手如何做清晰表达",
            content_type="image",
            missing_fields=["body"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["标题", "正文结构"])

        self.assertEqual(outcome["status_category"], "partial")
        reason = outcome["decision_readiness"]["reason"]
        self.assertIn("标题可以判断", reason)
        self.assertIn("正文结构证据不足", reason)

    def test_default_core_dimensions_are_complete_when_title_and_body_are_valid(self) -> None:
        capture = CaptureRecord(
            id="capture-default-complete",
            inbox_item_id="inbox-default-complete",
            source_url="https://www.xiaohongshu.com/explore/default-complete",
            capture_status="partial",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题，最后给一个具体做法。",
            content_type="image",
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            images=[{"path": "capture/image.jpg"}],
            missing_fields=["image.content", "comments", "metrics.likes"],
        )
        analysis = analyze_capture(capture)

        outcome = build_analysis_outcome(capture, analysis)

        self.assertEqual(outcome["status_category"], "complete")
        self.assertTrue(outcome["information_gaps"])
        self.assertIn("标题和正文结构证据足够", outcome["decision_readiness"]["reason"])

    def test_outcome_uses_saved_analysis_inference_without_creating_title_judgment(self) -> None:
        capture = CaptureRecord(
            id="capture-saved-analysis",
            inbox_item_id="inbox-saved-analysis",
            source_url="https://www.xiaohongshu.com/explore/saved-analysis",
            capture_status="success",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题，最后给一个具体做法。",
            content_type="image",
        )
        analysis = analyze_capture(capture)
        analysis.title_analysis["inference"] = "这是来自已保存 BenchmarkAnalysis 的标题判断"

        outcome = build_analysis_outcome(capture, analysis)

        judgments = [item["judgment"] for item in outcome["analysis_judgments"] if item["dimension"] == "标题"]
        self.assertEqual(judgments, ["这是来自已保存 BenchmarkAnalysis 的标题判断"])

    def test_cover_inference_without_image_content_evidence_is_filtered(self) -> None:
        capture = CaptureRecord(
            id="capture-filter-cover",
            inbox_item_id="inbox-filter-cover",
            source_url="https://www.xiaohongshu.com/explore/filter-cover",
            capture_status="success",
            title="表达能力提升方法",
            body="正文可见。",
            content_type="image",
            images=[{"remote_url": "https://example.test/image.jpg", "path": "capture/image.jpg"}],
            missing_fields=["image.content"],
        )
        analysis = analyze_capture(capture)
        analysis.cover_analysis["inference"] = "封面采用人物居中构图"

        outcome = build_analysis_outcome(capture, analysis, requested_focus=["封面"])

        self.assertFalse(any(item["judgment"] == "封面采用人物居中构图" for item in outcome["analysis_judgments"]))
        self.assertTrue(any("图片内容证据" in gap for gap in outcome["information_gaps"]))

    def test_user_summary_hides_account_fit_and_candidate_rule_ids(self) -> None:
        capture = CaptureRecord(
            id="capture-hidden-boundaries",
            inbox_item_id="inbox-hidden-boundaries",
            source_url="https://www.xiaohongshu.com/explore/hidden-boundaries",
            capture_status="success",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题，最后给一个具体做法。",
            content_type="image",
        )
        analysis = BenchmarkAnalysis(
            id="analysis-hidden-boundaries",
            capture_id=capture.id,
            title_analysis={"observable": capture.title, "inference": "标题判断来自 analysis"},
            structure_analysis={"observable": capture.body, "inference": "结构判断来自 analysis"},
            account_fit={"inference": "适合你的账号"},
            candidate_rule_ids=["candidate-rule-hidden"],
        )

        outcome = build_analysis_outcome(capture, analysis)

        self.assertNotIn("account_fit", outcome["user_summary"])
        self.assertNotIn("适合你的账号", outcome["user_summary"])
        self.assertNotIn("candidate-rule-hidden", outcome["user_summary"])


if __name__ == "__main__":
    unittest.main()
