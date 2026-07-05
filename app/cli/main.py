from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha1
from pathlib import Path
from typing import Any, Sequence

from app.capture import build_capture_record
from app.models.core import (
    MODEL_TYPES,
    BaseModel,
    BenchmarkAccount,
    BenchmarkPost,
    CaptureRecord,
    ContentDraft,
    ContentInboxItem,
    CreatorProfile,
    CustomTag,
    OwnPost,
    PublishTask,
    ReviewRecord,
    RuleCard,
    TopicItem,
)
from app.repositories import JsonRepository
from app.services.mock_prompt_service import MockPromptService
from app.services.prompt_contracts import load_contracts
from app.services.real_sample_validation import RealSampleValidator
from app.workflows import BenchmarkToPublishWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PROMPTS_DIR = PROJECT_ROOT / "prompts"
REQUIRED_WORKSPACE_FILES = ("creator_profile.json", "benchmark_account.json", "benchmark_post.json", "custom_tags.json")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
    except Exception as exc:
        print_json({"ok": False, "error": str(exc)})
        return 1

    print_json({"ok": True, "result": result})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local CLI for the personal content operation skill.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Path to local JSON data directory.")
    parser.add_argument("--prompts-dir", default=str(DEFAULT_PROMPTS_DIR), help="Path to prompt contract directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import-json", help="Import one model record from a JSON file.")
    import_parser.add_argument("collection", choices=sorted(MODEL_TYPES), help="Target collection name.")
    import_parser.add_argument("file", help="JSON file to import.")
    import_parser.add_argument("--upsert", action="store_true", help="Overwrite existing record with the same id.")
    import_parser.set_defaults(handler=handle_import_json)

    list_parser = subparsers.add_parser("list", help="List records in a collection.")
    list_parser.add_argument("collection", choices=sorted(MODEL_TYPES), help="Collection name.")
    list_parser.set_defaults(handler=handle_list)

    show_parser = subparsers.add_parser("show", help="Show one record by id.")
    show_parser.add_argument("collection", choices=sorted(MODEL_TYPES), help="Collection name.")
    show_parser.add_argument("record_id", help="Record id.")
    show_parser.set_defaults(handler=handle_show)

    workflow_parser = subparsers.add_parser("run-workflow", help="Run benchmark-to-publish local workflow.")
    workflow_parser.add_argument("--creator-id", required=True, help="CreatorProfile id.")
    workflow_parser.add_argument("--benchmark-post-id", required=True, help="BenchmarkPost id.")
    workflow_parser.add_argument("--planned-publish-time", required=True, help="Planned publish time string.")
    workflow_parser.add_argument("--topic-count", type=int, default=1, help="Number of topics to request.")
    workflow_parser.set_defaults(handler=handle_run_workflow)

    validation_parser = subparsers.add_parser("validate-real-sample", help="Run Phase 6 real sample validation.")
    validation_parser.add_argument("--workspace", required=True, help="Real sample workspace directory.")
    validation_parser.set_defaults(handler=handle_validate_real_sample)

    init_parser = subparsers.add_parser("init-workspace", help="Initialize a local account operation workspace.")
    init_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    init_parser.set_defaults(handler=handle_init_workspace)

    profile_parser = subparsers.add_parser("upsert-profile", help="Upsert a creator profile into a workspace.")
    profile_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    profile_parser.add_argument("--file", required=True, help="Creator profile JSON file.")
    profile_parser.set_defaults(handler=handle_upsert_profile)

    account_parser = subparsers.add_parser("add-benchmark-account", help="Add or update benchmark account data.")
    account_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    account_parser.add_argument("--file", required=True, help="Benchmark account JSON file.")
    account_parser.set_defaults(handler=handle_add_benchmark_account)

    post_parser = subparsers.add_parser("add-benchmark-post", help="Add or update benchmark post data.")
    post_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    post_parser.add_argument("--file", required=True, help="Benchmark post JSON file.")
    post_parser.set_defaults(handler=handle_add_benchmark_post)

    tags_parser = subparsers.add_parser("add-custom-tags", help="Add or update custom tags.")
    tags_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    tags_parser.add_argument("--file", required=True, help="Custom tags JSON file.")
    tags_parser.set_defaults(handler=handle_add_custom_tags)

    feedback_parser = subparsers.add_parser("add-feedback", help="Append user feedback to workspace validation feedback.")
    feedback_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    feedback_parser.add_argument("--file", required=True, help="Validation feedback JSON file.")
    feedback_parser.set_defaults(handler=handle_add_feedback)

    workspace_validation_parser = subparsers.add_parser(
        "validate-workspace",
        help="Validate whether a workspace has the minimum files needed for real sample validation.",
    )
    workspace_validation_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    workspace_validation_parser.set_defaults(handler=handle_validate_workspace)

    inbox_parser = subparsers.add_parser("add-inbox-item", help="Add or update one user-provided content link.")
    inbox_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    inbox_parser.add_argument("--url", required=True, help="User-provided Xiaohongshu URL.")
    inbox_parser.add_argument("--user-intent", default="", help="What the user wants to learn from the link.")
    inbox_parser.add_argument("--user-reason", default="", help="Why the user thinks the link is useful.")
    inbox_parser.add_argument("--focus", action="append", default=[], help="Requested focus, can be repeated.")
    inbox_parser.set_defaults(handler=handle_add_inbox_item)

    capture_parser = subparsers.add_parser("capture-xhs-link", help="Create a local capture record for one inbox item.")
    capture_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    capture_parser.add_argument("--inbox-item-id", required=True, help="ContentInboxItem id.")
    capture_parser.add_argument("--manual-file", help="Optional JSON file with user-visible copied content.")
    capture_parser.set_defaults(handler=handle_capture_xhs_link)

    show_capture_parser = subparsers.add_parser("show-capture-result", help="Show one capture record.")
    show_capture_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    show_capture_parser.add_argument("--capture-id", required=True, help="CaptureRecord id.")
    show_capture_parser.set_defaults(handler=handle_show_capture_result)

    rule_parser = subparsers.add_parser("generate-rule-cards", help="Generate local mock rule cards for one benchmark post.")
    rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    rule_parser.add_argument("--creator-id", required=True, help="CreatorProfile id.")
    rule_parser.add_argument("--benchmark-post-id", required=True, help="BenchmarkPost id.")
    rule_parser.set_defaults(handler=handle_generate_rule_cards)

    topics_parser = subparsers.add_parser("generate-topics", help="Generate local mock topics from rules and one benchmark post.")
    topics_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    topics_parser.add_argument("--creator-id", required=True, help="CreatorProfile id.")
    topics_parser.add_argument("--benchmark-post-id", required=True, help="BenchmarkPost id.")
    topics_parser.add_argument("--topic-count", type=int, default=5, help="Number of topics to generate.")
    topics_parser.set_defaults(handler=handle_generate_topics)

    draft_parser = subparsers.add_parser("generate-draft", help="Generate a local mock draft for one topic.")
    draft_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    draft_parser.add_argument("--topic-id", required=True, help="TopicItem id.")
    draft_parser.set_defaults(handler=handle_generate_draft)

    publish_parser = subparsers.add_parser("create-publish-task", help="Create a publish task for one draft.")
    publish_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    publish_parser.add_argument("--draft-id", required=True, help="ContentDraft id.")
    publish_parser.add_argument("--planned-publish-time", required=True, help="Planned publish time string.")
    publish_parser.add_argument("--account-id", default="creator-main", help="Creator account id.")
    publish_parser.set_defaults(handler=handle_create_publish_task)

    review_parser = subparsers.add_parser("review-own-post", help="Create a review record for one own post.")
    review_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    review_parser.add_argument("--own-post-id", required=True, help="OwnPost id.")
    review_parser.set_defaults(handler=handle_review_own_post)

    return parser


