from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from app.generation.context import GenerationContext
from app.models.core import TopicItem


class TopicGenerationError(ValueError):
    """Raised when topic generation cannot safely produce TopicItem records."""


@dataclass(frozen=True)
class TopicGenerationResult:
    context_status: str
    topics: list[TopicItem]
    warnings: list[str]
    user_summary: str
    machine_summary: dict[str, object]


def generate_topics_from_context(*, context: GenerationContext, topic_count: int) -> TopicGenerationResult:
    validate_topic_count(topic_count)
    if not context.usable_rules:
        raise TopicGenerationError("当前没有可用规则，请先确认至少一条可用于生成的规则。")

    machine_context = context.machine_summary
    profile_id = string_value(machine_context.get("profile_id"))
    profile_version = int_or_none(machine_context.get("profile_version"))
    constraints = dict_value(machine_context.get("task_constraints"))
    usable_rules = list(context.usable_rules)
    risk_warnings = text_list(machine_context.get("risk_warnings"))
    missing_information = text_list(machine_context.get("missing_information"))
    reference_ids = text_list(constraints.get("reference_ids"))
    content_format = first_text(
        [
            string_value(constraints.get("content_format")),
            *text_list(context.profile.get("content_formats")),
            "图文",
        ]
    )

    topics = [
        build_topic(
            context=context,
            index=index,
            profile_id=profile_id,
            profile_version=profile_version,
            constraints=constraints,
            usable_rules=usable_rules,
            risk_warnings=risk_warnings,
            missing_information=missing_information,
            reference_ids=reference_ids,
            content_format=content_format,
        )
        for index in range(1, topic_count + 1)
    ]
    seen_titles: set[str] = set()
    for topic in topics:
        if topic.title in seen_titles:
            raise TopicGenerationError("生成的选题标题重复，请减少选题数量或补充任务约束。")
        seen_titles.add(topic.title)

    warnings = []
    if context.status_category == "limited":
        warnings.append("当前上下文有信息限制")
    warnings.extend(missing_information)

    topic_ids = [topic.id for topic in topics]
    machine_summary = {
        "profile_id": profile_id,
        "profile_version": profile_version,
        "context_status": context.status_category,
        "topic_ids": topic_ids,
        "topic_count": len(topics),
        "usable_rule_ids": [string_value(item.get("rule_id")) for item in usable_rules if string_value(item.get("rule_id"))],
        "excluded_rule_ids": text_list(machine_context.get("excluded_rule_ids")),
        "task_constraints": constraints,
        "risk_warnings": risk_warnings,
        "missing_information": missing_information,
    }
    return TopicGenerationResult(
        context_status=context.status_category,
        topics=topics,
        warnings=unique_texts(warnings),
        user_summary=build_user_summary(context, topics, warnings),
        machine_summary=machine_summary,
    )


def validate_topic_count(topic_count: int) -> None:
    if not isinstance(topic_count, int) or topic_count < 1 or topic_count > 10:
        raise TopicGenerationError("选题数量必须是 1 到 10 之间的整数。")


def build_topic(
    *,
    context: GenerationContext,
    index: int,
    profile_id: str,
    profile_version: int | None,
    constraints: dict[str, object],
    usable_rules: list[dict[str, object]],
    risk_warnings: list[str],
    missing_information: list[str],
    reference_ids: list[str],
    content_format: str,
) -> TopicItem:
    rule = usable_rules[(index - 1) % len(usable_rules)]
    profile_name = profile_name_for(context)
    positioning = string_value(context.profile.get("positioning")) or "当前账号定位"
    audience = first_text(text_list(constraints.get("target_audiences")) + text_list(context.profile.get("target_audience")) + ["目标用户"])
    topic_area = first_text([string_value(constraints.get("topic_area")), string_value(constraints.get("intent")), positioning])
    content_type = first_text([string_value(constraints.get("content_type")), content_format])
    rule_summary = string_value(rule.get("summary")) or "已确认规则"
    rule_type = string_value(rule.get("rule_type")) or "topic"
    title = f"{topic_area}：给{audience}的{content_type}选题 {index}"
    content_goal = f"面向{audience}，围绕{topic_area}提供可执行内容。"
    reason = f"基于账号「{profile_name}」的定位，使用规则「{rule_summary}」，用于{content_goal}"
    topic_id = stable_topic_id(profile_id, profile_version, title, index)
    return TopicItem(
        id=topic_id,
        title=title,
        content_goal=content_goal,
        content_format=content_format,
        source_rule_cards=[string_value(item.get("rule_id")) for item in usable_rules if string_value(item.get("rule_id"))],
        reference_posts=reference_ids,
        reason=reason,
        status="idea",
        tags=unique_texts([topic_area, content_type, audience, rule_type]),
        source_profile_id=profile_id,
        source_profile_version=profile_version,
        generation_context_status=context.status_category,
        task_constraints=constraints,
        risk_warnings=risk_warnings,
        missing_information=missing_information,
        created_by="codex",
    )


def build_user_summary(context: GenerationContext, topics: list[TopicItem], warnings: list[str]) -> str:
    profile_name = profile_name_for(context)
    status_text = "可直接使用" if context.status_category == "ready" else "可使用但有限制"
    lines = [
        f"已为「{profile_name}」生成 {len(topics)} 个选题。",
        f"上下文状态：{status_text}。",
    ]
    if warnings:
        lines.append("限制与风险：" + "；".join(unique_texts(warnings)))
    lines.append("选题列表：")
    for index, topic in enumerate(topics, start=1):
        lines.append(f"{index}. {topic.title}")
        lines.append(f"   理由：{topic.reason}")
    lines.append("下一步：选择一个选题进入草稿生成。")
    return "\n".join(lines)


def stable_topic_id(profile_id: str, profile_version: int | None, title: str, index: int) -> str:
    digest = sha1(f"{profile_id}:{profile_version}:{title}:{index}".encode("utf-8")).hexdigest()[:12]
    return f"topic-{digest}"


def profile_name_for(context: GenerationContext) -> str:
    return string_value(context.profile.get("profile_name")) or string_value(context.profile.get("name")) or "当前账号"


def first_text(values: list[str]) -> str:
    for value in values:
        if value.strip():
            return value.strip()
    return ""


def string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 1 else None


def dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def unique_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result
