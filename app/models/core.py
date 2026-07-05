from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, ClassVar, Literal, TypeVar, get_args


ModelT = TypeVar("ModelT", bound="BaseModel")

TagScope = Literal[
    "benchmark_account",
    "benchmark_post",
    "rule_card",
    "topic_item",
    "content_draft",
    "publish_task",
    "own_post",
]

TagType = Literal["preference", "usage", "goal", "risk", "source", "custom"]
RuleType = Literal["title", "structure", "topic", "cover", "script", "operation"]
ContentStatus = Literal["idea", "draft", "reviewing", "ready", "archived"]
PublishStatus = Literal["planned", "preparing", "ready", "published", "cancelled"]
InboxStatus = Literal["inbox", "capturing", "captured", "analyzed", "promoted_to_benchmark", "rejected", "archived"]
CaptureStatus = Literal["pending", "success", "partial", "failed"]
CaptureMethod = Literal["manual", "browser_authorized"]
CapturedContentType = Literal["unknown", "image", "video", "mixed"]
AnalysisTemplate = Literal[
    "video_tutorial",
    "video_personal_story",
    "video_review",
    "image_carousel_tutorial",
    "image_carousel_experience",
    "case_study",
    "listicle",
]


class ValidationError(ValueError):
    """Raised when model data does not satisfy the project contract."""


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")


def require_list(value: list[Any], field_name: str) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{field_name} must be a list")


def require_dict(value: dict[str, Any], field_name: str) -> None:
    if not isinstance(value, dict):
        raise ValidationError(f"{field_name} must be an object")


def require_literal(value: str, allowed_type: Any, field_name: str) -> None:
    allowed = get_args(allowed_type)
    if value not in allowed:
        joined = ", ".join(allowed)
        raise ValidationError(f"{field_name} must be one of: {joined}")


def ensure_list_items_are_text(value: list[Any], field_name: str) -> None:
    require_list(value, field_name)
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(f"{field_name} must contain only non-empty strings")


def ensure_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string or null")


@dataclass
class BaseModel:
    id: str
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    missing_fields: list[str] = field(default_factory=list)
    confidence: float = 1.0
    source_type: str = ""
    source_note: str = ""
    user_reason: str = ""
    created_from: str = ""

    collection_name: ClassVar[str]

    def __post_init__(self) -> None:
        require_text(self.id, "id")
        require_text(self.created_at, "created_at")
        require_text(self.updated_at, "updated_at")
        ensure_list_items_are_text(self.missing_fields, "missing_fields")
        if not isinstance(self.confidence, (int, float)) or not 0 <= float(self.confidence) <= 1:
            raise ValidationError("confidence must be a number from 0 to 1")
        ensure_optional_text(self.source_type, "source_type")
        ensure_optional_text(self.source_note, "source_note")
        ensure_optional_text(self.user_reason, "user_reason")
        ensure_optional_text(self.created_from, "created_from")
        self.validate()

    def validate(self) -> None:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls: type[ModelT], data: dict[str, Any]) -> ModelT:
        require_dict(data, cls.__name__)
        field_names = {item.name for item in fields(cls)}
        filtered = {key: value for key, value in data.items() if key in field_names}
        missing = [
            item.name
            for item in fields(cls)
            if item.default is MISSING
            and item.default_factory is MISSING
            and item.name not in filtered
        ]
        if missing:
            raise ValidationError(f"Missing required fields: {', '.join(missing)}")
        return cls(**filtered)


@dataclass
class CreatorProfile(BaseModel):
    collection_name: ClassVar[str] = "creator-profiles"

    name: str = ""
    platform: str = "小红书"
    positioning: str = ""
    target_audience: list[str] = field(default_factory=list)
    content_style: list[str] = field(default_factory=list)
    forbidden_expressions: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    content_formats: list[str] = field(default_factory=list)
    publish_frequency: str = ""
    notes: str = ""

    def validate(self) -> None:
        require_text(self.name, "name")
        require_text(self.platform, "platform")
        require_text(self.positioning, "positioning")
        ensure_list_items_are_text(self.target_audience, "target_audience")
        ensure_list_items_are_text(self.content_style, "content_style")
        ensure_list_items_are_text(self.forbidden_expressions, "forbidden_expressions")
        ensure_list_items_are_text(self.goals, "goals")
        ensure_list_items_are_text(self.content_formats, "content_formats")
        require_text(self.publish_frequency, "publish_frequency")
        require_text(self.notes, "notes")