def handle_import_json(args: argparse.Namespace) -> dict[str, Any]:
    model_type = get_model_type(args.collection)
    with Path(args.file).open("r", encoding="utf-8") as file:
        data = json.load(file)
    model = model_type.from_dict(data)
    repo = JsonRepository(args.data_dir, model_type)
    saved = repo.upsert(model) if args.upsert else repo.create(model)
    return {"collection": args.collection, "id": saved.id}


def handle_list(args: argparse.Namespace) -> list[dict[str, Any]]:
    model_type = get_model_type(args.collection)
    repo = JsonRepository(args.data_dir, model_type)
    return [item.to_dict() for item in repo.list_all()]


def handle_show(args: argparse.Namespace) -> dict[str, Any]:
    model_type = get_model_type(args.collection)
    repo = JsonRepository(args.data_dir, model_type)
    return repo.read(args.record_id).to_dict()


def handle_run_workflow(args: argparse.Namespace) -> dict[str, Any]:
    workflow = BenchmarkToPublishWorkflow(args.data_dir, args.prompts_dir)
    result = workflow.run(
        creator_profile_id=args.creator_id,
        benchmark_post_id=args.benchmark_post_id,
        planned_publish_time=args.planned_publish_time,
        topic_count=args.topic_count,
    )
    return {
        "benchmark_post_id": result.benchmark_post.id,
        "rule_card_ids": [item.id for item in result.rule_cards],
        "topic_ids": [item.id for item in result.topics],
        "draft_id": result.draft.id,
        "publish_task_id": result.publish_task.id,
        "warnings": result.warnings,
    }


