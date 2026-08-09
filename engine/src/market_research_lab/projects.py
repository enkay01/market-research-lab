"""Durable Project files and immutable Definition Revisions."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence
from uuid import uuid4


class ProjectNotFoundError(Exception):
    """Raised when a requested Project does not exist."""


class RevisionNotFoundError(Exception):
    """Raised when a Run references a Definition Revision that does not exist."""


class RunNotFoundError(Exception):
    """Raised when a requested Run does not exist."""


class InvalidRunStateError(Exception):
    """Raised when a terminal Run operation is attempted more than once."""


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    created_at: str


@dataclass(frozen=True)
class DefinitionRevisionReference:
    kind: str
    name: str
    revision: str


@dataclass(frozen=True)
class RunRecord:
    id: str
    status: str
    error: str | None
    definition_revisions: list[DefinitionRevisionReference]
    dataset_versions: list[str]
    parameters: dict[str, object]
    software_revision: str
    environment: dict[str, str]
    logs: str
    artifacts: list[str]


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
        self, project_id: str, *, kind: str, name: str, definition: dict[str, object]
    ) -> str:
        self.save_draft(project_id, kind=kind, name=name, definition=definition)
        return self.save_draft_as_revision(project_id, kind=kind, name=name)

    def save_draft_as_revision(self, project_id: str, *, kind: str, name: str) -> str:
        draft = self.read_draft(project_id, kind=kind, name=name)
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
                "definition": draft["definition"],
            },
        )
        os.replace(temporary_directory, revision_directory)
        return revision

    def save_draft(
        self, project_id: str, *, kind: str, name: str, definition: dict[str, object]
    ) -> None:
        self.get_project(project_id)
        definition_root = self._directory(project_id) / "definitions" / kind / _slug(name)
        self._write_json(
            definition_root / "draft" / "definition.json",
            {"name": name, "definition": definition, "saved_at": _timestamp()},
        )

    def read_draft(self, project_id: str, *, kind: str, name: str) -> dict[str, object]:
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

    def create_run(
        self,
        project_id: str,
        *,
        definition_revisions: Sequence[DefinitionRevisionReference] = (),
        dataset_versions: Sequence[str] = (),
        parameters: dict[str, object] | None = None,
        software_revision: str = "uncommitted",
        environment: dict[str, str] | None = None,
    ) -> str:
        self.get_project(project_id)
        for revision_reference in definition_revisions:
            self._read_revision(project_id, revision_reference)

        run_id = str(uuid4())
        run_directory = self._directory(project_id) / "runs" / run_id
        self._artifact_staging_directory(project_id, run_id).mkdir(parents=True)
        self._write_json(run_directory / "status.json", {"id": run_id, "status": "pending"})
        self._write_json(
            run_directory / "manifest.json",
            {
                "id": run_id,
                "definition_revisions": [asdict(reference) for reference in definition_revisions],
                "dataset_versions": list(dataset_versions),
                "parameters": parameters or {},
                "software_revision": software_revision,
                "environment": environment or {"python": sys.version},
            },
        )
        (run_directory / "logs.txt").write_text("", encoding="utf-8")
        return run_id

    def artifact_staging_directory(self, project_id: str, run_id: str) -> Path:
        """Return the private directory where a Run writes artifacts before completion."""
        self._run_directory(project_id, run_id)
        return self._artifact_staging_directory(project_id, run_id)

    def read_run(self, project_id: str, run_id: str) -> RunRecord:
        run_directory = self._run_directory(project_id, run_id)
        status = json.loads((run_directory / "status.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_directory / "manifest.json").read_text(encoding="utf-8"))
        logs = (run_directory / "logs.txt").read_text(encoding="utf-8")
        artifacts_directory = run_directory / "artifacts"
        artifacts = (
            sorted(
                str(path.relative_to(artifacts_directory))
                for path in artifacts_directory.rglob("*")
                if path.is_file()
            )
            if status["status"] == "completed" and artifacts_directory.is_dir()
            else []
        )
        return RunRecord(
            id=run_id,
            status=status["status"],
            error=status.get("error"),
            definition_revisions=[
                DefinitionRevisionReference(**reference)
                for reference in manifest["definition_revisions"]
            ],
            dataset_versions=manifest["dataset_versions"],
            parameters=manifest["parameters"],
            software_revision=manifest["software_revision"],
            environment=manifest["environment"],
            logs=logs,
            artifacts=artifacts,
        )

    def append_run_log(self, project_id: str, run_id: str, message: str) -> None:
        run_directory = self._run_directory(project_id, run_id)
        with (run_directory / "logs.txt").open("a", encoding="utf-8") as log_file:
            log_file.write(message)

    def complete_run(self, project_id: str, run_id: str) -> None:
        run_directory = self._run_directory(project_id, run_id)
        self._ensure_run_is_pending(run_directory)
        staging_directory = self._artifact_staging_directory(project_id, run_id)
        os.replace(staging_directory, run_directory / "artifacts")
        self._write_json(
            run_directory / "status.json",
            {"id": run_id, "status": "completed", "completed_at": _timestamp()},
        )

    def fail_run(self, project_id: str, run_id: str, *, error: str) -> None:
        run_directory = self._run_directory(project_id, run_id)
        self._ensure_run_is_pending(run_directory)
        staging_directory = self._artifact_staging_directory(project_id, run_id)
        if staging_directory.exists():
            shutil.rmtree(staging_directory)
        self._write_json(
            run_directory / "status.json",
            {"id": run_id, "status": "failed", "failed_at": _timestamp(), "error": error},
        )

    def _directory(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def _read_revision(
        self, project_id: str, reference: DefinitionRevisionReference
    ) -> dict[str, object]:
        revision_path = (
            self._directory(project_id)
            / "definitions"
            / reference.kind
            / _slug(reference.name)
            / reference.revision
            / "definition.json"
        )
        if not revision_path.is_file():
            raise RevisionNotFoundError(
                f"{reference.kind}/{reference.name}/{reference.revision}"
            )
        return json.loads(revision_path.read_text(encoding="utf-8"))

    def _run_directory(self, project_id: str, run_id: str) -> Path:
        self.get_project(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        if not (run_directory / "status.json").is_file():
            raise RunNotFoundError(run_id)
        return run_directory

    def _artifact_staging_directory(self, project_id: str, run_id: str) -> Path:
        return self._directory(project_id) / "runs" / run_id / ".artifacts"

    @staticmethod
    def _ensure_run_is_pending(run_directory: Path) -> None:
        status = json.loads((run_directory / "status.json").read_text(encoding="utf-8"))
        if status["status"] != "pending":
            raise InvalidRunStateError(status["status"])

    @staticmethod
    def _next_revision_number(definition_root: Path) -> int:
        revisions = [
            int(entry.name[1:])
            for entry in definition_root.iterdir()
            if entry.is_dir() and re.fullmatch(r"v[1-9][0-9]*", entry.name)
        ]
        return max(revisions, default=0) + 1

    @staticmethod
    def _write_json(path: Path, contents: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as temporary:
            json.dump(contents, temporary, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
