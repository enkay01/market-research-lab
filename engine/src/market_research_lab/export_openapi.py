"""Write the application OpenAPI description for the browser client generator."""

from __future__ import annotations

import json
from pathlib import Path

from .api import create_app


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    engine_dir = Path(__file__).resolve().parents[2]
    content = json.dumps(create_app().openapi(), indent=2) + "\n"
    (engine_dir / "openapi.json").write_text(content, encoding="utf-8")
    (repo_root / "openapi.json").write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
