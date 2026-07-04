from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.core import ValidationError, require_dict, require_list, require_text


REQUIRED_CONTRACT_FIELDS = [
    "id",
    "purpose",
    "input_schema",
    "output_schema",
    "constraints",
    "quality_standards",
    "failure_handling",
]


@dataclass(frozen=True)
class PromptContract:
    id: str
    purpose: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    constraints: list[str]
    quality_standards: list[str]
    failure_handling: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptContract":
        require_dict(data, "prompt contract")
        missing = [field for field in REQUIRED_CONTRACT_FIELDS if field not in data]
        if missing:
            raise ValidationError(f"Missing prompt contract fields: {', '.join(missing)}")

        contract = cls(
            id=data["id"],
            purpose=data["purpose"],
            input_schema=data["input_schema"],
            output_schema=data["output_schema"],
            constraints=data["constraints"],
            quality_standards=data["quality_standards"],
            failure_handling=data["failure_handling"],
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        require_text(self.id, "id")
        require_text(self.purpose, "purpose")
        validate_schema(self.input_schema, "input_schema")
        validate_schema(self.output_schema, "output_schema")
        validate_required_object_schema(self.input_schema, "input_schema")
        validate_required_object_schema(self.output_schema, "output_schema")
        require_list(self.constraints, "constraints")
        require_list(self.quality_standards, "quality_standards")
        for item in self.constraints:
            require_text(item, "constraints item")
        for item in self.quality_standards:
            require_text(item, "quality_standards item")
        require_dict(self.failure_handling, "failure_handling")
        require_text(self.failure_handling.get("on_missing_input", ""), "failure_handling.on_missing_input")
        require_text(self.failure_handling.get("on_low_confidence", ""), "failure_handling.on_low_confidence")


def load_contract(path: Path | str) -> PromptContract:
    with Path(path).open("r", encoding="utf-8") as file:
        return PromptContract.from_dict(json.load(file))


def load_contracts(directory: Path | str) -> dict[str, PromptContract]:
    contracts = {}
    for path in sorted(Path(directory).glob("*.json")):
        contract = load_contract(path)
        if contract.id in contracts:
            raise ValidationError(f"Duplicate prompt contract id: {contract.id}")
        contracts[contract.id] = contract
    return contracts


def validate_schema(schema: dict[str, Any], field_name: str) -> None:
    require_dict(schema, field_name)
    schema_type = schema.get("type")
    if schema_type not in {"object", "array", "string", "number", "integer", "boolean"}:
        raise ValidationError(f"{field_name}.type must be a supported JSON type")

    if schema_type == "object":
        require_dict(schema.get("properties", {}), f"{field_name}.properties")
        require_list(schema.get("required", []), f"{field_name}.required")
        for key, nested_schema in schema.get("properties", {}).items():
            require_text(key, f"{field_name}.properties key")
            validate_schema(nested_schema, f"{field_name}.{key}")

    if schema_type == "array":
        validate_schema(schema.get("items", {}), f"{field_name}.items")


def validate_required_object_schema(schema: dict[str, Any], field_name: str) -> None:
    if schema.get("type") != "object":
        raise ValidationError(f"{field_name} must be an object schema")
    required = schema.get("required", [])
    if not required:
        raise ValidationError(f"{field_name}.required cannot be empty")
