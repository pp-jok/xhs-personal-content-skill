from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, field, fields
from datetime import datetime
import re
from typing import Any, ClassVar, Literal, TypeVar, get_args


ModelT = TypeVar("ModelT", bound="BaseModel")
CURRENT_SCHEMA_VERSION = "1"

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
RuleStatus = Literal["candidate", "approved", "testing", "validated", "rejected", "deprecated"]
RuleStrength = Literal["weak", "medium", "strong"]
RuleEvidenceSourceType = Literal[
    "benchmark_post",
    "benchmark_analysis",
    "content_mechanism",
    "user_feedback",
    "own_post",
    "review_record",
]
ContentAssetStatus = Literal["candidate", "active", "deprecated"]
ContentAssetType = Literal[
    "title_pattern",
    "cover_structure",
    "opening_template",
    "body_structure",
    "cta_template",
    "comparison_framework",
    "case_framework",
    "image_text_structure",
    "topic_framework",
]
ContentAssetEvidenceSourceType = Literal["content_mechanism"]
ContentMechanismStatus = Literal["candidate", "active", "deprecated"]
ContentMechanismConfidenceLevel = Literal["low", "medium", "high"]
ContentMechanismSourceType = Literal[
    "benchmark_post",
    "benchmark_analysis",
    "capture_record",
    "external_analysis",
    "user_input",
]
FeedbackNature = Literal[
    "explicit_user_rule",
    "content_specific_feedback",
    "inferred_preference",
    "candidate_rule",
    "uncertain",
]
ContentStatus = Literal["idea", "draft", "reviewing", "ready", "archived"]
PublishStatus = Literal["planned", "preparing", "ready", "published", "cancelled"]
QualityReviewType = Literal["pre_publish", "post_publish", "revision"]
InboxStatus = Literal["inbox", "capturing", "captured", "analyzed", "promoted_to_benchmark", "rejected", "archived"]
CaptureStatus = Literal["pending", "success", "partial", "failed"]
CaptureMethod = Literal["manual", "browser_authorized"]
CapturedContentType = Literal["unknown", "image", "video", "mixed"]
Actor = Literal["user", "codex", "system", "migration", "external_source"]
ArtifactNature = Literal["fact", "derived", "inference", "generated", "recommendation", "decision"]
DecisionStatus = Literal["pending", "confirmed", "rejected", "cancelled", "superseded"]
ObjectType = Literal[
    "creator_profile",
    "benchmark_account",
    "benchmark_post",
    "content_inbox",
    "capture_record",
    "benchmark_analysis",
    "content_mechanism",
    "content_asset",
    "custom_tag",
    "rule_card",
    "rule_evidence",
    "topic_item",
    "content_draft",
    "content_quality_review",
    "publish_task",
    "own_post",
    "review_record",
]
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


def ensure_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or value < 0:
        raise ValidationError(f"{field_name} must be a non-negative integer")


def ensure_score(value: int, field_name: str) -> None:
    if not isinstance(value, int) or not 0 <= value <= 5:
        raise ValidationError(f"{field_name} must be an integer from 0 to 5")


CONTENT_MECHANISM_CONFIDENCE_SCORES: dict[ContentMechanismConfidenceLevel, float] = {
    "low": 0.4,
    "medium": 0.6,
    "high": 0.8,
}
GENERIC_HOLLOW_TEXT = {"很好", "有价值", "推荐", "通用模板", "通用内容", "适合账号", "值得使用", "值得借鉴"}
VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLACEHOLDER_RE = re.compile(r"{{([^{}]*)}}")


def ensure_unique_texts(value: list[Any], field_name: str) -> None:
    ensure_list_items_are_text(value, field_name)
    cleaned = [item.strip() for item in value]
    if len(cleaned) != len(set(cleaned)):
        raise ValidationError(f"{field_name} must not contain duplicates")


def ensure_non_empty_unique_texts(value: list[Any], field_name: str, require_one: bool = False) -> None:
    ensure_unique_texts(value, field_name)
    if require_one and not value:
        raise ValidationError(f"{field_name} must contain at least one item")


def ensure_variable_names(value: list[str]) -> None:
    for item in value:
        if not VARIABLE_NAME_RE.match(item):
            raise ValidationError("variables must use names like result or process_step")


def reject_hollow_text(value: str, field_name: str) -> None:
    if value.strip() in GENERIC_HOLLOW_TEXT:
        raise ValidationError(f"{field_name} is too generic")


