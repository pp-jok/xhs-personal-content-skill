from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.core import BenchmarkAccount, BenchmarkPost, CreatorProfile, CustomTag, OwnPost
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
        workflow_result = self._run_workflow(creator.id, benchmark_posts[0].id, planned_publish_time)

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
            "rule_cards": len(workflow_result.rule_cards),
            "topics": len(workflow_result.topics),
            "content_drafts": 1 if workflow_result.draft else 0,
            "publish_tasks": 1 if workflow_result.publish_task else 0,
        }
        questions = default_human_review_questions()
        suggestions = default_next_suggestions(workflow_result)
        report_path = self.reports_dir / "validation_report.md"
        human_review_form_path = self.reports_dir / "human_review_form.md"

        report_path.write_text(
            render_validation_report(input_counts, generated_counts, self.steps, questions, suggestions),
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


def default_next_suggestions(result: BenchmarkToPublishResult) -> list[str]:
    suggestions = [
        "请人工填写 reports/human_review_form.md。",
        "优先检查生成选题是否贴合账号定位。",
        "把评分低于 3 的维度整理进下一轮迭代问题。",
    ]
    if result.warnings:
        suggestions.append("检查 workflow warnings，并补充缺失或低置信样本。")
    return suggestions
