from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Any

from app.models.core import ContentDraft, TopicItem, ValidationError


class DraftGenerationError(ValueError):
    """Raised when a draft cannot be generated from auditable local input."""


@dataclass(frozen=True)
class DraftGenerationResult:
    draft: ContentDraft
    warnings: list[str]
    user_summary: str
    machine_summary: dict[str, object]


@dataclass(frozen=True)
class DraftRevisionResult:
    draft: ContentDraft
    warnings: list[str]
    user_summary: str
    machine_summary: dict[str, object]


def generate_draft_from_topic(*, topic: TopicItem) -> DraftGenerationResult:
    if not isinstance(topic, TopicItem):
        raise DraftGenerationError("选题数据不可用：必须提供 TopicItem。")
    try:
        topic.validate()
    except ValidationError as exc:
        raise DraftGenerationError(f"选题数据不可用：{exc}") from exc

    diagnosis = build_diagnosis(
        risk_warnings=topic.risk_warnings,
        missing_information=topic.missing_information,
        revision_hint="开头更直接",
    )
    title = topic.title.strip()
    draft = ContentDraft(
        id=stable_draft_id(topic.id),
        topic_id=topic.id,
        titles=[
            title,
            f"{title}：照着做的版本",
        ],
        cover_titles=[cover_title_for(topic), "照着做清单"],
        script=script_for_topic(topic),
        shot_suggestions=shot_suggestions_for(topic),
        status="draft",
        quality_review={
            "account_fit": "基于已选选题和审计字段生成，仍需人工确认口吻。",
            "risk": "请优先检查风险和缺失信息。",
        },
        tags=unique_texts([*topic.tags, "草稿"]),
        source_profile_id=topic.source_profile_id,
        source_profile_version=topic.source_profile_version,
        source_rule_cards=list(topic.source_rule_cards),
        generation_context_status=topic.generation_context_status,
        task_constraints=dict(topic.task_constraints),
        risk_warnings=list(topic.risk_warnings),
        missing_information=list(topic.missing_information),
        diagnosis=diagnosis,
        created_by="codex",
    )
    draft.validate()
    warnings = unique_texts([*topic.risk_warnings, *topic.missing_information])
    return DraftGenerationResult(
        draft=draft,
        warnings=warnings,
        user_summary=build_generate_user_summary(topic=topic, draft=draft, warnings=warnings),
        machine_summary=machine_summary_for(draft),
    )


def revise_draft_with_focus(*, draft: ContentDraft, focus: str) -> DraftRevisionResult:
    if not isinstance(draft, ContentDraft):
        raise DraftGenerationError("草稿数据不可用：必须提供 ContentDraft。")
    try:
        draft.validate()
    except ValidationError as exc:
        raise DraftGenerationError(f"草稿数据不可用：{exc}") from exc

    cleaned_focus = focus.strip() if isinstance(focus, str) else ""
    if not cleaned_focus:
        raise DraftGenerationError("revision focus 不能为空。")

    diagnosis = build_diagnosis(
        risk_warnings=draft.risk_warnings,
        missing_information=draft.missing_information,
        revision_hint=cleaned_focus,
        revised=True,
    )
    revised = ContentDraft(
        id=stable_revision_id(draft.id, cleaned_focus),
        topic_id=draft.topic_id,
        titles=revise_titles(draft.titles, cleaned_focus),
        cover_titles=list(draft.cover_titles),
        script=revise_script(draft.script, cleaned_focus),
        shot_suggestions=unique_texts([*draft.shot_suggestions, f"围绕“{cleaned_focus}”检查一遍。"]),
        status="draft",
        quality_review={
            **dict(draft.quality_review),
            "revision": f"本次只聚焦：{cleaned_focus}",
        },
        tags=list(draft.tags),
        source_profile_id=draft.source_profile_id,
        source_profile_version=draft.source_profile_version,
        source_rule_cards=list(draft.source_rule_cards),
        generation_context_status=draft.generation_context_status,
        task_constraints=dict(draft.task_constraints),
        risk_warnings=list(draft.risk_warnings),
        missing_information=list(draft.missing_information),
        parent_draft_id=draft.id,
        revision_focus=cleaned_focus,
        diagnosis=diagnosis,
        created_by="codex",
    )
    revised.validate()
    warnings = unique_texts([*draft.risk_warnings, *draft.missing_information])
    return DraftRevisionResult(
        draft=revised,
        warnings=warnings,
        user_summary=build_revision_user_summary(draft=draft, revised=revised, focus=cleaned_focus),
        machine_summary=machine_summary_for(revised),
    )