@dataclass
class BenchmarkAccount(BaseModel):
    collection_name: ClassVar[str] = "benchmark-accounts"

    name: str = ""
    url: str = ""
    niche: str = ""
    reason_to_follow: str = ""
    learnable_points: list[str] = field(default_factory=list)
    non_learnable_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""

    def validate(self) -> None:
        require_text(self.name, "name")
        ensure_optional_text(self.url, "url")
        require_text(self.niche, "niche")
        require_text(self.reason_to_follow, "reason_to_follow")
        ensure_list_items_are_text(self.learnable_points, "learnable_points")
        ensure_list_items_are_text(self.non_learnable_points, "non_learnable_points")
        ensure_list_items_are_text(self.tags, "tags")
        require_text(self.summary, "summary")


@dataclass
class BenchmarkPost(BaseModel):
    collection_name: ClassVar[str] = "benchmark-posts"

    account_id: str = ""
    title: str = ""
    url: str = ""
    content_type: str = ""
    cover_text: str = ""
    raw_content: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    ai_analysis: dict[str, Any] = field(default_factory=dict)
    borrowable_points: list[str] = field(default_factory=list)
    non_borrowable_points: list[str] = field(default_factory=list)
    rule_card_candidates: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.account_id, "account_id")
        require_text(self.title, "title")
        ensure_optional_text(self.url, "url")
        require_text(self.content_type, "content_type")
        ensure_optional_text(self.cover_text, "cover_text")
        require_text(self.raw_content, "raw_content")
        require_dict(self.metrics, "metrics")
        ensure_list_items_are_text(self.tags, "tags")
        require_dict(self.ai_analysis, "ai_analysis")
        ensure_list_items_are_text(self.borrowable_points, "borrowable_points")
        ensure_list_items_are_text(self.non_borrowable_points, "non_borrowable_points")
        require_list(self.rule_card_candidates, "rule_card_candidates")
        for candidate in self.rule_card_candidates:
            require_dict(candidate, "rule_card_candidates item")


@dataclass
class ContentInboxItem(BaseModel):
    collection_name: ClassVar[str] = "content-inbox"

    source_url: str = ""
    source_platform: str = "xiaohongshu"
    status: InboxStatus = "inbox"
    capture_status: CaptureStatus = "pending"
    content_type: CapturedContentType = "unknown"
    user_intent: str = ""
    requested_focus: list[str] = field(default_factory=list)
    captured_at: str | None = None
    warnings: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.source_url, "source_url")
        require_text(self.source_platform, "source_platform")
        if self.source_platform != "xiaohongshu":
            raise ValidationError("source_platform must be xiaohongshu")
        require_literal(self.status, InboxStatus, "status")
        require_literal(self.capture_status, CaptureStatus, "capture_status")
        require_literal(self.content_type, CapturedContentType, "content_type")
        ensure_optional_text(self.user_intent, "user_intent")
        ensure_list_items_are_text(self.requested_focus, "requested_focus")
        ensure_optional_text(self.captured_at, "captured_at")
        ensure_list_items_are_text(self.warnings, "warnings")


@dataclass
class CaptureRecord(BaseModel):
    collection_name: ClassVar[str] = "capture-records"

    inbox_item_id: str = ""
    source_url: str = ""
    capture_method: CaptureMethod = "manual"
    capture_status: CaptureStatus = "partial"
    captured_at: str = field(default_factory=now_iso)
    title: str = ""
    body: str = ""
    content_type: CapturedContentType = "unknown"
    author: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)
    video: dict[str, Any] = field(default_factory=dict)
    comments: list[dict[str, Any]] = field(default_factory=list)
    available_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_snapshot_path: str = ""

    def validate(self) -> None:
        require_text(self.inbox_item_id, "inbox_item_id")
        require_text(self.source_url, "source_url")
        require_literal(self.capture_method, CaptureMethod, "capture_method")
        require_literal(self.capture_status, CaptureStatus, "capture_status")
        require_text(self.captured_at, "captured_at")
        ensure_optional_text(self.title, "title")
        ensure_optional_text(self.body, "body")
        require_literal(self.content_type, CapturedContentType, "content_type")
        require_dict(self.author, "author")
        require_dict(self.metrics, "metrics")
        require_list(self.images, "images")
        for image in self.images:
            require_dict(image, "images item")
        require_dict(self.video, "video")
        require_list(self.comments, "comments")
        for comment in self.comments:
            require_dict(comment, "comments item")
        ensure_list_items_are_text(self.available_fields, "available_fields")
        ensure_list_items_are_text(self.warnings, "warnings")
        ensure_optional_text(self.raw_snapshot_path, "raw_snapshot_path")


