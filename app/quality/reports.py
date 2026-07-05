from __future__ import annotations

from typing import Any

from app.models.core import ContentQualityReview, RuleCard


def calculate_quality_metrics(reviews: list[ContentQualityReview], rules: list[RuleCard]) -> dict[str, Any]:
    review_count = len(reviews)
    if review_count == 0:
        return {
            "review_count": 0,
            "first_pass_rate": 0.0,
            "average_revision_count": 0.0,
            "major_rewrite_rate": 0.0,
            "average_account_fit_score": 0.0,
            "average_publishability_score": 0.0,
            "title_rewrite_rate": 0.0,
            "script_rewrite_rate": 0.0,
            "rule_hit_rate": 0.0,
            "rule_validation_success_rate": 0.0,
        }

    accepted = sum(len(review.accepted_rules) for review in reviews)
    rejected = sum(len(review.rejected_rules) for review in reviews)
    validation_count = sum(rule.validation_count for rule in rules)
    success_count = sum(rule.success_count for rule in rules)

    return {
        "review_count": review_count,
        "first_pass_rate": round(
            sum(1 for review in reviews if review.revision_count == 0 and not review.major_rewrite_required) / review_count,
            2,
        ),
        "average_revision_count": round(sum(review.revision_count for review in reviews) / review_count, 2),
        "major_rewrite_rate": round(sum(1 for review in reviews if review.major_rewrite_required) / review_count, 2),
        "average_account_fit_score": round(sum(review.account_fit_score for review in reviews) / review_count, 2),
        "average_publishability_score": round(sum(review.publishability_score for review in reviews) / review_count, 2),
        "title_rewrite_rate": round(sum(1 for review in reviews if has_issue_area(review, "title")) / review_count, 2),
        "script_rewrite_rate": round(sum(1 for review in reviews if has_issue_area(review, "script")) / review_count, 2),
        "rule_hit_rate": round(accepted / (accepted + rejected), 2) if accepted + rejected else 0.0,
        "rule_validation_success_rate": round(success_count / validation_count, 2) if validation_count else 0.0,
    }


def build_quality_report(period: str, reviews: list[ContentQualityReview], rules: list[RuleCard]) -> tuple[dict[str, Any], str]:
    metrics = calculate_quality_metrics(reviews, rules)
    report = render_quality_report(period, metrics, reviews, rules)
    return metrics, report


def render_quality_report(
    period: str,
    metrics: dict[str, Any],
    reviews: list[ContentQualityReview],
    rules: list[RuleCard],
) -> str:
    validated_rules = [rule for rule in rules if rule.status == "validated" or rule.strength == "strong"]
    weak_rules = [rule for rule in rules if rule.failure_count > rule.success_count and rule.validation_count > 0]
    rejected_title_patterns = collect_issue_actions(reviews, "title")
    rejected_script_patterns = collect_issue_actions(reviews, "script")

    lines = [
        f"# Quality Report - {period}",
        "",
        "## 核心质量指标",
        "",
        f"- 评价数量: {metrics['review_count']}",
        f"- 一次通过率: {metrics['first_pass_rate']}",
        f"- 平均修改轮次: {metrics['average_revision_count']}",
        f"- 大改率: {metrics['major_rewrite_rate']}",
        f"- 平均账号贴合度: {metrics['average_account_fit_score']}",
        f"- 平均可发布率: {metrics['average_publishability_score']}",
        f"- 标题重写率: {metrics['title_rewrite_rate']}",
        f"- 脚本重写率: {metrics['script_rewrite_rate']}",
        f"- 规则命中率: {metrics['rule_hit_rate']}",
        f"- 规则验证成功率: {metrics['rule_validation_success_rate']}",
        "",
        "## 本周期新增或有效规则",
        "",
    ]
    if validated_rules:
        lines.extend(f"- {rule.id}: {rule.rule_summary}" for rule in validated_rules)
    else:
        lines.append("- 暂无已验证或强规则。")

    lines.extend(["", "## 表现差的规则", ""])
    if weak_rules:
        lines.extend(f"- {rule.id}: {rule.rule_summary}" for rule in weak_rules)
    else:
        lines.append("- 暂无明确表现差的规则。")

    lines.extend(["", "## 被重复否定的标题 / 脚本模式", ""])
    lines.append(f"- 标题: {', '.join(rejected_title_patterns) if rejected_title_patterns else '暂无'}")
    lines.append(f"- 脚本: {', '.join(rejected_script_patterns) if rejected_script_patterns else '暂无'}")

    lines.extend(["", "## 修改成本判断", ""])
    if metrics["average_revision_count"] <= 1 and metrics["major_rewrite_rate"] < 0.5:
        lines.append("- 修改成本较低，可继续扩大样本验证。")
    else:
        lines.append("- 修改成本仍偏高，下一周优先补充低分草稿对应的对标样本和负反馈。")

    lines.extend(["", "## 下一周建议", ""])
    lines.append("- 补充评分低于 3 的标题、封面或脚本案例。")
    lines.append("- 对表现差的规则做拒绝、废弃或改写。")
    lines.append("- 优先复用已验证或强规则生成下一批草稿。")
    return "\n".join(lines) + "\n"


def has_issue_area(review: ContentQualityReview, area: str) -> bool:
    for issue in review.issues:
        if str(issue.get("area", "")).lower() == area:
            return True
        action = str(issue.get("action", "")).lower()
        if area in action:
            return True
    return False


def collect_issue_actions(reviews: list[ContentQualityReview], area: str) -> list[str]:
    actions: list[str] = []
    for review in reviews:
        for issue in review.issues:
            if str(issue.get("area", "")).lower() == area:
                action = str(issue.get("action") or issue.get("problem") or "").strip()
                if action and action not in actions:
                    actions.append(action)
    return actions