def handle_validate_real_sample(args: argparse.Namespace) -> dict[str, Any]:
    validator = RealSampleValidator(args.workspace, args.prompts_dir)
    return validator.run().to_dict()


def handle_init_workspace(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    return workspace_status(workspace)


def handle_upsert_profile(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    data = read_json_object(Path(args.file), "creator profile")
    profile = CreatorProfile.from_dict(data)
    JsonRepository(workspace, CreatorProfile).upsert(profile)
    write_json(workspace / "creator_profile.json", profile.to_dict())
    status = workspace_status(workspace)
    return {"id": profile.id, "workspace": str(workspace), "missing_required_files": status["missing_required_files"]}


def handle_add_benchmark_account(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    items = read_json_items(Path(args.file), "benchmark account")
    repo = JsonRepository(workspace, BenchmarkAccount)
    saved = [repo.upsert(BenchmarkAccount.from_dict(item)) for item in items]
    root_items = merge_root_items(workspace / "benchmark_account.json", [item.to_dict() for item in saved])
    return {"ids": [item.id for item in saved], "total": len(root_items), "workspace": str(workspace)}


def handle_add_benchmark_post(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    items = read_json_items(Path(args.file), "benchmark post")
    repo = JsonRepository(workspace, BenchmarkPost)
    saved = [repo.upsert(BenchmarkPost.from_dict(item)) for item in items]
    root_items = merge_root_items(workspace / "benchmark_post.json", [item.to_dict() for item in saved])
    return {"ids": [item.id for item in saved], "total": len(root_items), "workspace": str(workspace)}


def handle_add_custom_tags(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    items = read_json_items(Path(args.file), "custom tags")
    repo = JsonRepository(workspace, CustomTag)
    saved = [repo.upsert(CustomTag.from_dict(item)) for item in items]
    root_items = merge_root_items(workspace / "custom_tags.json", [item.to_dict() for item in saved])
    return {"ids": [item.id for item in saved], "total": len(root_items), "workspace": str(workspace)}


def handle_add_feedback(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    incoming = read_json_object(Path(args.file), "validation feedback")
    issues = incoming.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("feedback issues must be a list")

    target = workspace / "validation_feedback.json"
    if target.exists():
        existing = read_json_object(target, "validation feedback")
        existing_issues = existing.get("issues", [])
        if not isinstance(existing_issues, list):
            raise ValueError("existing feedback issues must be a list")
        existing["issues"] = existing_issues + issues
        if incoming.get("overall_notes"):
            current_notes = existing.get("overall_notes", "")
            separator = "\n" if current_notes else ""
            existing["overall_notes"] = f"{current_notes}{separator}{incoming['overall_notes']}"
        merged = existing
    else:
        merged = incoming

    write_json(target, merged)
    rule_card_ids = create_feedback_rule_cards(workspace, issues)
    return {"workspace": str(workspace), "issue_count": len(merged.get("issues", [])), "rule_card_ids": rule_card_ids}


def handle_validate_workspace(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    return workspace_status(workspace)


def handle_add_inbox_item(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    repo = JsonRepository(workspace, ContentInboxItem)
    existing = find_inbox_item_by_url(repo.list_all(), args.url)
    deduplicated = existing is not None
    item_id = existing.id if existing else build_inbox_id(args.url)
    data = existing.to_dict() if existing else {}
    data.update(
        {
            "id": item_id,
            "source_url": args.url,
            "source_platform": "xiaohongshu",
            "status": data.get("status", "inbox"),
            "capture_status": data.get("capture_status", "pending"),
            "content_type": data.get("content_type", "unknown"),
            "user_intent": args.user_intent or data.get("user_intent", ""),
            "user_reason": args.user_reason or data.get("user_reason", ""),
            "requested_focus": args.focus or data.get("requested_focus", []),
            "source_type": "user_provided_link",
            "created_from": "add-inbox-item",
        }
    )
    saved = repo.upsert(ContentInboxItem.from_dict(data))
    return {"id": saved.id, "deduplicated": deduplicated, "status": saved.status, "capture_status": saved.capture_status}


def handle_capture_xhs_link(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    inbox_repo = JsonRepository(workspace, ContentInboxItem)
    capture_repo = JsonRepository(workspace, CaptureRecord)
    inbox_item = inbox_repo.update(args.inbox_item_id, {"status": "capturing"})
    manual_data = read_json_object(Path(args.manual_file), "manual capture") if args.manual_file else None
    capture = build_capture_record(inbox_item, manual_data)
    saved = capture_repo.upsert(capture)
    inbox_repo.update(
        inbox_item.id,
        {
            "status": "captured" if saved.capture_status in {"success", "partial"} else "inbox",
            "capture_status": saved.capture_status,
            "content_type": saved.content_type,
            "captured_at": saved.captured_at,
            "missing_fields": saved.missing_fields,
            "warnings": saved.warnings,
            "confidence": saved.confidence,
        },
    )
    return {
        "capture_id": saved.id,
        "inbox_item_id": inbox_item.id,
        "capture_status": saved.capture_status,
        "missing_fields": saved.missing_fields,
        "warnings": saved.warnings,
    }


def handle_show_capture_result(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    return JsonRepository(workspace, CaptureRecord).read(args.capture_id).to_dict()


def handle_generate_rule_cards(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    creator = JsonRepository(workspace, CreatorProfile).read(args.creator_id)
    post_repo = JsonRepository(workspace, BenchmarkPost)
    post = post_repo.read(args.benchmark_post_id)
    tags = JsonRepository(workspace, CustomTag).list_all()
    prompt_service = build_prompt_service(args.prompts_dir)

    analysis = prompt_service.run(
        "analyze_benchmark_post",
        {
            "creator_profile": creator.to_dict(),
            "benchmark_post": post.to_dict(),
            "custom_tags": [tag.to_dict() for tag in tags],
        },
    )
    post = post_repo.update(
        post.id,
        {
            "ai_analysis": analysis["ai_analysis"],
            "borrowable_points": analysis["borrowable_points"],
            "non_borrowable_points": analysis["non_borrowable_points"],
            "rule_card_candidates": analysis["rule_card_candidates"],
        },
    )
    extracted = prompt_service.run(
        "extract_rule_card",
        {
            "creator_profile": creator.to_dict(),
            "benchmark_post_id": post.id,
            "analysis_result": analysis,
        },
    )
    saved = save_rule_cards(workspace, post.id, extracted["rule_cards"])
    return {"rule_card_ids": [rule.id for rule in saved], "warnings": analysis.get("warnings", []) + extracted.get("warnings", [])}


def handle_generate_topics(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    creator = JsonRepository(workspace, CreatorProfile).read(args.creator_id)
    post = JsonRepository(workspace, BenchmarkPost).read(args.benchmark_post_id)
    tags = JsonRepository(workspace, CustomTag).list_all()
    rule_repo = JsonRepository(workspace, RuleCard)
    rule_cards = [rule for rule in rule_repo.list_all() if post.id in rule.source_ids]
    if not rule_cards:
        generated = handle_generate_rule_cards(args)
        rule_cards = [rule_repo.read(rule_id) for rule_id in generated["rule_card_ids"]]

    topic_payload = build_prompt_service(args.prompts_dir).run(
        "generate_topic_pool",
        {
            "creator_profile": creator.to_dict(),
            "custom_tags": [tag.to_dict() for tag in tags],
            "rule_cards": [rule.to_dict() for rule in rule_cards],
            "reference_posts": [post.to_dict()],
            "topic_count": args.topic_count,
        },
    )
    saved = save_topics(workspace, post.id, topic_payload["topics"])
    return {"topic_ids": [topic.id for topic in saved], "warnings": topic_payload.get("warnings", [])}


def handle_generate_draft(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    topic = JsonRepository(workspace, TopicItem).read(args.topic_id)
    creator = first_record(workspace, CreatorProfile)
    tags = JsonRepository(workspace, CustomTag).list_all()
    rule_cards = JsonRepository(workspace, RuleCard).list_all()
    draft_payload = build_prompt_service(args.prompts_dir).run(
        "generate_content_draft",
        {
            "creator_profile": creator.to_dict(),
            "topic": topic.to_dict(),
            "rule_cards": [rule.to_dict() for rule in rule_cards],
            "custom_tags": [tag.to_dict() for tag in tags],
        },
    )
    saved = save_draft(workspace, args.topic_id, draft_payload["draft"])
    return {"draft_id": saved.id, "warnings": draft_payload.get("warnings", [])}


def handle_create_publish_task(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    creator = JsonRepository(workspace, CreatorProfile).read(args.account_id)
    draft = JsonRepository(workspace, ContentDraft).read(args.draft_id)
    publish_payload = build_prompt_service(args.prompts_dir).run(
        "generate_publish_task",
        {
            "creator_profile": creator.to_dict(),
            "content_draft": draft.to_dict(),
            "planned_publish_time": args.planned_publish_time,
        },
    )
    saved = save_publish_task(workspace, args.draft_id, publish_payload["publish_task"])
    return {"publish_task_id": saved.id, "warnings": publish_payload.get("warnings", [])}


def handle_review_own_post(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    own_post_repo = JsonRepository(workspace, OwnPost)
    own_post = own_post_repo.read(args.own_post_id)
    rule_cards = JsonRepository(workspace, RuleCard).list_all()
    review_payload = build_prompt_service(args.prompts_dir).run(
        "review_own_post",
        {
            "own_post": own_post.to_dict(),
            "related_rule_cards": [rule.to_dict() for rule in rule_cards],
        },
    )
    review_data = dict(review_payload["review_record"])
    review_data["id"] = f"review-from-{own_post.id}"
    review = JsonRepository(workspace, ReviewRecord).upsert(ReviewRecord.from_dict(review_data))
    own_post_repo.update(own_post.id, {"review_record_id": review.id})
    return {"review_record_id": review.id, "warnings": review_payload.get("warnings", [])}


def get_model_type(collection: str) -> type[BaseModel]:
    return MODEL_TYPES[collection]


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def ensure_workspace_dirs(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "reports").mkdir(exist_ok=True)
    for model_type in MODEL_TYPES.values():
        (workspace / model_type.collection_name).mkdir(exist_ok=True)


def read_json_object(path: Path, label: str) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{label} file must contain a JSON object")
    return data


def read_json_items(path: Path, label: str) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise ValueError(f"{label} file must contain a JSON object or a list of objects")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_root_items(path: Path, incoming_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_items: list[dict[str, Any]]
    if path.exists():
        existing_items = read_json_items(path, path.name)
    else:
        existing_items = []

    merged_by_id = {item["id"]: item for item in existing_items if isinstance(item.get("id"), str)}
    for item in incoming_items:
        merged_by_id[item["id"]] = item
    merged = list(merged_by_id.values())
    write_json(path, merged)
    return merged


def workspace_status(workspace: Path) -> dict[str, Any]:
    missing = [file_name for file_name in REQUIRED_WORKSPACE_FILES if not (workspace / file_name).exists()]
    counts = {
        "benchmark_accounts": count_json_items(workspace / "benchmark_account.json"),
        "benchmark_posts": count_json_items(workspace / "benchmark_post.json"),
        "custom_tags": count_json_items(workspace / "custom_tags.json"),
        "feedback_issues": count_feedback_issues(workspace / "validation_feedback.json"),
    }
    return {
        "workspace": str(workspace),
        "ready_for_real_sample_validation": not missing,
        "missing_required_files": missing,
        "counts": counts,
    }


def count_json_items(path: Path) -> int:
    if not path.exists():
        return 0
    return len(read_json_items(path, path.name))


def count_feedback_issues(path: Path) -> int:
    if not path.exists():
        return 0
    data = read_json_object(path, path.name)
    issues = data.get("issues", [])
    return len(issues) if isinstance(issues, list) else 0


def find_inbox_item_by_url(items: list[ContentInboxItem], url: str) -> ContentInboxItem | None:
    for item in items:
        if item.source_url == url:
            return item
    return None


def build_inbox_id(url: str) -> str:
    return "inbox-" + sha1(url.encode("utf-8")).hexdigest()[:12]


def build_prompt_service(prompts_dir: str | Path) -> MockPromptService:
    return MockPromptService(load_contracts(prompts_dir))


def first_record(workspace: Path, model_type: type[BaseModel]) -> BaseModel:
    items = JsonRepository(workspace, model_type).list_all()
    if not items:
        raise ValueError(f"No records found in {model_type.collection_name}")
    return items[0]


def save_rule_cards(workspace: Path, post_id: str, rule_cards: list[dict[str, Any]]) -> list[RuleCard]:
    repo = JsonRepository(workspace, RuleCard)
    saved = []
    for index, rule_data in enumerate(rule_cards, start=1):
        data = dict(rule_data)
        data["id"] = f"rule-card-from-{post_id}-{index}"
        saved.append(repo.upsert(RuleCard.from_dict(data)))
    return saved


def save_topics(workspace: Path, post_id: str, topics: list[dict[str, Any]]) -> list[TopicItem]:
    repo = JsonRepository(workspace, TopicItem)
    saved = []
    for index, topic_data in enumerate(topics, start=1):
        data = dict(topic_data)
        data["id"] = f"topic-from-{post_id}-{index}"
        data["status"] = "idea"
        saved.append(repo.upsert(TopicItem.from_dict(data)))
    return saved


def save_draft(workspace: Path, topic_id: str, draft_data: dict[str, Any]) -> ContentDraft:
    data = dict(draft_data)
    data["id"] = f"draft-from-{topic_id}"
    data["status"] = "draft"
    return JsonRepository(workspace, ContentDraft).upsert(ContentDraft.from_dict(data))


def save_publish_task(workspace: Path, draft_id: str, publish_task_data: dict[str, Any]) -> PublishTask:
    data = dict(publish_task_data)
    data["id"] = f"publish-task-from-{draft_id}"
    data["result_metrics"] = data.get("result_metrics", {})
    data["review_summary"] = data.get("review_summary", "")
    return JsonRepository(workspace, PublishTask).upsert(PublishTask.from_dict(data))


def create_feedback_rule_cards(workspace: Path, issues: list[Any]) -> list[str]:
    repo = JsonRepository(workspace, RuleCard)
    saved_ids: list[str] = []
    existing_count = len(repo.list_all())
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        step = str(issue.get("step") or "custom").strip() or "custom"
        problem = str(issue.get("problem") or "").strip()
        suggestion = str(issue.get("suggestion") or "").strip()
        if not problem and not suggestion:
            continue
        rule_type = feedback_step_to_rule_type(step)
        rule_id = f"feedback-rule-{rule_type}-{len(saved_ids) + existing_count + 1}"
        rule = RuleCard(
            id=rule_id,
            name=f"用户反馈规则：{rule_type}",
            type=rule_type,
            source_ids=["validation_feedback"],
            applicable_scenarios=[step],
            rule_summary=problem or suggestion,
            examples=[],
            risks=[problem] if problem else [],
            adaptation_notes=suggestion or "后续生成时避开同类问题。",
            tags=["feedback"],
            source_type="user_feedback",
            source_note=step,
            user_reason=problem,
            created_from="add-feedback",
            confidence=0.8,
        )
        repo.upsert(rule)
        saved_ids.append(rule.id)
    return saved_ids


def feedback_step_to_rule_type(step: str) -> str:
    mapping = {
        "title": "title",
        "cover": "cover",
        "cover_title": "cover",
        "script": "script",
        "draft": "script",
        "topic": "topic",
        "structure": "structure",
    }
    return mapping.get(step, "operation")


if __name__ == "__main__":
    sys.exit(main())
