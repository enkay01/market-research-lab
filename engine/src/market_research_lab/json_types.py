"""Shared JSON-compatible contracts for validated boundaries and persistence."""

from __future__ import annotations

from typing_extensions import TypeAliasType

JsonScalar = None | bool | int | float | str
JsonValue = TypeAliasType(
    "JsonValue",
    JsonScalar | list["JsonValue"] | dict[str, "JsonValue"],
)
JsonObject = dict[str, JsonValue]