def validate_template_contract(template: str, variables: list[str]) -> None:
    require_text(template, "template")
    reject_hollow_text(template, "template")
    ensure_unique_texts(variables, "variables")
    ensure_variable_names(variables)
    if re.search(r"{{\s*}}", template):
        raise ValidationError("template placeholders cannot be empty")
    if template.count("{{") != template.count("}}"):
        raise ValidationError("template contains an unclosed placeholder")
    if "{{" in re.sub(PLACEHOLDER_RE, "", template) or "}}" in re.sub(PLACEHOLDER_RE, "", template):
        raise ValidationError("template contains invalid nested placeholders")
    placeholders = [item.strip() for item in PLACEHOLDER_RE.findall(template)]
    if not placeholders:
        raise ValidationError("template must contain at least one declared placeholder")
    if any(not VARIABLE_NAME_RE.match(item) for item in placeholders):
        raise ValidationError("template placeholders must use valid variable names")
    fixed_text = PLACEHOLDER_RE.sub("", template).strip()
    if not fixed_text:
        raise ValidationError("template must contain fixed structure text")
    declared = set(variables)
    used = set(placeholders)
    if not used <= declared:
        raise ValidationError("template contains undeclared placeholders")
    if declared != used:
        raise ValidationError("variables must all be used in template")


@dataclass
class BaseModel:
    id: str
    schema_version: str = CURRENT_SCHEMA_VERSION
    version: int = 1
    created_by: Actor = "user"
    provenance_refs: list[str] = field(default_factory=list)
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
        require_text(self.schema_version, "schema_version")
        ensure_non_negative_int(self.version, "version")
        if self.version < 1:
            raise ValidationError("version must be at least 1")
        require_literal(self.created_by, Actor, "created_by")
        ensure_list_items_are_text(self.provenance_refs, "provenance_refs")
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
    canonical_url: str = ""
    capture_method: CaptureMethod = "manual"
    capture_status: CaptureStatus = "partial"
    captured_at: str = field(default_factory=now_iso)
    published_at: str | None = None
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
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        require_text(self.inbox_item_id, "inbox_item_id")
        require_text(self.source_url, "source_url")
        ensure_optional_text(self.canonical_url, "canonical_url")
        require_literal(self.capture_method, CaptureMethod, "capture_method")
        require_literal(self.capture_status, CaptureStatus, "capture_status")
        require_text(self.captured_at, "captured_at")
        ensure_optional_text(self.published_at, "published_at")
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
        require_dict(self.diagnostics, "diagnostics")


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
class ContentMechanism(BaseModel):
    collection_name: ClassVar[str] = "content-mechanisms"

    confidence: float = 0.4
    name: str = ""
    description: str = ""
    status: ContentMechanismStatus = "candidate"
    confidence_level: ContentMechanismConfidenceLevel = "low"
    source_refs: list[dict[str, str]] = field(default_factory=list)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    problem: str = ""
    solution: str = ""
    pattern: list[str] = field(default_factory=list)
    applicable_scope: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentMechanism":
        require_dict(data, cls.__name__)
        normalized = dict(data)
        confidence_level = normalized.get("confidence_level", "low")
        if "confidence" not in normalized and confidence_level in CONTENT_MECHANISM_CONFIDENCE_SCORES:
            normalized["confidence"] = CONTENT_MECHANISM_CONFIDENCE_SCORES[confidence_level]
        return super().from_dict(normalized)

    def validate(self) -> None:
        require_text(self.name, "name")
        require_text(self.description, "description")
        require_literal(self.status, ContentMechanismStatus, "status")
        require_literal(self.confidence_level, ContentMechanismConfidenceLevel, "confidence_level")
        expected_confidence = CONTENT_MECHANISM_CONFIDENCE_SCORES[self.confidence_level]
        if float(self.confidence) != expected_confidence:
            raise ValidationError("confidence must match confidence_level")
        require_list(self.source_refs, "source_refs")
        for item in self.source_refs:
            require_dict(item, "source_refs item")
            if set(item) != {"source_type", "source_id"}:
                raise ValidationError("source_refs item must contain source_type and source_id")
            require_literal(item["source_type"], ContentMechanismSourceType, "source_type")
            require_text(item["source_id"], "source_id")
        require_dict(self.evidence_summary, "evidence_summary")
        observed_facts = self.evidence_summary.get("observed_facts")
        ensure_list_items_are_text(observed_facts, "evidence_summary.observed_facts")
        for field_name in ("inferences", "user_stated_preferences", "missing_information", "limitations"):
            if field_name in self.evidence_summary:
                ensure_list_items_are_text(self.evidence_summary[field_name], f"evidence_summary.{field_name}")
        if "source_coverage" in self.evidence_summary:
            require_dict(self.evidence_summary["source_coverage"], "evidence_summary.source_coverage")
            for key, value in self.evidence_summary["source_coverage"].items():
                require_text(key, "evidence_summary.source_coverage key")
                require_text(value, "evidence_summary.source_coverage value")
        ensure_optional_text(self.problem, "problem")
        ensure_optional_text(self.solution, "solution")
        ensure_list_items_are_text(self.pattern, "pattern")
        ensure_list_items_are_text(self.applicable_scope, "applicable_scope")
        ensure_list_items_are_text(self.limitations, "limitations")


