from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.models.core import ContentAsset, ValidationError
from app.repositories import RepositoryVersionConflictError


STATUS_LABELS = {
    "candidate": "候选",
    "active": "已激活",
    "deprecated": "已废弃",
}

ASSET_TYPE_LABELS = {
    "title_pattern": "标题公式",
    "cover_structure": "封面结构",
    "opening_template": "开头模板",
    "body_structure": "正文结构",
    "cta_template": "行动引导模板",
    "comparison_framework": "对比表达框架",
    "case_framework": "案例讲述框架",
    "image_text_structure": "图文页结构",
    "topic_framework": "选题框架",
}


class ContentAssetRepository(Protocol):
    def read(self, record_id: str) -> ContentAsset:
        ...

    def update_if_version(
        self,
        record_id: str,
        *,
        expected_version: int,
        changes=None,
        update_fn=None,
        changed_by: str = "system",
        change_note: str = "update",
    ) -> ContentAsset:
        ...


class ContentAssetLifecycleError(ValueError):
    """Raised when a content asset lifecycle transition cannot be safely applied."""


@dataclass(frozen=True)
class ContentAssetLifecycleResult:
    asset: ContentAsset
    previous_status: str
    new_status: str
    previous_version: int
    new_version: int
    user_summary: str
    machine_summary: dict[str, Any]


def activate_content_asset(
    repository: ContentAssetRepository,
    *,
    asset_id: str,
    expected_version: int,
    actor: str,
) -> ContentAssetLifecycleResult:
    return transition_content_asset(
        repository,
        asset_id=asset_id,
        expected_version=expected_version,
        actor=actor,
        operation="activate",
        allowed_from={"candidate"},
        target_status="active",
    )


def deprecate_content_asset(
    repository: ContentAssetRepository,
    *,
    asset_id: str,
    expected_version: int,
    actor: str,
) -> ContentAssetLifecycleResult:
    return transition_content_asset(
        repository,
        asset_id=asset_id,
        expected_version=expected_version,
        actor=actor,
        operation="deprecate",
        allowed_from={"candidate", "active"},
        target_status="deprecated",
    )


def transition_content_asset(
    repository: ContentAssetRepository,
    *,
    asset_id: str,
    expected_version: int,
    actor: str,
    operation: str,
    allowed_from: set[str],
    target_status: str,
) -> ContentAssetLifecycleResult:
    validate_inputs(asset_id=asset_id, expected_version=expected_version, actor=actor)
    previous_status = ""
    previous_version = 0

    def apply_transition(current_data: dict[str, Any]) -> dict[str, Any]:
        nonlocal previous_status, previous_version
        current = read_asset_data(current_data)
        validate_transition(current, expected_version=expected_version, allowed_from=allowed_from, target_status=target_status)
        previous_status = current.status
        previous_version = current.version
        updated_data = current.to_dict()
        updated_data["status"] = target_status
        return updated_data

    try:
        updated = repository.update_if_version(
            asset_id.strip(),
            expected_version=expected_version,
            update_fn=apply_transition,
            changed_by=actor.strip(),
            change_note=f"content-asset-{operation}",
        )
    except ContentAssetLifecycleError:
        raise
    except FileNotFoundError as exc:
        raise ContentAssetLifecycleError("内容资产不存在，请确认后重试。") from exc
    except RepositoryVersionConflictError as exc:
        raise ContentAssetLifecycleError("版本冲突：内容资产已变化，请重新查看后再操作。") from exc
    except (ValidationError, ValueError, TypeError) as exc:
        raise ContentAssetLifecycleError("内容资产数据无效，暂不能执行生命周期操作。") from exc
    except Exception as exc:
        raise ContentAssetLifecycleError("内容资产更新失败，本次未完成。") from exc

    return ContentAssetLifecycleResult(
        asset=updated,
        previous_status=previous_status,
        new_status=updated.status,
        previous_version=previous_version,
        new_version=updated.version,
        user_summary=build_user_summary(operation, updated, previous_status, previous_version),
        machine_summary=build_machine_summary(operation, updated, previous_status, previous_version, actor.strip()),
    )


