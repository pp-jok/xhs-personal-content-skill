from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.core import BenchmarkAccount, BenchmarkPost, CreatorProfile, CustomTag, OwnPost, RuleCard
from app.repositories import JsonRepository
from app.workflows import BenchmarkToPublishResult, BenchmarkToPublishWorkflow


@dataclass(frozen=True)
class ValidationStep:
    name: str
    success: bool
    message: str


@dataclass(frozen=True)
class RealSampleValidationResult:
    report_path: Path
    human_review_form_path: Path
    input_counts: dict[str, int]
    generated_counts: dict[str, int]
    steps: list[ValidationStep]
    questions_for_human_review: list[str]
    next_suggestions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_path": str(self.report_path),
            "human_review_form_path": str(self.human_review_form_path),
            "input_counts": self.input_counts,
            "generated_counts": self.generated_counts,
            "steps": [step.__dict__ for step in self.steps],
            "questions_for_human_review": self.questions_for_human_review,
            "next_suggestions": self.next_suggestions,
        }


class RealSampleValidator:
    def __init__(self, workspace: Path | str, prompts_dir: Path | str) -> None:
        self.workspace = Path(workspace)
        self.prompts_dir = Path(prompts_dir)
        self.reports_dir = self.workspace / "reports"
        self.steps: list[ValidationStep] = []

    def run(self) -> RealSampleValidationResult:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        creator = self._load_creator_profile()
        benchmark_accounts = self._load_benchmark_accounts()
        benchmark_posts = self._load_benchmark_posts()
        custom_tags = self._load_custom_tags()
        own_posts = self._load_optional_own_posts()
        weekly_plan = self._load_optional_json("weekly_publish_plan.json")
        validation_feedback = self._load_optional_json("validation_feedback.json")

        planned_publish_time = self._planned_publish_time(weekly_plan)
        workflow_results = [
            self._run_workflow(creator.id, benchmark_post.id, planned_publish_time)
            for benchmark_post in benchmark_posts
        ]
        generated_rule_cards = [rule for result in workflow_results for rule in result.rule_cards]
        generated_topics = [topic for result in workflow_results for topic in result.topics]
        generated_drafts = [result.draft for result in workflow_results if result.draft]
        generated_publish_tasks = [result.publish_task for result in workflow_results if result.publish_task]
        rule_findings = analyze_rule_cards(generated_rule_cards)

        input_counts = {
            "creator_profiles": 1,
            "benchmark_accounts": len(benchmark_accounts),
            "benchmark_posts": len(benchmark_posts),
            "custom_tags": len(custom_tags),
            "own_posts": len(own_posts),
            "weekly_publish_plans": 1 if weekly_plan else 0,
            "validation_feedback_files": 1 if validation_feedback else 0,
        }
        generated_counts = {
            "rule_cards": len(generated_rule_cards),
            "topics": len(generated_topics),
            "content_drafts": len(generated_drafts),
            "publish_tasks": len(generated_publish_tasks),
        }
        questions = default_human_review_questions()
        suggestions = default_next_suggestions(workflow_results, rule_findings)
        report_path = self.reports_dir / "validation_report.md"
        human_review_form_path = self.reports_dir / "human_review_form.md"

        report_path.write_text(
            render_validation_report(input_counts, generated_counts, self.steps, questions, suggestions, rule_findings),
            encoding="utf-8",
        )
        if not human_review_form_path.exists():
            human_review_form_path.write_text(render_human_review_form(), encoding="utf-8")

        return RealSampleValidationResult(
            report_path=report_path,
            human_review_form_path=human_review_form_path,
            input_counts=input_counts,
            generated_counts=generated_counts,
            steps=self.steps,
            questions_for_human_review=questions,
            next_suggestions=suggestions,
        )

    def _load_creator_profile(self) -> CreatorProfile:
        data = self._read_required_json("creator_profile.json")
        creator = CreatorProfile.from_dict(data)
        JsonRepository(self.workspace, CreatorProfile).upsert(creator)
        self._record("读取创作者账号档案", True, f"loaded {creator.id}")
        return creator

    def _load_benchmark_accounts(self) -> list[BenchmarkAccount]:
        items = self._read_required_items("benchmark_account.json")
        repo = JsonRepository(self.workspace, BenchmarkAccount)
        accounts = [repo.upsert(BenchmarkAccount.from_dict(item)) for item in items]
        self._record("读取对标账号", True, f"loaded {len(accounts)} account(s)")
        return accounts

    def _load_benchmark_posts(self) -> list[BenchmarkPost]:
        items = self._read_required_items("benchmark_post.json")
        repo = JsonRepository(self.workspace, BenchmarkPost)
        posts = [repo.upsert(BenchmarkPost.from_dict(item)) for item in items]
        if not posts:
            raise ValueError("benchmark_post.json must contain at least one post")
        self._record("读取对标帖子", True, f"loaded {len(posts)} post(s)")
        return posts

    def _load_custom_tags(self) -> list[CustomTag]:
        items = self._read_required_items("custom_tags.json")
        repo = JsonRepository(self.workspace, CustomTag)
        tags = [repo.upsert(CustomTag.from_dict(item)) for item in items]
        self._record("读取用户标签", True, f"loaded {len(tags)} tag(s)")
        return tags

    def _load_optional_own_posts(self) -> list[OwnPost]:
        path = self.workspace / "own_post.json"
        if not path.exists():
            self._record("读取已发布帖子", True, "optional file not provided")
            return []
        items = self._items_from_json(path)
        repo = JsonRepository(self.workspace, OwnPost)
        posts = [repo.upsert(OwnPost.from_dict(item)) for item in items]
        self._record("读取已发布帖子", True, f"loaded {len(posts)} own post(s)")
        return posts

    def _load_optional_json(self, file_name: str) -> dict[str, Any] | None:
        path = self.workspace / file_name
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f"{file_name} must contain a JSON object")
        return data

    def _run_workflow(
        self,
        creator_profile_id: str,
        benchmark_post_id: str,
        planned_publish_time: str,
    ) -> BenchmarkToPublishResult:
        workflow = BenchmarkToPublishWorkflow(self.workspace, self.prompts_dir)
        result = workflow.run(
            creator_profile_id=creator_profile_id,
            benchmark_post_id=benchmark_post_id,
            planned_publish_time=planned_publish_time,
            topic_count=1,
        )
        self._record("分析对标帖子", True, f"updated {result.benchmark_post.id}")
        self._record("生成规则卡片", True, f"generated {len(result.rule_cards)} rule card(s)")
        self._record("生成选题池", True, f"generated {len(result.topics)} topic(s)")
        self._record("生成内容草稿", True, f"generated {result.draft.id}")
        self._record("创建发布任务", True, f"generated {result.publish_task.id}")
        self._record("输出验证报告", True, "validation report will be written")
        return result

    def _read_required_json(self, file_name: str) -> dict[str, Any]:
        path = self.workspace / file_name
        if not path.exists():
            raise FileNotFoundError(f"Required real sample file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f"{file_name} must contain a JSON object")
        return data

    def _read_required_items(self, file_name: str) -> list[dict[str, Any]]:
        path = self.workspace / file_name
        if not path.exists():
            raise FileNotFoundError(f"Required real sample file not found: {path}")
        return self._items_from_json(path)

    def _items_from_json(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
        raise ValueError(f"{path.name} must contain a JSON object or a list of objects")

    def _planned_publish_time(self, weekly_plan: dict[str, Any] | None) -> str:
        if weekly_plan and isinstance(weekly_plan.get("planned_publish_time"), str):
            return weekly_plan["planned_publish_time"]
        return "2026-07-05T20:00:00+08:00"

    def _record(self, name: str, success: bool, message: str) -> None:
        self.steps.append(ValidationStep(name=name, success=success, message=message))


def render_validation_report(
    input_counts: dict[str, int],
    generated_counts: dict[str, int],
    steps: list[ValidationStep],
    questions: list[str],
    suggestions: list[str],
    rule_findings: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Real Sample Validation Report",
        "",
        "## 输入样本数量",
        "",
    ]
    for key, value in input_counts.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## 生成结果数量", ""])
    for key, value in generated_counts.items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## 步骤状态", ""])
    for step in steps:
        status = "成功" if step.success else "失败"
        lines.append(f"- {step.name}: {status} - {step.message}")

    if rule_findings is not None:
        lines.extend(["", "## 规则合并检查", ""])
        lines.append(f"- 重复规则: {len(rule_findings['duplicate_rule_summaries'])}")
        lines.append(f"- 冲突规则: {len(rule_findings['conflict_rule_types'])}")
        lines.append(f"- 低置信规则: {len(rule_findings['low_confidence_rule_ids'])}")
        if rule_findings["duplicate_rule_summaries"]:
            lines.append(f"- 需要合并的重复规则摘要: {'；'.join(rule_findings['duplicate_rule_summaries'])}")
        if rule_findings["conflict_rule_types"]:
            lines.append(f"- 需要人工判断的冲突类型: {'；'.join(rule_findings['conflict_rule_types'])}")
        if rule_findings["low_confidence_rule_ids"]:
            lines.append(f"- 建议复核的低置信规则: {'；'.join(rule_findings['low_confidence_rule_ids'])}")

    lines.extend(["", "## 需要人工评价的问题", ""])
    for question in questions:
        lines.append(f"- {question}")

    lines.extend(["", "## 下一步建议", ""])
    for suggestion in suggestions:
        lines.append(f"- {suggestion}")

    lines.append("")
    return "\n".join(lines)


def render_human_review_form() -> str:
    return """# Human Review Form

评分方式：

1 = 不可用
2 = 需要大改
3 = 可参考
4 = 小改可用
5 = 可直接使用

| 评价维度 | 评分 1-5 | 备注 |
| --- | --- | --- |
| 选题是否适合账号 |  |  |
| 标题是否可用 |  |  |
| 封面标题是否可用 |  |  |
| 视频逐字稿是否能录 |  |  |
| 是否符合账号风格 |  |  |
| 是否不像 AI |  |  |
| 是否有结果感 |  |  |
| 是否接地气 |  |  |
| 是否比通用内容生成更贴合个人账号 |  |  |
| 是否愿意连续使用 2 周 |  |  |

## 需要进入下一轮迭代的问题

-

## 人工结论

填写是否继续使用、需要修改哪些规则、是否需要补充样本。
"""


def default_human_review_questions() -> list[str]:
    return [
        "选题是否适合账号？",
        "标题是否可用？",
        "封面标题是否可用？",
        "视频逐字稿是否能录？",
        "是否符合账号风格？",
        "是否不像 AI？",
        "是否有结果感？",
        "是否接地气？",
        "是否比通用内容生成更贴合个人账号？",
        "是否愿意连续使用 2 周？",
    ]


def default_next_suggestions(
    results: list[BenchmarkToPublishResult],
    rule_findings: dict[str, Any] | None = None,
) -> list[str]:
    suggestions = [
        "请人工填写 reports/human_review_form.md。",
        "优先检查生成选题是否贴合账号定位。",
        "把评分低于 3 的维度整理进下一轮迭代问题。",
    ]
    if any(result.warnings for result in results):
        suggestions.append("检查 workflow warnings，并补充缺失或低置信样本。")
    if rule_findings and rule_findings["duplicate_rule_summaries"]:
        suggestions.append("合并重复规则，避免后续生成反复套用同一种表达。")
    if rule_findings and rule_findings["conflict_rule_types"]:
        suggestions.append("人工判断冲突规则，明确哪些规则适合当前账号。")
    return suggestions


def analyze_rule_cards(rule_cards: list[RuleCard]) -> dict[str, Any]:
    summary_counts: dict[str, int] = {}
    type_to_summaries: dict[str, set[str]] = {}
    low_confidence_rule_ids: list[str] = []

    for rule in rule_cards:
        summary_counts[rule.rule_summary] = summary_counts.get(rule.rule_summary, 0) + 1
        type_to_summaries.setdefault(rule.type, set()).add(rule.rule_summary)
        if rule.confidence < 0.5:
            low_confidence_rule_ids.append(rule.id)

    return {
        "duplicate_rule_summaries": [summary for summary, count in summary_counts.items() if count > 1],
        "conflict_rule_types": [
            rule_type for rule_type, summaries in type_to_summaries.items() if len(summaries) > 1
        ],
        "low_confidence_rule_ids": low_confidence_rule_ids,
    }
