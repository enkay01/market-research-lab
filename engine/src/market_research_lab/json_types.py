"""Framework-neutral JSON value types shared across application layers."""

from typing_extensions import TypeAliasType

JsonValue = TypeAliasType(
    "JsonValue",
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"],
)