@dataclass
class BenchmarkAnalysis(BaseModel):
    collection_name: ClassVar[str] = "benchmark-analyses"

    benchmark_post_id: str = ""
    capture_id: str = ""
    analysis_template: AnalysisTemplate = "image_carousel_tutorial"
    observable_facts: dict[str, Any] = field(default_factory=dict)
    topic_analysis: dict[str, Any] = field(default_factory=dict)
    title_analysis: dict[str, Any] = field(default_factory=dict)
    cover_analysis: dict[str, Any] = field(default_factory=dict)
    structure_analysis: dict[str, Any] = field(default_factory=dict)
    visual_analysis: dict[str, Any] = field(default_factory=dict)
    audio_analysis: dict[str, Any] = field(default_factory=dict)
    comment_analysis: dict[str, Any] = field(default_factory=dict)
    engagement_analysis: dict[str, Any] = field(default_factory=dict)
    account_fit: dict[str, Any] = field(default_factory=dict)
    transferable_elements: list[str] = field(default_factory=list)
    non_transferable_elements: list[str] = field(default_factory=list)
    candidate_rule_ids: list[str] = field(default_factory=list)
    derived_topic_ids: list[str] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)

    def validate(self) -> None:
        ensure_optional_text(self.benchmark_post_id, "benchmark_post_id")
        require_text(self.capture_id, "capture_id")
        require_literal(self.analysis_template, AnalysisTemplate, "analysis_template")
        require_dict(self.observable_facts, "observable_facts")
        require_dict(self.topic_analysis, "topic_analysis")
        require_dict(self.title_analysis, "title_analysis")
        require_dict(self.cover_analysis, "cover_analysis")
        require_dict(self.structure_analysis, "structure_analysis")
        require_dict(self.visual_analysis, "visual_analysis")
        require_dict(self.audio_analysis, "audio_analysis")
        require_dict(self.comment_analysis, "comment_analysis")
        require_dict(self.engagement_analysis, "engagement_analysis")
        require_dict(self.account_fit, "account_fit")
        ensure_list_items_are_text(self.transferable_elements, "transferable_elements")
        ensure_list_items_are_text(self.non_transferable_elements, "non_transferable_elements")
        ensure_list_items_are_text(self.candidate_rule_ids, "candidate_rule_ids")
        ensure_list_items_are_text(self.derived_topic_ids, "derived_topic_ids")
        ensure_list_items_are_text(self.uncertainties, "uncertainties")


@dataclass
class CustomTag(BaseModel):
    collection_name: ClassVar[str] = "custom-tags"

    name: str = ""
    type: TagType = "custom"
    description: str = ""
    scope: list[TagScope] = field(default_factory=list)
    weight: int = 1

    def validate(self) -> None:
        require_text(self.name, "name")
        require_literal(self.type, TagType, "type")
        require_text(self.description, "description")
        require_list(self.scope, "scope")
        for item in self.scope:
            require_literal(item, TagScope, "scope item")
        if not isinstance(self.weight, int) or not 1 <= self.weight <= 5:
            raise ValidationError("weight must be an integer from 1 to 5")


@dataclass
class RuleCard(BaseModel):
    collection_name: ClassVar[str] = "rule-cards"

    name: str = ""
    type: RuleType = "topic"
    source_ids: list[str] = field(default_factory=list)
    applicable_scenarios: list[str] = field(default_factory=list)
    rule_summary: str = ""
    examples: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    adaptation_notes: str = ""
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.name, "name")
        require_literal(self.type, RuleType, "type")
        ensure_list_items_are_text(self.source_ids, "source_ids")
        ensure_list_items_are_text(self.applicable_scenarios, "applicable_scenarios")
        require_text(self.rule_summary, "rule_summary")
        ensure_list_items_are_text(self.examples, "examples")
        ensure_list_items_are_text(self.risks, "risks")
        require_text(self.adaptation_notes, "adaptation_notes")
        ensure_list_items_are_text(self.tags, "tags")


