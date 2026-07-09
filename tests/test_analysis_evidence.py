import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analysis.outcome import build_analysis_outcome  # noqa: E402
from app.analysis import analyze_capture  # noqa: E402
from app.models.core import CaptureRecord  # noqa: E402


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

        self.assertEqual(outcome["status_category"], "partial")
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


if __name__ == "__main__":
    unittest.main()