@dataclass
class ContentAsset(BaseModel):
    collection_name: ClassVar[str] = "content-assets"

    confidence: float = 0.4
    status: ContentAssetStatus = "candidate"
    asset_type: ContentAssetType = "opening_template"
    name: str = ""
    description: str = ""
    template: str = ""
    variables: list[str] = field(default_factory=list)
    applicable_scope: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    usage_notes: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    creator_profile_id: str = ""
    source_mechanism_ids: list[str] = field(default_factory=list)
    selected_observed_facts: list[str] = field(default_factory=list)
    account_fit_reason: str = ""
    confidence_level: ContentMechanismConfidenceLevel = "low"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentAsset":
        require_dict(data, cls.__name__)
        normalized = dict(data)
        confidence_level = normalized.get("confidence_level", "low")
        if "confidence" not in normalized and confidence_level in CONTENT_MECHANISM_CONFIDENCE_SCORES:
            normalized["confidence"] = CONTENT_MECHANISM_CONFIDENCE_SCORES[confidence_level]
        return super().from_dict(normalized)

    def validate(self) -> None:
        require_literal(self.status, ContentAssetStatus, "status")
        require_literal(self.asset_type, ContentAssetType, "asset_type")
        require_text(self.name, "name")
        reject_hollow_text(self.name, "name")
        require_text(self.description, "description")
        reject_hollow_text(self.description, "description")
        validate_template_contract(self.template, self.variables)
        ensure_unique_texts(self.variables, "variables")
        ensure_variable_names(self.variables)
        ensure_non_empty_unique_texts(self.applicable_scope, "applicable_scope", require_one=True)
        ensure_non_empty_unique_texts(self.exclusions, "exclusions")
        ensure_non_empty_unique_texts(self.usage_notes, "usage_notes")
        ensure_non_empty_unique_texts(self.limitations, "limitations")
        ensure_non_empty_unique_texts(self.examples, "examples")
        require_text(self.creator_profile_id, "creator_profile_id")
        ensure_non_empty_unique_texts(self.source_mechanism_ids, "source_mechanism_ids", require_one=True)
        if len(self.source_mechanism_ids) != 1:
            raise ValidationError("source_mechanism_ids must contain exactly one mechanism id")
        ensure_non_empty_unique_texts(self.selected_observed_facts, "selected_observed_facts", require_one=True)
        if len(self.selected_observed_facts) > 3:
            raise ValidationError("selected_observed_facts can contain at most 3 items")
        require_text(self.account_fit_reason, "account_fit_reason")
        require_literal(self.confidence_level, ContentMechanismConfidenceLevel, "confidence_level")
        expected_confidence = CONTENT_MECHANISM_CONFIDENCE_SCORES[self.confidence_level]
        if float(self.confidence) != expected_confidence:
            raise ValidationError("confidence must match confidence_level")


