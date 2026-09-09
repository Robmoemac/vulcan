"""JSON Schema access and validation (rule V1)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema


@lru_cache(maxsize=8)
def load_schema(name: str) -> dict[str, Any]:
    text = resources.files("vulcan_map.schemas").joinpath(name).read_text(encoding="utf-8")
    return json.loads(text)


def validate_against(schema_name: str, instance: Any) -> list[str]:
    """Return human-readable validation errors; empty list means valid."""
    validator = jsonschema.Draft202012Validator(load_schema(schema_name))
    messages: list[str] = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        location = "/".join(str(p) for p in err.path) or "(root)"
        messages.append(f"{location}: {err.message}")
    return messages
