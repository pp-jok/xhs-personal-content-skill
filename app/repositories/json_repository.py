from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar

from app.models.core import BaseModel, now_iso


ModelT = TypeVar("ModelT", bound=BaseModel)


class NotFoundError(FileNotFoundError):
    """Raised when a stored record cannot be found."""


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

    def upsert(self, model: ModelT) -> ModelT:
        self._ensure_model_type(model)
        self._write(model)
        return model

    def read(self, record_id: str) -> ModelT:
        path = self._path_for(record_id)
        if not path.exists():
            raise NotFoundError(f"{self.model_type.__name__} not found: {record_id}")
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return self.model_type.from_dict(data)

    def update(self, record_id: str, changes: dict[str, object]) -> ModelT:
        current = self.read(record_id)
        data = current.to_dict()
        data.update(changes)
        data["id"] = record_id
        data["created_at"] = current.created_at
        data["updated_at"] = now_iso()
        updated = self.model_type.from_dict(data)
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