@dataclass
class ContentAssetEvidence(BaseModel):
    collection_name: ClassVar[str] = "content-asset-evidence"

    confidence: float = 0.4
    asset_id: str = ""
    source_type: ContentAssetEvidenceSourceType = "content_mechanism"
    source_id: str = ""
    source_version: int = 1
    source_fragment: str = ""
    evidence_text: str = ""
    confidence_level: ContentMechanismConfidenceLevel = "low"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentAssetEvidence":
        require_dict(data, cls.__name__)
        normalized = dict(data)
        confidence_level = normalized.get("confidence_level", "low")
        if "confidence" not in normalized and confidence_level in CONTENT_MECHANISM_CONFIDENCE_SCORES:
            normalized["confidence"] = CONTENT_MECHANISM_CONFIDENCE_SCORES[confidence_level]
        return super().from_dict(normalized)

    def validate(self) -> None:
        require_text(self.asset_id, "asset_id")
        require_literal(self.source_type, ContentAssetEvidenceSourceType, "source_type")
        require_text(self.source_id, "source_id")
        ensure_non_negative_int(self.source_version, "source_version")
        if self.source_version < 1:
            raise ValidationError("source_version must be at least 1")
        require_text(self.source_fragment, "source_fragment")
        require_text(self.evidence_text, "evidence_text")
        require_literal(self.confidence_level, ContentMechanismConfidenceLevel, "confidence_level")
        expected_confidence = CONTENT_MECHANISM_CONFIDENCE_SCORES[self.confidence_level]
        if float(self.confidence) != expected_confidence:
            raise ValidationError("confidence must match confidence_level")


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
    status: RuleStatus = "candidate"
    strength: RuleStrength = "weak"
    validation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_validated_at: str | None = None
    applicable_content_types: list[str] = field(default_factory=list)
    applicable_audiences: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    deprecated_reason: str = ""

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
        require_literal(self.status, RuleStatus, "status")
        require_literal(self.strength, RuleStrength, "strength")
        ensure_non_negative_int(self.validation_count, "validation_count")
        ensure_non_negative_int(self.success_count, "success_count")
        ensure_non_negative_int(self.failure_count, "failure_count")
        ensure_optional_text(self.last_validated_at, "last_validated_at")
        ensure_list_items_are_text(self.applicable_content_types, "applicable_content_types")
        ensure_list_items_are_text(self.applicable_audiences, "applicable_audiences")
        ensure_list_items_are_text(self.conflicts_with, "conflicts_with")
        ensure_list_items_are_text(self.supersedes, "supersedes")
        ensure_optional_text(self.deprecated_reason, "deprecated_reason")


@dataclass
class RuleEvidence(BaseModel):
    collection_name: ClassVar[str] = "rule-evidence"

    rule_id: str = ""
    source_type: RuleEvidenceSourceType = "benchmark_post"
    source_id: str = ""
    source_fragment: str = ""
    evidence_type: str = ""
    observable_fact: str = ""
    inference: str = ""

    def validate(self) -> None:
        require_text(self.rule_id, "rule_id")
        require_literal(self.source_type, RuleEvidenceSourceType, "source_type")
        require_text(self.source_id, "source_id")
        require_text(self.source_fragment, "source_fragment")
        require_text(self.evidence_type, "evidence_type")
        require_text(self.observable_fact, "observable_fact")
        require_text(self.inference, "inference")


@dataclass
class ProvenanceRecord(BaseModel):
    collection_name: ClassVar[str] = "provenance-records"

    target_object_type: ObjectType = "rule_card"
    target_object_id: str = ""
    source_object_type: ObjectType = "benchmark_analysis"
    source_object_id: str = ""
    source_version: int = 1
    actor: Actor = "system"
    artifact_nature: ArtifactNature = "fact"
    method: str = ""
    note: str = ""

    def validate(self) -> None:
        require_literal(self.target_object_type, ObjectType, "target_object_type")
        require_text(self.target_object_id, "target_object_id")
        require_literal(self.source_object_type, ObjectType, "source_object_type")
        require_text(self.source_object_id, "source_object_id")
        ensure_non_negative_int(self.source_version, "source_version")
        if self.source_version < 1:
            raise ValidationError("source_version must be at least 1")
        require_literal(self.actor, Actor, "actor")
        require_literal(self.artifact_nature, ArtifactNature, "artifact_nature")
        require_text(self.method, "method")
        ensure_optional_text(self.note, "note")