def build_diagnosis(
    *,
    risk_warnings: list[str],
    missing_information: list[str],
    revision_hint: str,
    revised: bool = False,
) -> dict[str, object]:
    issues = unique_texts([*missing_information, *risk_warnings])[:3]
    if not issues:
        issues = ["需要人工确认标题、封面和正文是否符合账号口吻。"]
    strengths = ["选题对象和内容目标清晰。"]
    if revised:
        strengths.append("已围绕单一修订重点调整。")
    return {
        "strengths": strengths,
        "issues": issues,
        "suggested_revision_focuses": unique_texts([revision_hint, "语气更符合账号", "降低夸大表达"])[:3],
    }


def script_for_topic(topic: TopicItem) -> str:
    constraints = dict(topic.task_constraints)
    topic_area = string_value(constraints.get("topic_area")) or topic.title
    content_type = string_value(constraints.get("content_type")) or topic.content_format
    risk_line = "；".join(unique_texts([*topic.risk_warnings, *topic.missing_information])) or "保持真实具体，不夸大结果。"
    return (
        f"开头：直接点明“{topic.title}”这个场景。\n"
        f"主体：围绕{topic.content_goal}，拆成 3 个可以当天执行的小步骤。\n"
        f"结构：先说对象，再说问题，再给清单式行动。\n"
        f"形式：按{content_type}表达，重点放在{topic_area}。\n"
        f"收尾：提醒用户根据自己的情况记录反馈。\n"
        f"风险提醒：{risk_line}"
    )


def cover_title_for(topic: TopicItem) -> str:
    cleaned = topic.title.replace("：", " ").strip()
    return cleaned[:18] if len(cleaned) > 18 else cleaned


def shot_suggestions_for(topic: TopicItem) -> list[str]:
    if topic.content_format == "视频":
        return ["开头口播点明场景", "中段展示三步行动", "结尾展示记录反馈"]
    return ["首图点明目标人群", "中页列三步行动", "末页提醒风险和反馈"]


def revise_titles(titles: list[str], focus: str) -> list[str]:
    base = titles[0] if titles else "修订草稿"
    if focus not in base:
        return [f"{base}｜{focus}", *titles[1:]]
    return list(titles)


def revise_script(script: str, focus: str) -> str:
    return f"本次修订重点：{focus}。\n保留原核心主题，只调整这一处。\n{script}"


def machine_summary_for(draft: ContentDraft) -> dict[str, object]:
    return {
        "draft_id": draft.id,
        "topic_id": draft.topic_id,
        "source_profile_id": draft.source_profile_id,
        "source_profile_version": draft.source_profile_version,
        "source_rule_cards": list(draft.source_rule_cards),
        "generation_context_status": draft.generation_context_status,
        "task_constraints": dict(draft.task_constraints),
        "risk_warnings": list(draft.risk_warnings),
        "missing_information": list(draft.missing_information),
        "diagnosis": dict(draft.diagnosis),
        "parent_draft_id": draft.parent_draft_id,
        "revision_focus": draft.revision_focus,
    }


def build_generate_user_summary(*, topic: TopicItem, draft: ContentDraft, warnings: list[str]) -> str:
    lines = [
        "已生成 1 个草稿。",
        f"基于选题：{topic.title}",
        f"草稿标题：{draft.titles[0]}",
        "核心结构：开头点明场景，主体给出三步行动，结尾提醒记录反馈。",
    ]
    if warnings:
        lines.append("主要风险/缺失提醒：" + "；".join(warnings))
    lines.append("简短诊断：" + diagnosis_text(draft.diagnosis))
    lines.append("建议选择一个 revision focus，例如：" + "、".join(text_list(draft.diagnosis.get("suggested_revision_focuses"))))
    lines.append("下一步：执行 revise-draft，或人工确认后继续进入发布流程。")
    return "\n".join(lines)


def build_revision_user_summary(*, draft: ContentDraft, revised: ContentDraft, focus: str) -> str:
    return "\n".join(
        [
            "已生成 1 个修订草稿。",
            f"本次修订重点：{focus}",
            "保留了原草稿的选题、账号审计信息和核心主题。",
            f"改了：围绕“{focus}”调整标题或正文表达。",
            "原草稿仍保留，未被覆盖。",
            "下一步：人工检查修订稿，确认后再进入发布任务。",
        ]
    )


def diagnosis_text(diagnosis: dict[str, Any]) -> str:
    strengths = text_list(diagnosis.get("strengths"))
    issues = text_list(diagnosis.get("issues"))
    return f"优势：{'；'.join(strengths)}。待改进：{'；'.join(issues)}。"


def stable_draft_id(topic_id: str) -> str:
    digest = sha1(topic_id.encode("utf-8")).hexdigest()[:12]
    return f"draft-from-{digest}"


def stable_revision_id(draft_id: str, focus: str) -> str:
    digest = sha1(f"{draft_id}:{focus}".encode("utf-8")).hexdigest()[:12]
    return f"draft-revision-{digest}"


def string_value(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


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
