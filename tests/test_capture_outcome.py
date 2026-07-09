import unittest

from app.capture.outcome import build_capture_error_outcome, build_capture_outcome
from app.models.core import CaptureRecord


class CaptureOutcomeTests(unittest.TestCase):
    def test_success_outcome_summarizes_available_content_and_next_step(self) -> None:
        record = CaptureRecord(
            id="capture-success",
            inbox_item_id="inbox-success",
            source_url="https://www.xiaohongshu.com/explore/success?xsec_token=secret",
            capture_method="browser_authorized",
            capture_status="success",
            title="新手如何做清晰表达",
            body="先讲对象，再讲问题。",
            content_type="image",
            author={"name": "可见作者"},
            metrics={"likes": 12, "collects": 8, "comments": 3, "shares": 1},
            images=[{"remote_url": "https://sns-img.example/sign?token=secret"}],
            comments=[{"content": "有帮助"}],
            available_fields=["title", "body", "author", "images", "comments", "metrics.likes"],
            missing_fields=[],
        )

        outcome = build_capture_outcome(record)

        self.assertEqual(outcome["status_category"], "success")
        self.assertIn("标题", outcome["available_content"])
        self.assertIn("正文", outcome["available_content"])
        self.assertEqual(outcome["missing_content"], [])
        self.assertIn("继续拆解", outcome["recommended_action"])
        self.assertIn("已获取", outcome["user_summary"])

    def test_partial_outcome_keeps_available_content_and_states_limitations(self) -> None:
        record = CaptureRecord(
            id="capture-partial",
            inbox_item_id="inbox-partial",
            source_url="https://www.xiaohongshu.com/explore/partial",
            capture_method="manual",
            capture_status="partial",
            title="标题",
            body="正文",
            content_type="image",
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            images=[{"path": "/tmp/local-image.png"}],
            available_fields=["title", "body", "images"],
            missing_fields=["metrics.likes", "metrics.collects", "metrics.comments", "metrics.shares", "comments"],
        )

        outcome = build_capture_outcome(record)

        self.assertEqual(outcome["status_category"], "partial")
        self.assertIn("标题", outcome["available_content"])
        self.assertIn("互动数据", outcome["missing_content"])
        self.assertIn("无法稳定判断互动表现", outcome["limitations"])
        self.assertIn("不是完整采集", outcome["user_summary"])
        self.assertNotIn("采集成功。", outcome["user_summary"])

    def test_failed_outcome_does_not_become_success_when_non_core_fields_exist(self) -> None:
        record = CaptureRecord(
            id="capture-failed",
            inbox_item_id="inbox-failed",
            source_url="https://www.xiaohongshu.com/explore/failed",
            capture_method="browser_authorized",
            capture_status="failed",
            content_type="unknown",
            author={"name": "可见作者"},
            available_fields=["author"],
            missing_fields=["title", "body", "images", "video"],
            diagnostics={"error_code": "page_unreachable", "page_reachable": False},
        )

        outcome = build_capture_outcome(record)

        self.assertEqual(outcome["status_category"], "failed")
        self.assertIn("确认链接能打开", outcome["recommended_action"])
        self.assertNotIn("采集成功", outcome["user_summary"])

    def test_user_summary_hides_technical_and_sensitive_details(self) -> None:
        record = CaptureRecord(
            id="capture-sensitive",
            inbox_item_id="inbox-sensitive",
            source_url="https://www.xiaohongshu.com/explore/sensitive?xsec_token=secret&track_id=1",
            capture_method="browser_authorized",
            capture_status="failed",
            content_type="unknown",
            missing_fields=["title", "body"],
            warnings=[
                "cdp_connection_failed: Playwright stack trace /Users/lht/project/app.py xsec_token=secret https://sns-img.example/signature?token=secret"
            ],
            diagnostics={
                "error_code": "cdp_connection_failed",
                "error_message": "Playwright stack trace /Users/lht/project/app.py xsec_token=secret",
            },
            raw_snapshot_path="/Users/lht/project/captures/page.html",
        )

        outcome = build_capture_outcome(record)
        summary = outcome["user_summary"]

        self.assertNotIn("CDP", summary.upper())
        self.assertNotIn("Playwright", summary)
        self.assertNotIn("stack trace", summary)
        self.assertNotIn("/Users/", summary)
        self.assertNotIn("xsec_token", summary)
        self.assertNotIn("token=secret", summary)
        self.assertIn("专用 Chrome", outcome["recommended_action"])

    def test_recovery_action_uses_highest_priority_warning(self) -> None:
        record = CaptureRecord(
            id="capture-login",
            inbox_item_id="inbox-login",
            source_url="https://www.xiaohongshu.com/explore/login",
            capture_method="browser_authorized",
            capture_status="failed",
            content_type="unknown",
            missing_fields=["title", "body", "images"],
            warnings=["部分页面字段未采集到。", "login_required: 当前页面需要登录。"],
            diagnostics={"login_required": True, "selectors_failed": ["title", "body"]},
        )

        outcome = build_capture_outcome(record)

        self.assertEqual(outcome["recommended_action"], "在专用 Chrome 中登录后重试。")

    def test_captcha_priority_beats_structure_missing_fields(self) -> None:
        record = CaptureRecord(
            id="capture-captcha",
            inbox_item_id="inbox-captcha",
            source_url="https://www.xiaohongshu.com/explore/captcha",
            capture_method="browser_authorized",
            capture_status="failed",
            content_type="unknown",
            missing_fields=["title", "body"],
            diagnostics={"captcha_detected": True, "selectors_failed": ["title", "body"]},
        )

        outcome = build_capture_outcome(record)

        self.assertEqual(outcome["recommended_action"], "完成人工验证后重试。")

    def test_missing_metrics_are_not_fabricated(self) -> None:
        record = CaptureRecord(
            id="capture-metrics",
            inbox_item_id="inbox-metrics",
            source_url="https://www.xiaohongshu.com/explore/metrics",
            capture_method="manual",
            capture_status="partial",
            title="标题",
            body="正文",
            content_type="image",
            metrics={"likes": None, "collects": None, "comments": None, "shares": None},
            images=[{"path": "screenshot.png"}],
            available_fields=["title", "body", "images"],
            missing_fields=["metrics.likes", "metrics.collects", "metrics.comments", "metrics.shares"],
        )

        outcome = build_capture_outcome(record)

        self.assertIn("互动数据", outcome["missing_content"])
        self.assertNotIn("0", outcome["user_summary"])

    def test_manual_file_invalid_has_plain_recovery_action(self) -> None:
        outcome = build_capture_error_outcome(
            error_code="manual_file_invalid",
            error_message="manual capture file must contain a JSON object",
        )

        self.assertEqual(outcome["status_category"], "failed")
        self.assertEqual(outcome["recommended_action"], "复制标题和正文，或重新提供一份可读取的手动内容。")
        self.assertNotIn("JSON", outcome["user_summary"])

    def test_unknown_fields_do_not_enter_user_facing_summary(self) -> None:
        record = CaptureRecord(
            id="capture-internal-fields",
            inbox_item_id="inbox-internal-fields",
            source_url="https://www.xiaohongshu.com/explore/internal",
            capture_method="browser_authorized",
            capture_status="partial",
            title="可见标题",
            content_type="unknown",
            available_fields=["title", "raw_snapshot_path", "internal_selector", "source_url"],
            missing_fields=["body", "raw_snapshot_path", "internal_selector", "source_url"],
        )

        outcome = build_capture_outcome(record)

        for internal_field in ("raw_snapshot_path", "internal_selector", "source_url"):
            self.assertNotIn(internal_field, outcome["available_content"])
            self.assertNotIn(internal_field, outcome["missing_content"])
            self.assertNotIn(internal_field, outcome["user_summary"])
        self.assertEqual(outcome["technical_details"]["missing_fields"], record.missing_fields)


if __name__ == "__main__":
    unittest.main()
