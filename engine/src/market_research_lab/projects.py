"""Durable Project files and immutable Definition Revisions."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .json_types import JsonValue


class ProjectNotFoundError(Exception):
    """Raised when a requested Project does not exist."""


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    created_at: str


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "definition"


class ProjectStore:
    """Owns Project paths, atomic file writes, revisions, and Run directories."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    @property
    def projects_root(self) -> Path:
        return self.workspace_root / "projects"

    def create_project(self, name: str) -> Project:
        project = Project(id=str(uuid4()), name=name, created_at=_timestamp())
        directory = self._directory(project.id)
        directory.mkdir(parents=True, exist_ok=False)
        self._write_json(directory / "project.json", asdict(project))
        self._write_json(directory / "watchlist.json", {"security_ids": []})
        return project

    def get_project(self, project_id: str) -> Project:
        path = self._directory(project_id) / "project.json"
        if not path.is_file():
            raise ProjectNotFoundError(project_id)
        return Project(**json.loads(path.read_text(encoding="utf-8")))

    def rename_project(self, project_id: str, new_name: str) -> Project:
        project = self.get_project(project_id)
        updated_project = Project(id=project.id, name=new_name, created_at=project.created_at)
        self._write_json(self._directory(project_id) / "project.json", asdict(updated_project))
        return updated_project

    def delete_project(self, project_id: str) -> None:
        path = self._directory(project_id)
        if not (path / "project.json").is_file():
            raise ProjectNotFoundError(project_id)
        shutil.rmtree(path)

    def list_projects(self) -> list[Project]:
        if not self.projects_root.exists():
            return []
        return sorted(
            (
                self.get_project(entry.name)
                for entry in self.projects_root.iterdir()
                if entry.is_dir()
            ),
            key=lambda project: project.created_at,
            reverse=True,
        )

    def save_revision(
        self, project_id: str, *, kind: str, name: str, definition: dict[str, JsonValue]
    ) -> str:
        self.get_project(project_id)
        definition_root = self._directory(project_id) / "definitions" / kind / _slug(name)
        definition_root.mkdir(parents=True, exist_ok=True)
        revision = f"v{self._next_revision_number(definition_root)}"
        revision_directory = definition_root / revision
        temporary_directory = definition_root / f".{revision}-{uuid4().hex}.tmp"
        temporary_directory.mkdir()
        self._write_json(
            temporary_directory / "definition.json",
            {
                "name": name,
                "revision": revision,
                "saved_at": _timestamp(),
                "definition": definition,
            },
        )
        os.replace(temporary_directory, revision_directory)
        self.save_draft(project_id, kind=kind, name=name, definition=definition)
        return revision

    def save_draft(
        self, project_id: str, *, kind: str, name: str, definition: dict[str, JsonValue]
    ) -> None:
        self.get_project(project_id)
        definition_root = self._directory(project_id) / "definitions" / kind / _slug(name)
        self._write_json(
            definition_root / "draft" / "definition.json",
            {"name": name, "definition": definition, "saved_at": _timestamp()},
        )

    def read_draft(self, project_id: str, *, kind: str, name: str) -> dict[str, JsonValue]:
        self.get_project(project_id)
        draft_path = (
            self._directory(project_id)
            / "definitions"
            / kind
            / _slug(name)
            / "draft"
            / "definition.json"
        )
        if not draft_path.is_file():
            raise ProjectNotFoundError(project_id)
        return json.loads(draft_path.read_text(encoding="utf-8"))

    def create_run(self, project_id: str) -> str:
        self.get_project(project_id)
        run_id = str(uuid4())
        run_directory = self._directory(project_id) / "runs" / run_id
        (run_directory / "artifacts").mkdir(parents=True)
        self._write_json(run_directory / "status.json", {"id": run_id, "status": "pending"})
        self._write_json(
            run_directory / "manifest.json",
            {
                "id": run_id,
                "definition_revisions": [],
                "dataset_versions": [],
                "parameters": {},
                "software_revision": "uncommitted",
                "environment": {"python": os.sys.version},
            },
        )
        (run_directory / "logs.txt").write_text("", encoding="utf-8")
        return run_id

    def get_watchlist(self, project_id: str) -> list[str]:
        self.get_project(project_id)
        watchlist_path = self._directory(project_id) / "watchlist.json"
        if not watchlist_path.is_file():
            return []
        data = json.loads(watchlist_path.read_text(encoding="utf-8"))
        return [str(sec_id) for sec_id in data.get("security_ids", [])]

    def add_to_watchlist(self, project_id: str, security_id: str) -> list[str]:
        from .research import validate_security_id

        valid_id = validate_security_id(security_id)
        self.get_project(project_id)
        current = self.get_watchlist(project_id)
        if valid_id not in current:
            current.append(valid_id)
            self._write_json(
                self._directory(project_id) / "watchlist.json", {"security_ids": current}
            )
        return current

    def remove_from_watchlist(self, project_id: str, security_id: str) -> list[str]:
        from .research import validate_security_id

        valid_id = validate_security_id(security_id)
        self.get_project(project_id)
        current = self.get_watchlist(project_id)
        if valid_id in current:
            current = [sid for sid in current if sid != valid_id]
            self._write_json(
                self._directory(project_id) / "watchlist.json", {"security_ids": current}
            )
        return current

    def is_watched(self, project_id: str, security_id: str) -> bool:
        from .research import validate_security_id

        valid_id = validate_security_id(security_id)
        return valid_id in self.get_watchlist(project_id)

    def get_thesis(self, project_id: str, security_id: str):
        from .research import SecurityNotWatchedError, get_thesis, validate_security_id

        valid_id = validate_security_id(security_id)
        if not self.is_watched(project_id, valid_id):
            raise SecurityNotWatchedError(
                f"Security '{valid_id}' is not in the project watchlist."
            )
        return get_thesis(self._directory(project_id), valid_id)

    def save_thesis(self, project_id: str, security_id: str, content: str):
        from .research import SecurityNotWatchedError, save_thesis, validate_security_id

        valid_id = validate_security_id(security_id)
        if not self.is_watched(project_id, valid_id):
            raise SecurityNotWatchedError(
                f"Security '{valid_id}' is not in the project watchlist."
            )
        return save_thesis(self._directory(project_id), valid_id, content)

    def list_theses(self, project_id: str):
        from .research import list_theses

        self.get_project(project_id)
        return list_theses(self._directory(project_id))

    def list_valuations_for_security(
        self, project_id: str, security_id: str
    ) -> list[dict[str, JsonValue]]:
        from .research import validate_security_id

        valid_id = validate_security_id(security_id)
        self.get_project(project_id)
        valuation_dir = self._directory(project_id) / "definitions" / "valuation"
        if not valuation_dir.is_dir():
            return []

        results: list[dict[str, JsonValue]] = []
        for model_dir in valuation_dir.iterdir():
            if not model_dir.is_dir():
                continue
            # Check revisions (v1, v2...) and draft
            for rev_dir in model_dir.iterdir():
                if not rev_dir.is_dir():
                    continue
                def_file = rev_dir / "definition.json"
                if not def_file.is_file():
                    continue
                try:
                    data = json.loads(def_file.read_text(encoding="utf-8"))
                    definition = data.get("definition", {})
                    if isinstance(definition, dict) and definition.get("security_id") == valid_id:
                        results.append(
                            {
                                "name": data.get("name", model_dir.name),
                                "revision": rev_dir.name,
                                "kind": "valuation",
                                "saved_at": data.get("saved_at", ""),
                            }
                        )
                except Exception:
                    pass
        return results

    def list_runs_for_security(
        self, project_id: str, security_id: str
    ) -> list[dict[str, JsonValue]]:
        from .research import validate_security_id

        valid_id = validate_security_id(security_id)
        self.get_project(project_id)
        runs_dir = self._directory(project_id) / "runs"
        if not runs_dir.is_dir():
            return []

        results: list[dict[str, JsonValue]] = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest_file = run_dir / "manifest.json"
            status_file = run_dir / "status.json"
            if manifest_file.is_file() and status_file.is_file():
                try:
                    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    status_data = json.loads(status_file.read_text(encoding="utf-8"))
                    params = manifest.get("parameters", {})
                    if isinstance(params, dict) and params.get("security_id") == valid_id:
                        results.append(
                            {
                                "id": run_dir.name,
                                "status": status_data.get("status", "unknown"),
                                "parameters": params,
                            }
                        )
                except Exception:
                    pass
        return results

    def _directory(self, project_id: str) -> Path:
        return self.projects_root / project_id

    @staticmethod
    def _next_revision_number(definition_root: Path) -> int:
        revisions = [
            int(entry.name[1:])
            for entry in definition_root.iterdir()
            if entry.is_dir() and re.fullmatch(r"v[1-9][0-9]*", entry.name)
        ]
        return max(revisions, default=0) + 1

    @staticmethod
    def _write_json(path: Path, contents: dict[str, JsonValue]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            json.dump(contents, temporary, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