@dataclass
class TopicItem(BaseModel):
    collection_name: ClassVar[str] = "topic-pool"

    title: str = ""
    content_goal: str = ""
    content_format: str = ""
    source_rule_cards: list[str] = field(default_factory=list)
    reference_posts: list[str] = field(default_factory=list)
    reason: str = ""
    status: ContentStatus = "idea"
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.title, "title")
        require_text(self.content_goal, "content_goal")
        require_text(self.content_format, "content_format")
        ensure_list_items_are_text(self.source_rule_cards, "source_rule_cards")
        ensure_list_items_are_text(self.reference_posts, "reference_posts")
        require_text(self.reason, "reason")
        require_literal(self.status, ContentStatus, "status")
        ensure_list_items_are_text(self.tags, "tags")


@dataclass
class ContentDraft(BaseModel):
    collection_name: ClassVar[str] = "content-drafts"

    topic_id: str = ""
    titles: list[str] = field(default_factory=list)
    cover_titles: list[str] = field(default_factory=list)
    script: str = ""
    shot_suggestions: list[str] = field(default_factory=list)
    status: ContentStatus = "draft"
    quality_review: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.topic_id, "topic_id")
        ensure_list_items_are_text(self.titles, "titles")
        ensure_list_items_are_text(self.cover_titles, "cover_titles")
        require_text(self.script, "script")
        ensure_list_items_are_text(self.shot_suggestions, "shot_suggestions")
        require_literal(self.status, ContentStatus, "status")
        require_dict(self.quality_review, "quality_review")
        ensure_list_items_are_text(self.tags, "tags")


@dataclass
class PublishTask(BaseModel):
    collection_name: ClassVar[str] = "publish-tasks"

    account_id: str = ""
    draft_id: str = ""
    planned_publish_time: str = ""
    content_goal: str = ""
    status: PublishStatus = "planned"
    materials_needed: list[str] = field(default_factory=list)
    result_metrics: dict[str, Any] = field(default_factory=dict)
    review_summary: str = ""
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.account_id, "account_id")
        require_text(self.draft_id, "draft_id")
        require_text(self.planned_publish_time, "planned_publish_time")
        require_text(self.content_goal, "content_goal")
        require_literal(self.status, PublishStatus, "status")
        ensure_list_items_are_text(self.materials_needed, "materials_needed")
        require_dict(self.result_metrics, "result_metrics")
        ensure_optional_text(self.review_summary, "review_summary")
        ensure_list_items_are_text(self.tags, "tags")


@dataclass
class OwnPost(BaseModel):
    collection_name: ClassVar[str] = "own-posts"

    account_id: str = ""
    title: str = ""
    url: str = ""
    content_type: str = ""
    published_at: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    source_topic_id: str = ""
    review_record_id: str | None = None

    def validate(self) -> None:
        require_text(self.account_id, "account_id")
        require_text(self.title, "title")
        ensure_optional_text(self.url, "url")
        require_text(self.content_type, "content_type")
        require_text(self.published_at, "published_at")
        require_dict(self.metrics, "metrics")
        ensure_list_items_are_text(self.tags, "tags")
        require_text(self.source_topic_id, "source_topic_id")
        ensure_optional_text(self.review_record_id, "review_record_id")


@dataclass
class ReviewRecord(BaseModel):
    collection_name: ClassVar[str] = "review-records"

    own_post_id: str = ""
    performance_summary: str = ""
    lessons: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    rule_updates: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.own_post_id, "own_post_id")
        require_text(self.performance_summary, "performance_summary")
        ensure_list_items_are_text(self.lessons, "lessons")
        ensure_list_items_are_text(self.next_actions, "next_actions")
        require_list(self.rule_updates, "rule_updates")
        for update in self.rule_updates:
            require_dict(update, "rule_updates item")


MODEL_TYPES: dict[str, type[BaseModel]] = {
    model.collection_name: model
    for model in [
        CreatorProfile,
        BenchmarkAccount,
        BenchmarkPost,
        ContentInboxItem,
        CaptureRecord,
        BenchmarkAnalysis,
        CustomTag,
        RuleCard,
        TopicItem,
        ContentDraft,
        PublishTask,
        OwnPost,
        ReviewRecord,
    ]
}