def validate_inputs(*, asset_id: str, expected_version: int, actor: str) -> None:
    if not isinstance(asset_id, str) or not asset_id.strip() or "/" in asset_id or "\\" in asset_id:
        raise ContentAssetLifecycleError("输入参数无效：内容资产标识不可为空或包含路径分隔符。")
    if type(expected_version) is not int or expected_version < 1:
        raise ContentAssetLifecycleError("输入参数无效：expected version 必须是大于等于 1 的整数。")
    if not isinstance(actor, str) or not actor.strip():
        raise ContentAssetLifecycleError("输入参数无效：actor 不能为空。")
    if len(actor.strip()) > 256:
        raise ContentAssetLifecycleError("输入参数无效：actor 长度不能超过 256 个字符。")


def read_asset(repository: ContentAssetRepository, asset_id: str) -> ContentAsset:
    try:
        asset = repository.read(asset_id.strip())
    except FileNotFoundError as exc:
        raise ContentAssetLifecycleError("内容资产不存在，请确认后重试。") from exc
    except (ValidationError, ValueError, TypeError) as exc:
        raise ContentAssetLifecycleError("内容资产数据无效，暂不能执行生命周期操作。") from exc
    if not isinstance(asset, ContentAsset):
        raise ContentAssetLifecycleError("内容资产数据无效，暂不能执行生命周期操作。")
    try:
        asset.validate()
    except ValidationError as exc:
        raise ContentAssetLifecycleError("内容资产数据无效，暂不能执行生命周期操作。") from exc
    return asset


def read_asset_data(data: dict[str, Any]) -> ContentAsset:
    try:
        asset = ContentAsset.from_dict(data)
        asset.validate()
    except (ValidationError, ValueError, TypeError) as exc:
        raise ContentAssetLifecycleError("内容资产数据无效，暂不能执行生命周期操作。") from exc
    return asset


def validate_transition(
    asset: ContentAsset,
    *,
    expected_version: int,
    allowed_from: set[str],
    target_status: str,
) -> None:
    if asset.version != expected_version:
        raise ContentAssetLifecycleError("版本冲突：内容资产已变化，请重新查看后再操作。")
    if asset.status == target_status or asset.status not in allowed_from:
        raise ContentAssetLifecycleError("当前状态不能执行该操作，请重新查看内容资产状态。")


def build_user_summary(operation: str, asset: ContentAsset, previous_status: str, previous_version: int) -> str:
    status_line = f"原状态：{STATUS_LABELS[previous_status]}；新状态：{STATUS_LABELS[asset.status]}。"
    version_line = f"版本：{previous_version} → {asset.version}。"
    type_line = f"类型：{ASSET_TYPE_LABELS[asset.asset_type]}。"
    name_line = f"名称：{asset.name}。"
    if operation == "activate":
        return "\n".join(
            [
                "已激活 1 个内容资产。",
                type_line,
                name_line,
                status_line,
                version_line,
                "该操作只改变资产治理状态。",
                "当前仍未自动进入生成上下文，也不会自动参与选题或草稿生成。",
                "后续 PR-5D 才会实现对已激活资产的显式引用。",
            ]
        )
    return "\n".join(
        [
            "已废弃 1 个内容资产。",
            type_line,
            name_line,
            status_line,
            version_line,
            "已废弃资产不能用于未来显式生成引用。",
            "历史记录仍保留，既有历史生成结果不会被修改。",
        ]
    )


def build_machine_summary(
    operation: str,
    asset: ContentAsset,
    previous_status: str,
    previous_version: int,
    actor: str,
) -> dict[str, Any]:
    return {
        "asset_id": asset.id,
        "asset_type": asset.asset_type,
        "previous_status": previous_status,
        "new_status": asset.status,
        "previous_version": previous_version,
        "new_version": asset.version,
        "actor": actor,
        "operation": operation,
        "generation_context_connected": False,
        "decision_request_created": False,
    }
