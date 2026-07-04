from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from app.models.core import MODEL_TYPES, BaseModel
from app.repositories import JsonRepository
from app.services.real_sample_validation import RealSampleValidator
from app.workflows import BenchmarkToPublishWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PROMPTS_DIR = PROJECT_ROOT / "prompts"


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


def get_model_type(collection: str) -> type[BaseModel]:
    return MODEL_TYPES[collection]


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