@dataclass
class DecisionRequest(BaseModel):
    collection_name: ClassVar[str] = "decision-requests"

    target_object_type: ObjectType = "rule_card"
    target_object_id: str = ""
    question: str = ""
    options: list[str] = field(default_factory=list)
    option_outcomes: dict[str, DecisionStatus] = field(default_factory=dict)
    recommendation: str = ""
    recommendation_reason: str = ""
    impact: str = ""
    status: DecisionStatus = "pending"
    selected_option: str = ""
    user_note: str = ""
    resulting_state_changes: list[dict[str, Any]] = field(default_factory=list)
    expected_target_version: int | None = None
    resolved_at: str | None = None
    resolved_by: Actor | None = None

    def validate(self) -> None:
        require_literal(self.target_object_type, ObjectType, "target_object_type")
        require_text(self.target_object_id, "target_object_id")
        require_text(self.question, "question")
        ensure_list_items_are_text(self.options, "options")
        if len(self.options) < 2:
            raise ValidationError("options must contain at least two choices")
        if not self.option_outcomes:
            self.option_outcomes.update(legacy_option_outcomes(self.options))
        require_dict(self.option_outcomes, "option_outcomes")
        for option, outcome in self.option_outcomes.items():
            if option not in self.options:
                raise ValidationError("option_outcomes keys must be present in options")
            require_literal(outcome, DecisionStatus, "option_outcomes value")
            if outcome == "pending":
                raise ValidationError("option_outcomes cannot resolve to pending")
        for option in self.options:
            if option not in self.option_outcomes:
                raise ValidationError("each option must have an explicit outcome")
        require_text(self.recommendation, "recommendation")
        if self.recommendation not in self.options:
            raise ValidationError("recommendation must be one of options")
        require_text(self.recommendation_reason, "recommendation_reason")
        require_text(self.impact, "impact")
        require_literal(self.status, DecisionStatus, "status")
        ensure_optional_text(self.selected_option, "selected_option")
        if self.selected_option and self.selected_option not in self.options:
            raise ValidationError("selected_option must be one of options")
        ensure_optional_text(self.user_note, "user_note")
        require_list(self.resulting_state_changes, "resulting_state_changes")
        for change in self.resulting_state_changes:
            require_dict(change, "resulting_state_changes item")
        if self.expected_target_version is not None:
            ensure_non_negative_int(self.expected_target_version, "expected_target_version")
            if self.expected_target_version < 1:
                raise ValidationError("expected_target_version must be at least 1")
        ensure_optional_text(self.resolved_at, "resolved_at")
        if self.resolved_by is not None:
            require_literal(self.resolved_by, Actor, "resolved_by")
        if self.status == "pending":
            if self.selected_option or self.resolved_at or self.resulting_state_changes or self.resolved_by:
                raise ValidationError("pending decisions cannot have selected_option, resolved_at, resolved_by, or state changes")
        else:
            require_text(self.selected_option, "selected_option")
            require_text(self.resolved_at or "", "resolved_at")
            require_text(self.resolved_by or "", "resolved_by")
            selected_outcome = self.option_outcomes.get(self.selected_option)
            if selected_outcome != self.status:
                raise ValidationError("selected option outcome must match decision status")


@dataclass
class ObjectVersion(BaseModel):
    collection_name: ClassVar[str] = "object-versions"

    target_object_type: ObjectType = "rule_card"
    target_object_id: str = ""
    object_version: int = 1
    snapshot: dict[str, Any] = field(default_factory=dict)
    changed_by: Actor = "system"
    change_note: str = ""

    def validate(self) -> None:
        require_literal(self.target_object_type, ObjectType, "target_object_type")
        require_text(self.target_object_id, "target_object_id")
        ensure_non_negative_int(self.object_version, "object_version")
        if self.object_version < 1:
            raise ValidationError("object_version must be at least 1")
        require_dict(self.snapshot, "snapshot")
        require_literal(self.changed_by, Actor, "changed_by")
        ensure_optional_text(self.change_note, "change_note")


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
    source_profile_id: str = ""
    source_profile_version: int | None = None
    generation_context_status: str = ""
    task_constraints: dict[str, Any] = field(default_factory=dict)
    risk_warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    def validate(self) -> None:
        require_text(self.title, "title")
        require_text(self.content_goal, "content_goal")
        require_text(self.content_format, "content_format")
        ensure_list_items_are_text(self.source_rule_cards, "source_rule_cards")
        ensure_list_items_are_text(self.reference_posts, "reference_posts")
        require_text(self.reason, "reason")
        require_literal(self.status, ContentStatus, "status")
        ensure_list_items_are_text(self.tags, "tags")
        if not isinstance(self.source_profile_id, str):
            raise ValidationError("source_profile_id must be a string")
        if self.source_profile_version is not None:
            ensure_non_negative_int(self.source_profile_version, "source_profile_version")
            if self.source_profile_version < 1:
                raise ValidationError("source_profile_version must be at least 1")
        if self.generation_context_status not in {"", "ready", "limited"}:
            raise ValidationError("generation_context_status must be empty, ready, or limited")
        require_dict(self.task_constraints, "task_constraints")
        ensure_list_items_are_text(self.risk_warnings, "risk_warnings")
        ensure_list_items_are_text(self.missing_information, "missing_information")


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
    source_profile_id: str = ""
    source_profile_version: int | None = None
    source_rule_cards: list[str] = field(default_factory=list)
    generation_context_status: str = ""
    task_constraints: dict[str, Any] = field(default_factory=dict)
    risk_warnings: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    parent_draft_id: str = ""
    revision_focus: str = ""
    diagnosis: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        require_text(self.topic_id, "topic_id")
        ensure_list_items_are_text(self.titles, "titles")
        ensure_list_items_are_text(self.cover_titles, "cover_titles")
        require_text(self.script, "script")
        ensure_list_items_are_text(self.shot_suggestions, "shot_suggestions")
        require_literal(self.status, ContentStatus, "status")
        require_dict(self.quality_review, "quality_review")
        ensure_list_items_are_text(self.tags, "tags")
        if not isinstance(self.source_profile_id, str):
            raise ValidationError("source_profile_id must be a string")
        if self.source_profile_version is not None:
            ensure_non_negative_int(self.source_profile_version, "source_profile_version")
            if self.source_profile_version < 1:
                raise ValidationError("source_profile_version must be at least 1")
        ensure_list_items_are_text(self.source_rule_cards, "source_rule_cards")
        if self.generation_context_status not in {"", "ready", "limited"}:
            raise ValidationError("generation_context_status must be empty, ready, or limited")
        require_dict(self.task_constraints, "task_constraints")
        ensure_list_items_are_text(self.risk_warnings, "risk_warnings")
        ensure_list_items_are_text(self.missing_information, "missing_information")
        if not isinstance(self.parent_draft_id, str):
            raise ValidationError("parent_draft_id must be a string")
        if not isinstance(self.revision_focus, str):
            raise ValidationError("revision_focus must be a string")
        require_dict(self.diagnosis, "diagnosis")


