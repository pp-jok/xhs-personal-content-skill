from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha1
from pathlib import Path
from typing import Any, Sequence

from app.analysis import analyze_capture
from app.capture import build_browser_capture_record, build_capture_record
from app.capture.browser.cdp_client import DEFAULT_CDP_URL, capture_xhs_link_with_browser
from app.capture.outcome import build_capture_error_outcome, build_capture_outcome
from app.models.core import (
    MODEL_TYPES,
    Actor,
    BaseModel,
    BenchmarkAccount,
    BenchmarkAnalysis,
    BenchmarkPost,
    CaptureRecord,
    ContentDraft,
    ContentInboxItem,
    ContentQualityReview,
    CreatorProfile,
    CustomTag,
    DecisionRequest,
    ObjectVersion,
    OwnPost,
    PublishTask,
    ProvenanceRecord,
    ReviewRecord,
    RuleCard,
    RuleEvidence,
    TopicItem,
    ValidationError,
    now_iso,
)
from app.repositories import VERSIONED_COLLECTIONS, JsonRepository
from app.quality import build_quality_report
from app.rules import build_rule_and_evidence_from_analysis, check_rule_relations, select_active_rule_cards
from app.services.mock_prompt_service import MockPromptService
from app.services.prompt_contracts import load_contracts
from app.services.real_sample_validation import RealSampleValidator
from app.workflows import BenchmarkToPublishWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PROMPTS_DIR = PROJECT_ROOT / "prompts"
REQUIRED_WORKSPACE_FILES = ("creator_profile.json", "benchmark_account.json", "benchmark_post.json", "custom_tags.json")
OBJECT_TYPE_TO_MODEL: dict[str, type[BaseModel]] = {
    "creator_profile": CreatorProfile,
    "benchmark_account": BenchmarkAccount,
    "benchmark_post": BenchmarkPost,
    "content_inbox": ContentInboxItem,
    "capture_record": CaptureRecord,
    "benchmark_analysis": BenchmarkAnalysis,
    "custom_tag": CustomTag,
    "rule_card": RuleCard,
    "rule_evidence": RuleEvidence,
    "topic_item": TopicItem,
    "content_draft": ContentDraft,
    "content_quality_review": ContentQualityReview,
    "publish_task": PublishTask,
    "own_post": OwnPost,
    "review_record": ReviewRecord,
}
COLLECTION_TO_OBJECT_TYPE = {model.collection_name: object_type for object_type, model in OBJECT_TYPE_TO_MODEL.items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
    except Exception as exc:
        payload: dict[str, Any] = {"ok": False, "error": str(exc)}
        if getattr(args, "handler", None) is handle_capture_xhs_link:
            payload["outcome"] = build_capture_error_outcome(
                error_code="manual_file_invalid" if getattr(args, "manual_file", "") else "capture_failed",
                error_message=str(exc),
            )
        print_json(payload)
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

    provenance_parser = subparsers.add_parser("show-provenance", help="Show provenance records for one object.")
    provenance_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    provenance_parser.add_argument("--target-type", required=True, help="Target object type, for example rule_card.")
    provenance_parser.add_argument("--target-id", required=True, help="Target object id.")
    provenance_parser.set_defaults(handler=handle_show_provenance)

    create_decision_parser = subparsers.add_parser("create-decision", help="Create a pending user decision.")
    create_decision_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    create_decision_parser.add_argument("--target-type", required=True, help="Target object type.")
    create_decision_parser.add_argument("--target-id", required=True, help="Target object id.")
    create_decision_parser.add_argument("--question", required=True, help="Decision question.")
    create_decision_parser.add_argument("--option", action="append", required=True, help="Decision option, repeatable.")
    create_decision_parser.add_argument(
        "--option-outcome",
        action="append",
        default=[],
        help="Map an option label to a resolution, for example '确认使用=confirmed'.",
    )
    create_decision_parser.add_argument("--recommendation", required=True, help="Recommended option.")
    create_decision_parser.add_argument("--recommendation-reason", required=True, help="Reason for recommendation.")
    create_decision_parser.add_argument("--impact", required=True, help="Impact after the decision.")
    create_decision_parser.set_defaults(handler=handle_create_decision)

    list_decisions_parser = subparsers.add_parser("list-decisions", help="List user decisions.")
    list_decisions_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    list_decisions_parser.add_argument("--status", help="Optional decision status filter.")
    list_decisions_parser.set_defaults(handler=handle_list_decisions)

    resolve_decision_parser = subparsers.add_parser("resolve-decision", help="Confirm or reject a pending user decision.")
    resolve_decision_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    resolve_decision_parser.add_argument("--decision-id", required=True, help="DecisionRequest id.")
    resolve_decision_parser.add_argument("--selected-option", required=True, help="Selected decision option.")
    resolve_decision_parser.add_argument("--user-note", default="", help="Optional user note.")
    resolve_decision_parser.set_defaults(handler=handle_resolve_decision)

    versions_parser = subparsers.add_parser("show-object-versions", help="Show stored version snapshots for one object.")
    versions_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    versions_parser.add_argument("--collection", choices=sorted(VERSIONED_COLLECTIONS), required=True, help="Collection name.")
    versions_parser.add_argument("--record-id", required=True, help="Record id.")
    versions_parser.set_defaults(handler=handle_show_object_versions)

    user_context_parser = subparsers.add_parser("show-user-context", help="Show one object with user-facing context sections.")
    user_context_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    user_context_parser.add_argument("--collection", choices=sorted(MODEL_TYPES), required=True, help="Collection name.")
    user_context_parser.add_argument("--record-id", required=True, help="Record id.")
    user_context_parser.set_defaults(handler=handle_show_user_context)

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
    capture_parser.add_argument("--cdp-url", default=DEFAULT_CDP_URL, help="Chrome DevTools Protocol endpoint.")
    capture_parser.set_defaults(handler=handle_capture_xhs_link)

    show_capture_parser = subparsers.add_parser("show-capture-result", help="Show one capture record.")
    show_capture_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    show_capture_parser.add_argument("--capture-id", required=True, help="CaptureRecord id.")
    show_capture_parser.set_defaults(handler=handle_show_capture_result)

    analyze_parser = subparsers.add_parser("analyze-captured-post", help="Analyze one captured post into structured dimensions.")
    analyze_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    analyze_parser.add_argument("--capture-id", required=True, help="CaptureRecord id.")
    analyze_parser.set_defaults(handler=handle_analyze_captured_post)

    promote_parser = subparsers.add_parser("promote-to-benchmark", help="Promote one analyzed inbox item to benchmark account and post records.")
    promote_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    promote_parser.add_argument("--inbox-item-id", required=True, help="ContentInboxItem id.")
    promote_parser.set_defaults(handler=handle_promote_to_benchmark)

    create_rule_parser = subparsers.add_parser("create-rule-from-analysis", help="Create a candidate rule and evidence from one analysis candidate.")
    create_rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    create_rule_parser.add_argument("--analysis-id", required=True, help="BenchmarkAnalysis id.")
    create_rule_parser.add_argument("--candidate-id", required=True, help="Candidate rule id from the analysis.")
    create_rule_parser.set_defaults(handler=handle_create_rule_from_analysis)

    approve_rule_parser = subparsers.add_parser("approve-rule", help="Mark a candidate rule as approved.")
    approve_rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    approve_rule_parser.add_argument("--rule-id", required=True, help="RuleCard id.")
    approve_rule_parser.set_defaults(handler=handle_approve_rule)

    testing_rule_parser = subparsers.add_parser("mark-rule-testing", help="Mark an approved rule as testing.")
    testing_rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    testing_rule_parser.add_argument("--rule-id", required=True, help="RuleCard id.")
    testing_rule_parser.set_defaults(handler=handle_mark_rule_testing)

    rule_result_parser = subparsers.add_parser("record-rule-result", help="Record one rule validation result.")
    rule_result_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    rule_result_parser.add_argument("--rule-id", required=True, help="RuleCard id.")
    rule_result_parser.add_argument("--result", choices=("success", "failure"), required=True, help="Validation result.")
    rule_result_parser.set_defaults(handler=handle_record_rule_result)

    reject_rule_parser = subparsers.add_parser("reject-rule", help="Reject a rule for the current account.")
    reject_rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    reject_rule_parser.add_argument("--rule-id", required=True, help="RuleCard id.")
    reject_rule_parser.add_argument("--reason", required=True, help="Why the rule is rejected.")
    reject_rule_parser.set_defaults(handler=handle_reject_rule)

    deprecate_rule_parser = subparsers.add_parser("deprecate-rule", help="Deprecate a rule replaced by better guidance.")
    deprecate_rule_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    deprecate_rule_parser.add_argument("--rule-id", required=True, help="RuleCard id.")
    deprecate_rule_parser.add_argument("--reason", required=True, help="Why the rule is deprecated.")
    deprecate_rule_parser.add_argument("--superseded-by", help="Replacement rule id.")
    deprecate_rule_parser.set_defaults(handler=handle_deprecate_rule)

    relation_parser = subparsers.add_parser("check-rule-relations", help="Detect duplicate, context-different, and conflicting rules.")
    relation_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    relation_parser.set_defaults(handler=handle_check_rule_relations)

    quality_review_parser = subparsers.add_parser("add-quality-review", help="Add one content quality review.")
    quality_review_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    quality_review_parser.add_argument("--file", required=True, help="Content quality review JSON file.")
    quality_review_parser.set_defaults(handler=handle_add_quality_review)

    quality_report_parser = subparsers.add_parser("generate-quality-report", help="Generate a local quality trend report.")
    quality_report_parser.add_argument("--workspace", required=True, help="Workspace directory.")
    quality_report_parser.add_argument("--period", default="weekly", choices=("weekly", "monthly"), help="Report period.")
    quality_report_parser.set_defaults(handler=handle_generate_quality_report)

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
    if isinstance(model, ProvenanceRecord):
        validate_provenance_record(args.data_dir, model)
    repo = JsonRepository(args.data_dir, model_type)
    if isinstance(model, ProvenanceRecord):
        saved = save_provenance_record(args.data_dir, model, upsert=args.upsert)
    else:
        saved = repo.upsert(model, changed_by="migration", change_note="import-json --upsert") if args.upsert else repo.create(model)
    return {"collection": args.collection, "id": saved.id}


def handle_list(args: argparse.Namespace) -> list[dict[str, Any]]:
    model_type = get_model_type(args.collection)
    repo = JsonRepository(args.data_dir, model_type)
    return [item.to_dict() for item in repo.list_all()]


def handle_show(args: argparse.Namespace) -> dict[str, Any]:
    model_type = get_model_type(args.collection)
    repo = JsonRepository(args.data_dir, model_type)
    return repo.read(args.record_id).to_dict()


def handle_show_provenance(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    target_type = normalize_object_type(args.target_type)
    records = [
        item
        for item in JsonRepository(workspace, ProvenanceRecord).list_all()
        if item.target_object_type == target_type and item.target_object_id == args.target_id
    ]
    return {
        "target": {"object_type": target_type, "object_id": args.target_id},
        "records": [item.to_dict() for item in records],
    }


def handle_create_decision(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    target_type = normalize_object_type(args.target_type)
    assert_target_exists(workspace, target_type, args.target_id)
    option_outcomes = parse_option_outcomes(args.option, args.option_outcome)
    existing = find_existing_decision(workspace, target_type, args.target_id, args.question)
    if existing and existing.status == "pending":
        return {"decision_id": existing.id, "status": existing.status, "target_object_id": existing.target_object_id}
    decision_id = build_decision_id(workspace, target_type, args.target_id, args.question)
    decision = DecisionRequest(
        id=decision_id,
        target_object_type=target_type,
        target_object_id=args.target_id,
        question=args.question,
        options=args.option,
        option_outcomes=option_outcomes,
        recommendation=args.recommendation,
        recommendation_reason=args.recommendation_reason,
        impact=args.impact,
        created_by="codex",
        source_type="codex_recommendation",
        created_from="create-decision",
    )
    saved = JsonRepository(workspace, DecisionRequest).upsert(decision)
    return {"decision_id": saved.id, "status": saved.status, "target_object_id": saved.target_object_id}


def handle_list_decisions(args: argparse.Namespace) -> list[dict[str, Any]]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    decisions = JsonRepository(workspace, DecisionRequest).list_all()
    if args.status:
        decisions = [item for item in decisions if item.status == args.status]
    return [item.to_dict() for item in decisions]


def handle_resolve_decision(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    repo = JsonRepository(workspace, DecisionRequest)
    decision = repo.read(args.decision_id)
    if decision.status != "pending":
        raise ValueError("Only pending decisions can be resolved. Create a new DecisionRequest to change a past decision.")
    selected = args.selected_option
    if selected not in decision.options:
        raise ValueError("selected option must be one of the decision options")

    status = decision.option_outcomes[selected]
    changes = apply_decision_result(workspace, decision, status)
    updated = repo.update(
        decision.id,
        {
            "status": status,
            "selected_option": selected,
            "user_note": args.user_note,
            "resolved_at": now_iso(),
            "resolved_by": "user",
            "resulting_state_changes": changes,
        },
        changed_by="user",
        change_note="user resolved decision",
    )
    return {
        "decision_id": updated.id,
        "status": updated.status,
        "selected_option": updated.selected_option,
        "resulting_state_changes": updated.resulting_state_changes,
    }


def handle_show_object_versions(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    if args.collection not in VERSIONED_COLLECTIONS:
        raise ValueError(f"show-object-versions only supports: {', '.join(sorted(VERSIONED_COLLECTIONS))}")
    target_type = COLLECTION_TO_OBJECT_TYPE[args.collection]
    versions = [
        item
        for item in JsonRepository(workspace, ObjectVersion).list_all()
        if item.target_object_type == target_type and item.target_object_id == args.record_id
    ]
    versions.sort(key=lambda item: item.object_version)
    return {
        "target": {"collection": args.collection, "record_id": args.record_id},
        "versions": [item.to_dict() for item in versions],
    }


def handle_show_user_context(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    model_type = get_model_type(args.collection)
    item = JsonRepository(workspace, model_type).read(args.record_id)
    target_type = COLLECTION_TO_OBJECT_TYPE[args.collection]
    provenance, provenance_diagnostics = collect_provenance_for_object(workspace, item, target_type)
    decisions = [
        decision
        for decision in JsonRepository(workspace, DecisionRequest).list_all()
        if decision.target_object_type == target_type and decision.target_object_id == item.id
    ]
    return {
        "target": {"collection": args.collection, "record_id": args.record_id},
        "sections": build_user_context_sections(item, target_type, provenance, decisions, provenance_diagnostics),
    }


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
    saved = JsonRepository(workspace, CreatorProfile).upsert(profile, changed_by="user", change_note="upsert-profile")
    write_json(workspace / "creator_profile.json", saved.to_dict())
    status = workspace_status(workspace)
    return {"id": saved.id, "workspace": str(workspace), "missing_required_files": status["missing_required_files"]}


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
    if args.manual_file:
        manual_data = read_json_object(Path(args.manual_file), "manual capture")
        capture = build_capture_record(inbox_item, manual_data)
    else:
        capture_id = f"capture-from-{inbox_item.id}"
        browser_result = capture_xhs_link_with_browser(
            source_url=inbox_item.source_url,
            cdp_url=args.cdp_url,
            output_dir=workspace / "captures" / capture_id,
        )
        capture = build_browser_capture_record(inbox_item, browser_result, capture_id=capture_id)
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
        "outcome": build_capture_outcome(saved),
    }


def handle_show_capture_result(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    record = JsonRepository(workspace, CaptureRecord).read(args.capture_id)
    data = record.to_dict()
    data["outcome"] = build_capture_outcome(record)
    return data


def handle_analyze_captured_post(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    capture = JsonRepository(workspace, CaptureRecord).read(args.capture_id)
    analysis = analyze_capture(capture)
    saved = JsonRepository(workspace, BenchmarkAnalysis).upsert(analysis)
    JsonRepository(workspace, ContentInboxItem).update(
        capture.inbox_item_id,
        {
            "status": "analyzed",
            "missing_fields": saved.uncertainties,
            "confidence": saved.confidence,
        },
    )
    return {
        "analysis_id": saved.id,
        "capture_id": saved.capture_id,
        "analysis_template": saved.analysis_template,
        "candidate_rule_ids": saved.candidate_rule_ids,
        "uncertainties": saved.uncertainties,
    }


def handle_promote_to_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    inbox_repo = JsonRepository(workspace, ContentInboxItem)
    inbox_item = inbox_repo.read(args.inbox_item_id)
    capture = find_capture_by_inbox_id(JsonRepository(workspace, CaptureRecord).list_all(), inbox_item.id)
    if capture is None:
        raise ValueError(f"No capture record found for inbox item: {inbox_item.id}")
    analysis_repo = JsonRepository(workspace, BenchmarkAnalysis)
    analysis = find_analysis_by_capture_id(analysis_repo.list_all(), capture.id)
    if analysis is None:
        analysis = analysis_repo.upsert(analyze_capture(capture))

    account_id = f"benchmark-account-from-{inbox_item.id}"
    post_id = f"benchmark-post-from-{inbox_item.id}"
    author_name = str(capture.author.get("name") or "未知可见账号")
    account = BenchmarkAccount(
        id=account_id,
        name=author_name,
        url="",
        niche="待人工确认",
        reason_to_follow=inbox_item.user_reason or inbox_item.user_intent or "由素材收件箱提升为对标账号。",
        learnable_points=analysis.transferable_elements or ["待人工确认"],
        non_learnable_points=analysis.non_transferable_elements or ["待人工确认"],
        tags=[],
        summary="由单条采集内容自动生成的对标账号草稿，需要人工确认。",
        source_type="capture_record",
        source_note=capture.id,
        created_from="promote-to-benchmark",
        confidence=0.6,
    )
    post = BenchmarkPost(
        id=post_id,
        account_id=account.id,
        title=capture.title or "待补充标题",
        url=capture.source_url,
        content_type=capture.content_type,
        cover_text="",
        raw_content=capture.body or "待补充正文",
        metrics=capture.metrics,
        tags=[],
        ai_analysis=analysis.to_dict(),
        borrowable_points=analysis.transferable_elements,
        non_borrowable_points=analysis.non_transferable_elements,
        rule_card_candidates=[
            {
                "id": candidate_id,
                "source_id": analysis.id,
                "evidence": analysis.observable_facts.get("title", ""),
            }
            for candidate_id in analysis.candidate_rule_ids
        ],
        missing_fields=capture.missing_fields,
        source_type="capture_record",
        source_note=capture.id,
        user_reason=inbox_item.user_reason,
        created_from="promote-to-benchmark",
        confidence=analysis.confidence,
    )
    JsonRepository(workspace, BenchmarkAccount).upsert(account)
    JsonRepository(workspace, BenchmarkPost).upsert(post)
    analysis_repo.update(analysis.id, {"benchmark_post_id": post.id})
    inbox_repo.update(inbox_item.id, {"status": "promoted_to_benchmark"})
    return {
        "benchmark_account_id": account.id,
        "benchmark_post_id": post.id,
        "analysis_id": analysis.id,
    }


def handle_create_rule_from_analysis(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    analysis = JsonRepository(workspace, BenchmarkAnalysis).read(args.analysis_id)
    rule, evidence = build_rule_and_evidence_from_analysis(analysis, args.candidate_id)
    saved_rule = JsonRepository(workspace, RuleCard).upsert(
        rule,
        changed_by="codex",
        change_note="create-rule-from-analysis",
    )
    saved_evidence = JsonRepository(workspace, RuleEvidence).upsert(evidence)
    return {"rule_id": saved_rule.id, "evidence_id": saved_evidence.id, "status": saved_rule.status}


def handle_approve_rule(args: argparse.Namespace) -> dict[str, Any]:
    rule = update_rule_status(
        Path(args.workspace),
        args.rule_id,
        {"status": "approved", "strength": "medium"},
        changed_by="user",
        change_note="approve-rule",
    )
    return summarize_rule(rule)


def handle_mark_rule_testing(args: argparse.Namespace) -> dict[str, Any]:
    rule = update_rule_status(Path(args.workspace), args.rule_id, {"status": "testing"}, changed_by="user", change_note="mark-rule-testing")
    return summarize_rule(rule)


def handle_record_rule_result(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    repo = JsonRepository(workspace, RuleCard)
    rule = repo.read(args.rule_id)
    changes: dict[str, Any] = {
        "validation_count": rule.validation_count + 1,
        "last_validated_at": now_iso(),
        "status": "validated" if args.result == "success" else rule.status,
    }
    if args.result == "success":
        changes["success_count"] = rule.success_count + 1
        changes["strength"] = "strong" if rule.success_count + 1 >= 2 else rule.strength
    else:
        changes["failure_count"] = rule.failure_count + 1
    updated = repo.update(rule.id, changes, changed_by="user", change_note=f"record-rule-result {args.result}")
    return summarize_rule(updated)


def handle_reject_rule(args: argparse.Namespace) -> dict[str, Any]:
    rule = update_rule_status(
        Path(args.workspace),
        args.rule_id,
        {"status": "rejected", "deprecated_reason": args.reason},
        changed_by="user",
        change_note="reject-rule",
    )
    return summarize_rule(rule)


def handle_deprecate_rule(args: argparse.Namespace) -> dict[str, Any]:
    supersedes: list[str] = []
    if args.superseded_by:
        supersedes.append(args.superseded_by)
    rule = update_rule_status(
        Path(args.workspace),
        args.rule_id,
        {"status": "deprecated", "deprecated_reason": args.reason, "supersedes": supersedes},
    )
    return summarize_rule(rule)


def handle_check_rule_relations(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    rules = JsonRepository(workspace, RuleCard).list_all()
    return check_rule_relations(rules)


def handle_add_quality_review(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    data = read_json_object(Path(args.file), "content quality review")
    review = ContentQualityReview.from_dict(data)
    saved = JsonRepository(workspace, ContentQualityReview).upsert(review)
    draft_repo = JsonRepository(workspace, ContentDraft)
    draft = draft_repo.read(saved.draft_id)
    quality_summary = dict(draft.quality_review)
    quality_summary.update(
        {
            "latest_review_id": saved.id,
            "account_fit_score": saved.account_fit_score,
            "publishability_score": saved.publishability_score,
            "major_rewrite_required": saved.major_rewrite_required,
        }
    )
    draft_repo.update(draft.id, {"quality_review": quality_summary})
    return {"id": saved.id, "draft_id": saved.draft_id, "major_rewrite_required": saved.major_rewrite_required}


def handle_generate_quality_report(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    reviews = JsonRepository(workspace, ContentQualityReview).list_all()
    rules = JsonRepository(workspace, RuleCard).list_all()
    metrics, report = build_quality_report(args.period, reviews, rules)
    report_path = workspace / "reports" / f"quality_report_{args.period}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    return {"period": args.period, "report_path": str(report_path), "metrics": metrics}


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
    active_rule_cards = select_active_rule_cards(rule_cards)

    topic_payload = build_prompt_service(args.prompts_dir).run(
        "generate_topic_pool",
        {
            "creator_profile": creator.to_dict(),
            "custom_tags": [tag.to_dict() for tag in tags],
            "rule_cards": [rule.to_dict() for rule in active_rule_cards],
            "reference_posts": [post.to_dict()],
            "topic_count": args.topic_count,
        },
    )
    saved = save_topics(workspace, post.id, topic_payload["topics"])
    warnings = list(topic_payload.get("warnings", []))
    if rule_cards and not active_rule_cards:
        warnings.append("存在未确认候选规则，已从正式选题生成上下文中排除。")
    return {"topic_ids": [topic.id for topic in saved], "warnings": warnings}


def handle_generate_draft(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    topic = JsonRepository(workspace, TopicItem).read(args.topic_id)
    creator = first_record(workspace, CreatorProfile)
    tags = JsonRepository(workspace, CustomTag).list_all()
    rule_cards = select_active_rule_cards(JsonRepository(workspace, RuleCard).list_all())
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
    rule_cards = select_active_rule_cards(JsonRepository(workspace, RuleCard).list_all())
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


def find_capture_by_inbox_id(items: list[CaptureRecord], inbox_item_id: str) -> CaptureRecord | None:
    for item in items:
        if item.inbox_item_id == inbox_item_id:
            return item
    return None


def find_analysis_by_capture_id(items: list[BenchmarkAnalysis], capture_id: str) -> BenchmarkAnalysis | None:
    for item in items:
        if item.capture_id == capture_id:
            return item
    return None


def update_rule_status(
    workspace: Path,
    rule_id: str,
    changes: dict[str, Any],
    changed_by: Actor = "system",
    change_note: str = "update-rule-status",
) -> RuleCard:
    ensure_workspace_dirs(workspace)
    return JsonRepository(workspace, RuleCard).update(rule_id, changes, changed_by=changed_by, change_note=change_note)


def summarize_rule(rule: RuleCard) -> dict[str, Any]:
    return {
        "rule_id": rule.id,
        "status": rule.status,
        "strength": rule.strength,
        "validation_count": rule.validation_count,
        "success_count": rule.success_count,
        "failure_count": rule.failure_count,
    }


def build_inbox_id(url: str) -> str:
    return "inbox-" + sha1(url.encode("utf-8")).hexdigest()[:12]


def normalize_object_type(value: str) -> str:
    if value not in OBJECT_TYPE_TO_MODEL:
        raise ValueError(f"Unsupported target object type: {value}")
    return value


def assert_target_exists(workspace: Path, target_type: str, target_id: str) -> BaseModel:
    model_type = OBJECT_TYPE_TO_MODEL[target_type]
    return JsonRepository(workspace, model_type).read(target_id)


def validate_provenance_record(workspace: str | Path, record: ProvenanceRecord) -> None:
    workspace_path = Path(workspace)
    target = assert_target_exists(workspace_path, record.target_object_type, record.target_object_id)
    source = assert_target_exists(workspace_path, record.source_object_type, record.source_object_id)
    if record.target_object_id != target.id:
        raise ValueError("provenance target does not match the stored target object")
    if record.source_object_id != source.id:
        raise ValueError("provenance source does not match the stored source object")
    if record.source_version > source.version:
        versions = JsonRepository(workspace_path, ObjectVersion).list_all()
        has_snapshot = any(
            item.target_object_type == record.source_object_type
            and item.target_object_id == record.source_object_id
            and item.object_version == record.source_version
            for item in versions
        )
        if not has_snapshot:
            raise ValueError("provenance source_version does not exist")


def save_provenance_record(workspace: str | Path, record: ProvenanceRecord, upsert: bool = True) -> ProvenanceRecord:
    validate_provenance_record(workspace, record)
    repo = JsonRepository(workspace, ProvenanceRecord)
    return repo.upsert(record) if upsert else repo.create(record)


def parse_option_outcomes(options: list[str], raw_mappings: list[str]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for raw_mapping in raw_mappings:
        if "=" not in raw_mapping:
            raise ValueError("option outcome must use option=resolution format")
        option, outcome = raw_mapping.split("=", 1)
        option = option.strip()
        outcome = outcome.strip()
        if option not in options:
            raise ValueError("option outcome key must be one of the decision options")
        if outcome not in {"confirmed", "rejected", "cancelled", "superseded"}:
            raise ValueError("option outcome must be confirmed, rejected, cancelled, or superseded")
        mappings[option] = outcome
    if mappings:
        missing = [option for option in options if option not in mappings]
        if missing:
            raise ValueError(f"missing option outcomes for: {', '.join(missing)}")
        return mappings
    # Backward compatibility for the original English CLI options. New labels should pass --option-outcome.
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
    mappings = {option: legacy[option] for option in options if option in legacy}
    if len(mappings) != len(options):
        raise ValueError("custom decision options require explicit --option-outcome mappings")
    return mappings


def find_existing_decision(workspace: Path, target_type: str, target_id: str, question: str) -> DecisionRequest | None:
    for decision in JsonRepository(workspace, DecisionRequest).list_all():
        if (
            decision.target_object_type == target_type
            and decision.target_object_id == target_id
            and decision.question == question
            and decision.status == "pending"
        ):
            return decision
    return None


def build_decision_id(workspace: Path, target_type: str, target_id: str, question: str) -> str:
    key = f"{target_type}:{target_id}:{question}"
    base_id = "decision-" + sha1(key.encode("utf-8")).hexdigest()[:12]
    existing_ids = {item.id for item in JsonRepository(workspace, DecisionRequest).list_all()}
    if base_id not in existing_ids:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}-{suffix}"


def apply_decision_result(workspace: Path, decision: DecisionRequest, resolution: str) -> list[dict[str, Any]]:
    if decision.target_object_type != "rule_card":
        return []
    repo = JsonRepository(workspace, RuleCard)
    if resolution == "confirmed":
        target_status = "approved"
    elif resolution == "rejected":
        target_status = "rejected"
    else:
        return []
    rule = repo.update(
        decision.target_object_id,
        {"status": target_status},
        changed_by="user",
        change_note=f"decision {decision.id} resolved as {resolution}",
    )
    return [
        {
            "target_object_type": decision.target_object_type,
            "target_object_id": decision.target_object_id,
            "field": "status",
            "value": rule.status,
        }
    ]


def build_user_context_sections(
    item: BaseModel,
    target_type: str,
    provenance: list[ProvenanceRecord],
    decisions: list[DecisionRequest],
    provenance_diagnostics: list[str] | None = None,
) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {
        "【已有资料】": [],
        "【规则约束】": [],
        "【规则状态】": [],
        "【客观数据】": [],
        "【Codex 判断】": [],
        "【Codex 生成】": [],
        "【需要你决定】": [],
        "【已由你决定】": [],
        "【信息不足】": [],
    }
    data = item.to_dict()
    label = str(data.get("name") or data.get("title") or item.id)
    if item.created_by == "user" and not any(record.artifact_nature in {"inference", "generated"} for record in provenance):
        sections["【已有资料】"].append(f"{label}（版本 {item.version}）")
    elif item.created_by == "codex":
        sections["【Codex 生成】" if target_type == "content_draft" else "【Codex 判断】"].append(f"{label}（版本 {item.version}）")
    elif item.created_by == "system":
        sections["【客观数据】"].append(f"{label}（版本 {item.version}）")
    else:
        sections["【已有资料】"].append(f"{label}（版本 {item.version}）")
    if item.missing_fields:
        sections["【信息不足】"].extend(item.missing_fields)
    if provenance_diagnostics:
        sections["【信息不足】"].extend(provenance_diagnostics)

    if isinstance(item, RuleCard):
        sections["【规则约束】"].append(item.rule_summary)
        has_pending_decision = any(decision.status == "pending" for decision in decisions)
        user_decision_state = get_user_decision_state_for_rule(item, decisions, provenance)
        if user_decision_state == "conflicting":
            sections["【信息不足】"].append("当前规则状态与用户历史决定不一致。")
        if item.status == "candidate" and not has_pending_decision:
            sections["【需要你决定】"].append("候选规则，需要确认后才会长期生效。")
        elif item.status in {"approved", "testing", "validated"}:
            if user_decision_state == "confirmed":
                sections["【已由你决定】"].append(f"规则当前状态：{item.status}")
            elif user_decision_state != "conflicting":
                sections["【规则状态】"].append(f"当前状态：{item.status}")
        elif item.status in {"rejected", "deprecated"}:
            if user_decision_state in {"rejected", "cancelled", "superseded"}:
                sections["【已由你决定】"].append(f"这条规则已标记为：{item.status}")
            elif user_decision_state != "conflicting":
                sections["【规则状态】"].append(f"当前状态：{item.status}")

    for record in provenance:
        if record.artifact_nature == "fact":
            sections["【客观数据】"].append(record.note or f"来自 {record.source_object_type}")
        elif record.artifact_nature in {"inference", "recommendation"}:
            sections["【Codex 判断】"].append(record.note or f"由 {record.actor} 产生")
        elif record.artifact_nature == "generated":
            sections["【Codex 生成】"].append(record.note or f"由 {record.actor} 生成")

    for decision in decisions:
        if decision.status == "pending":
            sections["【需要你决定】"].append(decision.question)
        elif (
            decision.status in {"confirmed", "rejected", "cancelled", "superseded"}
            and decision.resolved_by == "user"
            and not (isinstance(item, RuleCard) and not decision_matches_rule_status(item.status, decision.status))
        ):
            sections["【已由你决定】"].append(f"{decision.question} -> {decision.selected_option}")

    return sections


def get_user_decision_state_for_rule(
    rule: RuleCard,
    decisions: list[DecisionRequest],
    provenance: list[ProvenanceRecord],
) -> str:
    user_decisions = [
        decision.status
        for decision in decisions
        if decision.resolved_by == "user" and decision.status in {"confirmed", "rejected", "cancelled", "superseded"}
    ]
    if user_decisions:
        if any(decision_matches_rule_status(rule.status, status) for status in user_decisions):
            for status in user_decisions:
                if decision_matches_rule_status(rule.status, status):
                    return status
        return "conflicting"
    if rule.status in {"approved", "testing", "validated"} and any(
        record.actor == "user" and record.artifact_nature == "decision" for record in provenance
    ):
        return "confirmed"
    return "none"


def decision_matches_rule_status(rule_status: str, decision_status: str) -> bool:
    if rule_status in {"approved", "testing", "validated"}:
        return decision_status == "confirmed"
    if rule_status == "rejected":
        return decision_status == "rejected"
    if rule_status == "deprecated":
        return decision_status in {"cancelled", "superseded"}
    if rule_status == "candidate":
        return decision_status == "pending"
    return False


def collect_provenance_for_object(
    workspace: Path,
    item: BaseModel,
    target_type: str,
) -> tuple[list[ProvenanceRecord], list[str]]:
    repo = JsonRepository(workspace, ProvenanceRecord)
    by_id = {record.id: record for record in repo.list_all()}
    diagnostics: list[str] = []
    selected: list[ProvenanceRecord] = []
    if item.provenance_refs:
        for ref in item.provenance_refs:
            record = by_id.get(ref)
            if record is None:
                diagnostics.append(f"来源记录缺失：{ref}")
                continue
            if record.target_object_type != target_type or record.target_object_id != item.id:
                diagnostics.append(f"来源记录目标不匹配：{ref}")
                continue
            selected.append(record)
        return selected, diagnostics
    selected = [
        record
        for record in by_id.values()
        if record.target_object_type == target_type and record.target_object_id == item.id
    ]
    return selected, diagnostics


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
        data = enforce_rule_safety_defaults(data)
        saved.append(repo.upsert(RuleCard.from_dict(data), changed_by=data["created_by"], change_note="generate-rule-cards"))
    return saved


def enforce_rule_safety_defaults(rule_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(rule_data)
    created_by = data.get("created_by") or "codex"
    has_structured_user_confirmation = (
        created_by == "user"
        and data.get("feedback_nature") == "explicit_user_rule"
        and data.get("user_confirmed") is True
    )
    data["created_by"] = created_by
    if not has_structured_user_confirmation:
        data["status"] = "candidate"
        if created_by != "user":
            data["created_by"] = "codex"
    return {key: value for key, value in data.items() if key in RuleCard.__dataclass_fields__}


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
    data.setdefault("created_by", "codex")
    return JsonRepository(workspace, ContentDraft).upsert(
        ContentDraft.from_dict(data),
        changed_by="codex",
        change_note="generate-draft",
    )


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
        feedback_nature = normalize_feedback_nature(issue.get("feedback_nature"))
        user_confirmed = issue.get("user_confirmed") is True
        rule_type = feedback_step_to_rule_type(step)
        rule_id = f"feedback-rule-{rule_type}-{len(saved_ids) + existing_count + 1}"
        explicit_instruction = feedback_nature == "explicit_user_rule" and user_confirmed
        status = "approved" if explicit_instruction else "candidate"
        created_by: Actor = "user" if explicit_instruction else "codex"
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
            status=status,
            source_type="user_feedback",
            source_note=step,
            user_reason=problem,
            created_from="add-feedback",
            confidence=0.8,
            created_by=created_by,
        )
        saved = repo.upsert(rule, changed_by=created_by, change_note="add-feedback")
        if explicit_instruction:
            create_feedback_confirmation_decision(workspace, saved, step, problem, suggestion)
        elif feedback_nature in {"inferred_preference", "candidate_rule", "uncertain", ""}:
            create_feedback_candidate_decision(workspace, saved, step)
        saved_ids.append(rule.id)
    return saved_ids


def normalize_feedback_nature(value: Any) -> str:
    if value in {"explicit_user_rule", "content_specific_feedback", "inferred_preference", "candidate_rule", "uncertain"}:
        return str(value)
    return ""


def create_feedback_candidate_decision(workspace: Path, rule: RuleCard, step: str) -> DecisionRequest:
    decision = DecisionRequest(
        id=build_decision_id(workspace, "rule_card", rule.id, "是否确认这条反馈推导规则？"),
        target_object_type="rule_card",
        target_object_id=rule.id,
        question="是否确认这条反馈推导规则？",
        options=["confirm", "reject"],
        option_outcomes={"confirm": "confirmed", "reject": "rejected"},
        recommendation="confirm",
        recommendation_reason="这条规则来自反馈推导，需要你确认后才长期生效。",
        impact="确认后进入长期规则；拒绝后不参与后续生成。",
        created_by="codex",
        source_type="user_feedback",
        source_note=step,
        created_from="add-feedback",
    )
    return JsonRepository(workspace, DecisionRequest).upsert(
        decision,
        changed_by="codex",
        change_note="add-feedback candidate decision",
    )


def create_feedback_confirmation_decision(
    workspace: Path,
    rule: RuleCard,
    step: str,
    problem: str,
    suggestion: str,
) -> DecisionRequest:
    decision = DecisionRequest(
        id=build_decision_id(workspace, "rule_card", rule.id, "是否将这条反馈作为长期规则？"),
        target_object_type="rule_card",
        target_object_id=rule.id,
        question="是否将这条反馈作为长期规则？",
        options=["确认长期使用", "不作为长期规则"],
        option_outcomes={"确认长期使用": "confirmed", "不作为长期规则": "rejected"},
        recommendation="确认长期使用",
        recommendation_reason="用户结构化输入已明确这是长期规则。",
        impact="确认后进入长期规则。",
        status="confirmed",
        selected_option="确认长期使用",
        resulting_state_changes=[{"target_object_type": "rule_card", "target_object_id": rule.id, "field": "status", "value": "approved"}],
        resolved_at=now_iso(),
        resolved_by="user",
        created_by="codex",
        source_type="user_feedback",
        source_note=step,
        created_from="add-feedback",
    )
    saved_decision = JsonRepository(workspace, DecisionRequest).upsert(
        decision,
        changed_by="user",
        change_note="add-feedback explicit user rule decision",
    )
    provenance_note = f"step={step}; problem={problem}; suggestion={suggestion}".strip()
    save_provenance_record(
        workspace,
        ProvenanceRecord(
            id=f"provenance-explicit-user-rule-{rule.id}",
            target_object_type="rule_card",
            target_object_id=rule.id,
            source_object_type="rule_card",
            source_object_id=rule.id,
            source_version=rule.version,
            actor="user",
            artifact_nature="decision",
            method="explicit-user-rule-input",
            note=provenance_note,
            created_by="system",
            source_type="user_feedback",
            source_note=step,
            created_from="add-feedback",
        ),
    )
    return saved_decision


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
