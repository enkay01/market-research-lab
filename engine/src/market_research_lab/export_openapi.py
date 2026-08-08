"""Write the application OpenAPI description for the browser client generator."""

from __future__ import annotations

import json
from pathlib import Path

from .api import create_app


def main() -> None:
    target = Path(__file__).resolve().parents[3] / "engine" / "openapi.json"
    target.write_text(json.dumps(create_app().openapi(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
