from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.models.core import MODEL_TYPES, BaseModel, BenchmarkAccount, BenchmarkPost, CreatorProfile, CustomTag
from app.repositories import JsonRepository
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
    return {"workspace": str(workspace), "issue_count": len(merged.get("issues", []))}


def handle_validate_workspace(args: argparse.Namespace) -> dict[str, Any]:
    workspace = Path(args.workspace)
    ensure_workspace_dirs(workspace)
    return workspace_status(workspace)


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


if __name__ == "__main__":
    sys.exit(main())
