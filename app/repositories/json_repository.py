from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Generic, Optional, TypeVar

from app.models.core import Actor, BaseModel, ObjectVersion, now_iso


ModelT = TypeVar("ModelT", bound=BaseModel)

VERSIONED_COLLECTIONS = {"creator-profiles", "rule-cards", "content-drafts"}
COLLECTION_TO_OBJECT_TYPE = {
    "creator-profiles": "creator_profile",
    "rule-cards": "rule_card",
    "content-drafts": "content_draft",
}


class NotFoundError(FileNotFoundError):
    """Raised when a stored record cannot be found."""


class RepositoryVersionConflictError(ValueError):
    """Raised when a conditional update sees a different current version."""


class JsonRepository(Generic[ModelT]):
    def __init__(self, data_dir: Path | str, model_type: type[ModelT]) -> None:
        self.data_dir = Path(data_dir)
        self.model_type = model_type
        self.collection_dir = self.data_dir / model_type.collection_name
        self.collection_dir.mkdir(parents=True, exist_ok=True)

    def create(self, model: ModelT) -> ModelT:
        self._ensure_model_type(model)
        path = self._path_for(model.id)
        if path.exists():
            raise FileExistsError(f"{self.model_type.__name__} already exists: {model.id}")
        self._write(model)
        return model

    def upsert(
        self,
        model: ModelT,
        changed_by: Actor = "system",
        change_note: str = "upsert",
    ) -> ModelT:
        self._ensure_model_type(model)
        path = self._path_for(model.id)
        if not path.exists() or self.model_type.collection_name not in VERSIONED_COLLECTIONS:
            if self.model_type.collection_name in VERSIONED_COLLECTIONS:
                data = model.to_dict()
                data["version"] = 1
                model = self.model_type.from_dict(data)
            self._write(model)
            return model
        current = self.read(model.id)
        self._write_version_snapshot(current, changed_by=changed_by, change_note=change_note)
        data = model.to_dict()
        data["id"] = current.id
        data["created_at"] = current.created_at
        data["updated_at"] = next_updated_at(current.updated_at)
        data["version"] = current.version + 1
        updated = self.model_type.from_dict(data)
        self._write(updated)
        return updated

    def read(self, record_id: str) -> ModelT:
        path = self._path_for(record_id)
        if not path.exists():
            raise NotFoundError(f"{self.model_type.__name__} not found: {record_id}")
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return self.model_type.from_dict(data)

    def update(
        self,
        record_id: str,
        changes: dict[str, object],
        changed_by: Actor = "system",
        change_note: str = "update",
    ) -> ModelT:
        current = self.read(record_id)
        self._write_version_snapshot(current, changed_by=changed_by, change_note=change_note)
        data = current.to_dict()
        data.update(changes)
        data["id"] = record_id
        data["created_at"] = current.created_at
        data["updated_at"] = next_updated_at(current.updated_at)
        data["version"] = current.version + 1
        updated = self.model_type.from_dict(data)
        self._write(updated)
        return updated

    def update_if_version(
        self,
        record_id: str,
        *,
        expected_version: int,
        changes: Optional[dict[str, object]] = None,
        update_fn: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None,
        changed_by: Actor = "system",
        change_note: str = "update-if-version",
    ) -> ModelT:
        current = self.read(record_id)
        if current.version != expected_version:
            raise RepositoryVersionConflictError("record version does not match expected version")

        data = current.to_dict()
        if changes:
            data.update(changes)
        if update_fn:
            data = update_fn(dict(data))
        data["id"] = current.id
        data["created_at"] = current.created_at
        data["updated_at"] = next_updated_at(current.updated_at)
        data["version"] = current.version + 1
        updated = self.model_type.from_dict(data)
        self._write_version_snapshot(current, changed_by=changed_by, change_note=change_note)
        self._write(updated)
        return updated

    def delete(self, record_id: str) -> None:
        path = self._path_for(record_id)
        if not path.exists():
            raise NotFoundError(f"{self.model_type.__name__} not found: {record_id}")
        path.unlink()

    def list_all(self) -> list[ModelT]:
        items = []
        for path in sorted(self.collection_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as file:
                items.append(self.model_type.from_dict(json.load(file)))
        return items

    def _path_for(self, record_id: str) -> Path:
        if "/" in record_id or "\\" in record_id:
            raise ValueError("record_id cannot contain path separators")
        return self.collection_dir / f"{record_id}.json"

    def _write(self, model: ModelT) -> None:
        self._ensure_model_type(model)
        model.validate()
        with self._path_for(model.id).open("w", encoding="utf-8") as file:
            json.dump(model.to_dict(), file, ensure_ascii=False, indent=2)
            file.write("\n")


    def _ensure_model_type(self, model: ModelT) -> None:
        if not isinstance(model, self.model_type):
            raise TypeError(f"Expected {self.model_type.__name__}")

    def _write_version_snapshot(self, model: ModelT, changed_by: Actor, change_note: str) -> None:
        if self.model_type.collection_name not in VERSIONED_COLLECTIONS:
            return
        versions_dir = self.data_dir / ObjectVersion.collection_name
        versions_dir.mkdir(parents=True, exist_ok=True)
        version_id = f"{self.model_type.collection_name}-{model.id}-v{model.version}"
        snapshot = ObjectVersion(
            id=version_id,
            target_object_type=COLLECTION_TO_OBJECT_TYPE[self.model_type.collection_name],
            target_object_id=model.id,
            object_version=model.version,
            snapshot=model.to_dict(),
            changed_by=changed_by,
            change_note=change_note,
        )
        with (versions_dir / f"{version_id}.json").open("w", encoding="utf-8") as file:
            json.dump(snapshot.to_dict(), file, ensure_ascii=False, indent=2)
            file.write("\n")


def next_updated_at(previous: str) -> str:
    current = now_iso()
    if current != previous:
        return current
    try:
        parsed = datetime.strptime(previous, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return current
    return (parsed + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