@dataclass
class ContentQualityReview(BaseModel):
    collection_name: ClassVar[str] = "content-quality-reviews"

    draft_id: str = ""
    review_type: QualityReviewType = "pre_publish"
    account_fit_score: int = 0
    publishability_score: int = 0
    title_score: int = 0
    cover_score: int = 0
    structure_score: int = 0
    tone_score: int = 0
    revision_count: int = 0
    major_rewrite_required: bool = False
    issues: list[dict[str, Any]] = field(default_factory=list)
    accepted_rules: list[str] = field(default_factory=list)
    rejected_rules: list[str] = field(default_factory=list)
    reviewer_notes: str = ""

    def validate(self) -> None:
        require_text(self.draft_id, "draft_id")
        require_literal(self.review_type, QualityReviewType, "review_type")
        ensure_score(self.account_fit_score, "account_fit_score")
        ensure_score(self.publishability_score, "publishability_score")
        ensure_score(self.title_score, "title_score")
        ensure_score(self.cover_score, "cover_score")
        ensure_score(self.structure_score, "structure_score")
        ensure_score(self.tone_score, "tone_score")
        ensure_non_negative_int(self.revision_count, "revision_count")
        if not isinstance(self.major_rewrite_required, bool):
            raise ValidationError("major_rewrite_required must be a boolean")
        require_list(self.issues, "issues")
        for issue in self.issues:
            require_dict(issue, "issues item")
        ensure_list_items_are_text(self.accepted_rules, "accepted_rules")
        ensure_list_items_are_text(self.rejected_rules, "rejected_rules")
        ensure_optional_text(self.reviewer_notes, "reviewer_notes")


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
        ContentMechanism,
        ContentAsset,
        ContentAssetEvidence,
        CustomTag,
        RuleCard,
        RuleEvidence,
        ProvenanceRecord,
        DecisionRequest,
        ObjectVersion,
        TopicItem,
        ContentDraft,
        ContentQualityReview,
        PublishTask,
        OwnPost,
        ReviewRecord,
    ]
}


def legacy_option_outcomes(options: list[str]) -> dict[str, DecisionStatus]:
    legacy = {
        "confirm": "confirmed",
        "approve": "confirmed",
        "approved": "confirmed",
        "reject": "rejected",
        "rejected": "rejected",
        "cancel": "cancelled",
        "cancelled": "cancelled",
        "supersede": "superseded",
        "superseded": "superseded",
    }
    outcomes: dict[str, DecisionStatus] = {}
    for option in options:
        outcome = legacy.get(option)
        if outcome:
            outcomes[option] = outcome  # type: ignore[assignment]
    return outcomes
