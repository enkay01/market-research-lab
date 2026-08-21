"""Durable Project files and immutable Definition Revisions."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .json_types import JsonValue

if TYPE_CHECKING:
    from .research import ResearchThesis


class ProjectNotFoundError(Exception):
    """Raised when a requested Project does not exist."""


class RevisionNotFoundError(Exception):
    """Raised when a requested immutable Definition Revision does not exist."""


class RevisionNotImmutableError(Exception):
    """Raised when a draft or non-vN name is treated as an immutable revision."""


_REVISION_REGEX = re.compile(r"^v[1-9][0-9]*$")


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


@dataclass(frozen=True)
class ValuationRunRecord:
    """Record describing a completed Valuation to persist as a Run artifact."""

    method_revision: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    result: dict[str, JsonValue]


@dataclass(frozen=True)
class BacktestRunRecord:
    """Record describing a completed Backtest to persist as a Run artifact."""

    strategy_revision: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    result: dict[str, JsonValue]


@dataclass(frozen=True)
class FailedBacktestRunRecord:
    """Record describing a failed Backtest to persist as a Run artifact."""

    strategy_revision: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    error_message: str


@dataclass(frozen=True)
class PredictiveModelRunRecord:
    """Record describing a completed Predictive Model Run."""

    model_revision: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    as_of: str | None
    completed_at: str
    artifact: dict[str, JsonValue]
    predictions: list[dict[str, JsonValue]]
    result: dict[str, JsonValue]
    evaluation: dict[str, JsonValue] = field(default_factory=dict)
    fold_artifacts: list[dict[str, JsonValue]] = field(default_factory=list)
    folds: list[dict[str, JsonValue]] = field(default_factory=list)


@dataclass(frozen=True)
class FailedPredictiveModelRunRecord:
    """Record describing a failed Predictive Model Run."""

    model_revision: str
    dataset_version_ids: list[str]
    parameters: dict[str, JsonValue]
    as_of: str | None
    error_message: str


@dataclass(frozen=True)
class ExportArtifact:
    """Exported file payload with content, MIME media type, and filename."""

    content: str
    media_type: str
    filename: str


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

    def read_revision(
        self, project_id: str, *, kind: str, name: str, revision: str
    ) -> dict[str, JsonValue]:
        """Read one immutable Definition Revision, rejecting drafts and unknown revisions."""
        self.get_project(project_id)
        if not _REVISION_REGEX.fullmatch(revision):
            raise RevisionNotImmutableError(
                f"'{revision}' is not an immutable revision (expected 'v1', 'v2', ...)."
            )
        revision_path = (
            self._directory(project_id)
            / "definitions"
            / kind
            / _slug(name)
            / revision
            / "definition.json"
        )
        if not revision_path.is_file():
            raise RevisionNotFoundError(
                f"Revision '{revision}' of {kind} '{name}' does not exist."
            )
        return json.loads(revision_path.read_text(encoding="utf-8"))

    def list_strategy_revisions(self, project_id: str) -> list[dict[str, JsonValue]]:
        """List saved immutable Strategy revisions available for enabling."""
        self.get_project(project_id)
        definitions_root = self._directory(project_id) / "definitions" / "strategy"
        if not definitions_root.is_dir():
            return []
        results: list[dict[str, JsonValue]] = []
        for name_directory in sorted(definitions_root.iterdir(), key=lambda path: path.name):
            if not name_directory.is_dir():
                continue
            for revision_directory in sorted(name_directory.iterdir(), key=lambda path: path.name):
                if not revision_directory.is_dir():
                    continue
                if not _REVISION_REGEX.fullmatch(revision_directory.name):
                    continue
                definition_file = revision_directory / "definition.json"
                if not definition_file.is_file():
                    continue
                with contextlib.suppress(json.JSONDecodeError, OSError):
                    data = json.loads(definition_file.read_text(encoding="utf-8"))
                    results.append(
                        {
                            "name": str(data.get("name", name_directory.name)),
                            "revision": revision_directory.name,
                            "saved_at": str(data.get("saved_at", "")),
                        }
                    )
        return results

    def enable_strategy(
        self, project_id: str, *, name: str, revision: str
    ) -> dict[str, JsonValue]:
        """Persist one validated immutable Strategy revision as enabled."""
        self.read_revision(project_id, kind="strategy", name=name, revision=revision)
        enabled = self.list_enabled_strategies(project_id)
        for item in enabled:
            if item.get("name") == name and item.get("revision") == revision:
                return item
        record: dict[str, JsonValue] = {
            "name": name,
            "revision": revision,
            "enabled_at": _timestamp(),
        }
        enabled.append(record)
        self._write_enabled_strategies(project_id, enabled)
        return record

    def disable_strategy(self, project_id: str, *, name: str, revision: str) -> None:
        """Remove one enabled Strategy revision by name and revision."""
        enabled = self.list_enabled_strategies(project_id)
        remaining = [
            item
            for item in enabled
            if not (item.get("name") == name and item.get("revision") == revision)
        ]
        self._write_enabled_strategies(project_id, remaining)

    def list_enabled_strategies(self, project_id: str) -> list[dict[str, JsonValue]]:
        """Read the Project's enabled Strategy revisions."""
        self.get_project(project_id)
        path = self._directory(project_id) / "enabled_strategies.json"
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        strategies = data.get("strategies", [])
        if not isinstance(strategies, list):
            return []
        return [item for item in strategies if isinstance(item, dict)]

    def save_signal(self, project_id: str, signal: dict[str, JsonValue]) -> str:
        """Persist one Signal as an immutable Alert artifact."""
        self.get_project(project_id)
        signal_id = str(signal.get("signal_id") or uuid4().hex)
        self._write_json(self._directory(project_id) / "alerts" / f"{signal_id}.json", signal)
        return signal_id

    def list_signals(self, project_id: str) -> list[dict[str, JsonValue]]:
        """Read persisted Signals newest-first."""
        self.get_project(project_id)
        alerts_root = self._directory(project_id) / "alerts"
        if not alerts_root.is_dir():
            return []
        signals: list[dict[str, JsonValue]] = []
        for entry in alerts_root.iterdir():
            if not entry.is_file() or entry.suffix != ".json":
                continue
            with contextlib.suppress(OSError, json.JSONDecodeError):
                loaded = json.loads(entry.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    signals.append(loaded)
        signals.sort(key=lambda item: str(item.get("decision_time", "")), reverse=True)
        return signals

    def list_signals_for_security(
        self, project_id: str, security_id: str
    ) -> list[dict[str, JsonValue]]:
        """Read persisted Signals for one Security newest-first (RES-005)."""
        return [
            signal
            for signal in self.list_signals(project_id)
            if str(signal.get("security_id", "")) == security_id
        ]

    def _write_enabled_strategies(
        self, project_id: str, strategies: list[dict[str, JsonValue]]
    ) -> None:
        self.get_project(project_id)
        self._write_json(
            self._directory(project_id) / "enabled_strategies.json",
            {"strategies": strategies},
        )

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

    def append_run_log(self, project_id: str, run_id: str, message: str) -> None:
        """Append one already-formatted diagnostic line to an existing Run log."""
        self.get_project(project_id)
        log_path = self._directory(project_id) / "runs" / run_id / "logs.txt"
        if not log_path.is_file():
            raise FileNotFoundError(f"Run {run_id} does not have a log file.")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{message}\n")

    def create_valuation_result(
        self,
        project_id: str,
        record: ValuationRunRecord,
    ) -> str:
        """Persist one completed Valuation as a reproducible Run artifact."""
        from .reporting import generate_valuation_csv, generate_valuation_html_report

        run_id = self.create_run(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        manifest = {
            "id": run_id,
            "kind": "valuation",
            "definition_revisions": [record.method_revision],
            "dataset_versions": record.dataset_version_ids,
            "parameters": record.parameters,
            "software_revision": "uncommitted",
            "environment": {"python": os.sys.version},
        }
        self._write_json(run_directory / "manifest.json", manifest)
        persisted_result = dict(record.result)
        persisted_result["method_revision"] = record.method_revision
        persisted_result["run_id"] = run_id
        self._write_json(run_directory / "artifacts" / "valuation.json", persisted_result)

        # Write self-contained HTML report and CSV summary artifacts
        html_report = generate_valuation_html_report(persisted_result, manifest)
        (run_directory / "artifacts" / "valuation_report.html").write_text(
            html_report, encoding="utf-8"
        )
        csv_data = generate_valuation_csv(persisted_result)
        (run_directory / "artifacts" / "summary.csv").write_text(csv_data, encoding="utf-8")

        self._write_json(run_directory / "status.json", {"id": run_id, "status": "completed"})
        return run_id

    def get_valuation_export(
        self, project_id: str, run_id: str, format_type: str
    ) -> ExportArtifact:
        """Return ExportArtifact for an exported Valuation run."""
        self.get_project(project_id)
        run_dir = self._directory(project_id) / "runs" / run_id
        if not run_dir.is_dir():
            raise ProjectNotFoundError(f"Run {run_id} not found in project {project_id}")

        norm_fmt = format_type.lower().strip()
        if norm_fmt in ("html", "report"):
            report_path = run_dir / "artifacts" / "valuation_report.html"
            if report_path.is_file():
                return ExportArtifact(
                    content=report_path.read_text(encoding="utf-8"),
                    media_type="text/html",
                    filename=f"valuation_{run_id}.html",
                )
            raise FileNotFoundError(f"HTML report not found for run {run_id}")
        if norm_fmt == "csv":
            csv_path = run_dir / "artifacts" / "summary.csv"
            if csv_path.is_file():
                return ExportArtifact(
                    content=csv_path.read_text(encoding="utf-8"),
                    media_type="text/csv",
                    filename=f"valuation_{run_id}.csv",
                )
            raise FileNotFoundError(f"CSV export not found for run {run_id}")
        if norm_fmt in ("json", "manifest"):
            manifest_path = run_dir / "manifest.json"
            artifact_path = run_dir / "artifacts" / "valuation.json"
            combined = {
                "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file()
                else {},
                "valuation": json.loads(artifact_path.read_text(encoding="utf-8"))
                if artifact_path.is_file()
                else {},
            }
            return ExportArtifact(
                content=json.dumps(combined, indent=2),
                media_type="application/json",
                filename=f"valuation_manifest_{run_id}.json",
            )

        raise ValueError(f"Unsupported export format: {format_type}. Supported: json, csv, html")

    def list_valuation_results(self, project_id: str) -> list[dict[str, JsonValue]]:
        """Read completed Valuation Run artifacts for Project reloads."""
        self.get_project(project_id)
        runs_dir = self._directory(project_id) / "runs"
        if not runs_dir.is_dir():
            return []
        results: list[dict[str, JsonValue]] = []
        for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name):
            manifest_path = run_dir / "manifest.json"
            status_path = run_dir / "status.json"
            artifact_path = run_dir / "artifacts" / "valuation.json"
            if not (manifest_path.is_file() and status_path.is_file() and artifact_path.is_file()):
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                status_data = json.loads(status_path.read_text(encoding="utf-8"))
                result = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if manifest.get("kind") != "valuation" or status_data.get("status") != "completed":
                continue
            revisions = manifest.get("definition_revisions", [])
            method_revision = str(revisions[0]) if revisions else ""
            results.append(
                {
                    "run_id": run_dir.name,
                    "method_revision": method_revision,
                    "calculated_at": result.get("calculated_at", ""),
                    "result": result,
                }
            )
        return results

    def create_backtest_result(
        self,
        project_id: str,
        record: BacktestRunRecord,
    ) -> str:
        """Persist one completed Backtest as a reproducible Run artifact."""
        from .reporting import generate_backtest_csv, generate_backtest_html_report

        run_id = self.create_run(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        manifest = {
            "id": run_id,
            "kind": "backtest",
            "definition_revisions": [record.strategy_revision],
            "dataset_versions": record.dataset_version_ids,
            "parameters": record.parameters,
            "software_revision": "uncommitted",
            "environment": {"python": os.sys.version},
        }
        self._write_json(run_directory / "manifest.json", manifest)
        persisted_result = dict(record.result)
        persisted_result["strategy_revision"] = record.strategy_revision
        persisted_result["run_id"] = run_id
        self._write_json(run_directory / "artifacts" / "backtest.json", persisted_result)

        # Write self-contained HTML report and CSV summary artifacts
        html_report = generate_backtest_html_report(persisted_result, manifest)
        (run_directory / "artifacts" / "backtest_report.html").write_text(
            html_report, encoding="utf-8"
        )
        csv_data = generate_backtest_csv(persisted_result)
        (run_directory / "artifacts" / "summary.csv").write_text(csv_data, encoding="utf-8")

        self._write_json(run_directory / "status.json", {"id": run_id, "status": "completed"})
        return run_id

    def create_failed_backtest_run(
        self,
        project_id: str,
        record: FailedBacktestRunRecord,
    ) -> str:
        """Persist a failed Backtest run recording its error and logs without partial artifacts (CORE-008)."""
        run_id = self.create_run(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        manifest = {
            "id": run_id,
            "kind": "backtest",
            "definition_revisions": [record.strategy_revision],
            "dataset_versions": record.dataset_version_ids,
            "parameters": record.parameters,
            "software_revision": "uncommitted",
            "environment": {"python": os.sys.version},
            "error": record.error_message,
        }
        self._write_json(run_directory / "manifest.json", manifest)
        self._write_json(
            run_directory / "artifacts" / "error.json",
            {"run_id": run_id, "error": record.error_message, "failed_at": _timestamp()},
        )
        self._write_json(
            run_directory / "status.json",
            {"id": run_id, "status": "failed", "error": record.error_message},
        )
        return run_id

    def create_predictive_model_result(
        self,
        project_id: str,
        record: PredictiveModelRunRecord,
    ) -> str:
        """Persist a completed Predictive Model Run and its reproducibility artifacts."""
        from .reporting import generate_predictive_model_csv, generate_predictive_model_html_report

        run_id = self.create_run(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        evaluation_summary = dict(record.evaluation)
        evaluation_summary.pop("folds", None)
        manifest = {
            "id": run_id,
            "kind": "predictive_model",
            "definition_revisions": [record.model_revision],
            "dataset_versions": record.dataset_version_ids,
            "parameters": record.parameters,
            "as_of": record.as_of,
            "completed_at": record.completed_at,
            "evaluation": evaluation_summary,
            "software_revision": "uncommitted",
            "environment": {"python": os.sys.version},
        }
        temporary_artifacts = run_directory / f".artifacts-{uuid4().hex}.tmp"
        try:
            temporary_artifacts.mkdir()
            self._write_json(run_directory / "manifest.json", manifest)

            persisted_result = dict(record.result)
            persisted_result.update(
                {
                    "run_id": run_id,
                    "model_revision": record.model_revision,
                    "artifact": record.artifact,
                    "predictions": record.predictions,
                    "evaluation": evaluation_summary,
                    "fold_artifacts": record.fold_artifacts,
                }
            )
            persisted_result.pop("folds", None)
            report_result = dict(persisted_result)
            report_result["evaluation"] = record.evaluation
            report_result["folds"] = record.folds
            self._write_json(
                temporary_artifacts / "predictive_model.json", persisted_result
            )
            self._write_json(temporary_artifacts / "fitted_model.json", record.artifact)
            self._write_json(
                temporary_artifacts / "predictions.json",
                {"predictions": record.predictions},
            )
            self._write_json(
                temporary_artifacts / "fold_artifacts.json",
                {"artifacts": record.fold_artifacts},
            )
            self._write_json(
                temporary_artifacts / "folds.json",
                {"folds": record.folds},
            )
            (temporary_artifacts / "predictive_model_report.html").write_text(
                generate_predictive_model_html_report(report_result, manifest),
                encoding="utf-8",
            )
            (temporary_artifacts / "summary.csv").write_text(
                generate_predictive_model_csv(report_result),
                encoding="utf-8",
            )
            shutil.rmtree(run_directory / "artifacts")
            os.replace(temporary_artifacts, run_directory / "artifacts")
            self._write_json(
                run_directory / "status.json", {"id": run_id, "status": "completed"}
            )
        except Exception as error:
            try:
                self._mark_predictive_model_run_failed(run_directory, manifest, str(error))
            except Exception as mark_error:
                error.add_note(f"Failed to persist the Predictive Model failure: {mark_error}")
            raise
        return run_id

    def create_failed_predictive_model_run(
        self,
        project_id: str,
        record: FailedPredictiveModelRunRecord,
    ) -> str:
        """Persist a failed Predictive Model Run with its error and provenance."""
        run_id = self.create_run(project_id)
        run_directory = self._directory(project_id) / "runs" / run_id
        manifest = {
            "id": run_id,
            "kind": "predictive_model",
            "definition_revisions": [record.model_revision],
            "dataset_versions": record.dataset_version_ids,
            "parameters": record.parameters,
            "as_of": record.as_of,
            "software_revision": "uncommitted",
            "environment": {"python": os.sys.version},
            "error": record.error_message,
        }
        self._mark_predictive_model_run_failed(
            run_directory,
            manifest,
            record.error_message,
        )
        return run_id

    def _mark_predictive_model_run_failed(
        self,
        run_directory: Path,
        manifest: dict[str, JsonValue],
        error_message: str,
    ) -> None:
        """Replace pending Predictive Model state with a durable failure record."""
        run_id = str(manifest.get("id", run_directory.name))
        failed_manifest = dict(manifest)
        failed_manifest["error"] = error_message
        artifacts_directory = run_directory / "artifacts"
        artifacts_directory.mkdir(parents=True, exist_ok=True)
        self._write_json(run_directory / "manifest.json", failed_manifest)
        self._write_json(
            artifacts_directory / "error.json",
            {"run_id": run_id, "error": error_message, "failed_at": _timestamp()},
        )
        self._write_json(
            run_directory / "status.json",
            {"id": run_id, "status": "failed", "error": error_message},
        )

    def list_predictive_model_results(self, project_id: str) -> list[dict[str, JsonValue]]:
        """Read completed Predictive Model Runs for Project reloads."""
        self.get_project(project_id)
        runs_dir = self._directory(project_id) / "runs"
        if not runs_dir.is_dir():
            return []
        results: list[dict[str, JsonValue]] = []
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            result = self._read_predictive_model_result(run_dir)
            if result is not None:
                results.append(result)
        return sorted(
            results,
            key=lambda item: str(item.get("completed_at", "")),
            reverse=True,
        )

    def get_predictive_model_result(
        self, project_id: str, run_id: str
    ) -> dict[str, JsonValue] | None:
        """Read one completed Predictive Model Run, or None when it is unavailable."""
        self.get_project(project_id)
        return self._read_predictive_model_result(self._directory(project_id) / "runs" / run_id)

    def get_predictive_model_export(
        self, project_id: str, run_id: str, format_type: str
    ) -> ExportArtifact:
        """Return an HTML, CSV, or manifest export for a Predictive Model Run."""
        self.get_project(project_id)
        run_dir = self._directory(project_id) / "runs" / run_id
        if not run_dir.is_dir():
            raise ProjectNotFoundError(f"Run {run_id} not found in project {project_id}")

        norm_fmt = format_type.lower().strip()
        if norm_fmt in ("html", "report"):
            report_path = run_dir / "artifacts" / "predictive_model_report.html"
            if report_path.is_file():
                return ExportArtifact(
                    content=report_path.read_text(encoding="utf-8"),
                    media_type="text/html",
                    filename=f"predictive_model_{run_id}.html",
                )
            raise FileNotFoundError(f"HTML report not found for run {run_id}")
        if norm_fmt == "csv":
            csv_path = run_dir / "artifacts" / "summary.csv"
            if csv_path.is_file():
                return ExportArtifact(
                    content=csv_path.read_text(encoding="utf-8"),
                    media_type="text/csv",
                    filename=f"predictive_model_{run_id}.csv",
                )
            raise FileNotFoundError(f"CSV export not found for run {run_id}")
        if norm_fmt in ("json", "manifest"):
            manifest_path = run_dir / "manifest.json"
            artifact_path = run_dir / "artifacts" / "predictive_model.json"
            folds_path = run_dir / "artifacts" / "folds.json"
            predictive_model = (
                json.loads(artifact_path.read_text(encoding="utf-8"))
                if artifact_path.is_file()
                else {}
            )
            if folds_path.is_file() and isinstance(predictive_model, dict):
                folds_document = json.loads(folds_path.read_text(encoding="utf-8"))
                if isinstance(folds_document, dict):
                    predictive_model["folds"] = folds_document.get("folds", [])
            combined = {
                "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file()
                else {},
                "predictive_model": predictive_model,
            }
            return ExportArtifact(
                content=json.dumps(combined, indent=2),
                media_type="application/json",
                filename=f"predictive_model_manifest_{run_id}.json",
            )

        raise ValueError(f"Unsupported export format: {format_type}. Supported: json, csv, html")

    @staticmethod
    def _read_predictive_model_result(run_dir: Path) -> dict[str, JsonValue] | None:
        manifest_path = run_dir / "manifest.json"
        status_path = run_dir / "status.json"
        artifact_path = run_dir / "artifacts" / "predictive_model.json"
        folds_path = run_dir / "artifacts" / "folds.json"
        if not (manifest_path.is_file() and status_path.is_file() and artifact_path.is_file()):
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            status_data = json.loads(status_path.read_text(encoding="utf-8"))
            result = json.loads(artifact_path.read_text(encoding="utf-8"))
            folds_document = (
                json.loads(folds_path.read_text(encoding="utf-8"))
                if folds_path.is_file()
                else {}
            )
        except (OSError, json.JSONDecodeError):
            return None
        if manifest.get("kind") != "predictive_model" or status_data.get("status") != "completed":
            return None
        if (
            isinstance(result, dict)
            and "folds" not in result
            and isinstance(folds_document, dict)
        ):
            result["folds"] = folds_document.get("folds", [])
        revisions = manifest.get("definition_revisions", [])
        model_revision = str(revisions[0]) if revisions else ""
        return {
            "run_id": run_dir.name,
            "model_revision": model_revision,
            "completed_at": result.get("completed_at", ""),
            "result": result,
        }

    def get_backtest_export(
        self, project_id: str, run_id: str, format_type: str
    ) -> ExportArtifact:
        """Return ExportArtifact for an exported Backtest run."""
        self.get_project(project_id)
        run_dir = self._directory(project_id) / "runs" / run_id
        if not run_dir.is_dir():
            raise ProjectNotFoundError(f"Run {run_id} not found in project {project_id}")

        norm_fmt = format_type.lower().strip()
        if norm_fmt in ("html", "report"):
            report_path = run_dir / "artifacts" / "backtest_report.html"
            if report_path.is_file():
                return ExportArtifact(
                    content=report_path.read_text(encoding="utf-8"),
                    media_type="text/html",
                    filename=f"backtest_{run_id}.html",
                )
            raise FileNotFoundError(f"HTML report not found for run {run_id}")
        if norm_fmt == "csv":
            csv_path = run_dir / "artifacts" / "summary.csv"
            if csv_path.is_file():
                return ExportArtifact(
                    content=csv_path.read_text(encoding="utf-8"),
                    media_type="text/csv",
                    filename=f"backtest_{run_id}.csv",
                )
            raise FileNotFoundError(f"CSV export not found for run {run_id}")
        if norm_fmt in ("json", "manifest"):
            manifest_path = run_dir / "manifest.json"
            artifact_path = run_dir / "artifacts" / "backtest.json"
            combined = {
                "manifest": json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file()
                else {},
                "backtest": json.loads(artifact_path.read_text(encoding="utf-8"))
                if artifact_path.is_file()
                else {},
            }
            return ExportArtifact(
                content=json.dumps(combined, indent=2),
                media_type="application/json",
                filename=f"backtest_manifest_{run_id}.json",
            )

        raise ValueError(f"Unsupported export format: {format_type}. Supported: json, csv, html")

    def list_backtest_results(self, project_id: str) -> list[dict[str, JsonValue]]:
        """Read completed Backtest Run artifacts for Project reloads."""
        self.get_project(project_id)
        runs_dir = self._directory(project_id) / "runs"
        if not runs_dir.is_dir():
            return []
        results: list[dict[str, JsonValue]] = []
        for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name):
            if not run_dir.is_dir():
                continue
            item = self._read_backtest_result(run_dir)
            if item is not None:
                results.append(item)
        return results

    def get_backtest_result(
        self, project_id: str, run_id: str
    ) -> dict[str, JsonValue] | None:
        """Read one completed Backtest Run artifact, or None when not completed."""
        self.get_project(project_id)
        return self._read_backtest_result(self._directory(project_id) / "runs" / run_id)

    @staticmethod
    def _read_backtest_result(run_dir: Path) -> dict[str, JsonValue] | None:
        """Parse one completed Backtest Run directory into a result record."""
        manifest_path = run_dir / "manifest.json"
        status_path = run_dir / "status.json"
        artifact_path = run_dir / "artifacts" / "backtest.json"
        if not (manifest_path.is_file() and status_path.is_file() and artifact_path.is_file()):
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            status_data = json.loads(status_path.read_text(encoding="utf-8"))
            result = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if manifest.get("kind") != "backtest" or status_data.get("status") != "completed":
            return None
        revisions = manifest.get("definition_revisions", [])
        strategy_revision = str(revisions[0]) if revisions else ""
        return {
            "run_id": run_dir.name,
            "strategy_revision": strategy_revision,
            "result": result,
        }

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

    def get_thesis(self, project_id: str, security_id: str) -> ResearchThesis | None:
        from .research import SecurityNotWatchedError, get_thesis, validate_security_id

        valid_id = validate_security_id(security_id)
        if not self.is_watched(project_id, valid_id):
            raise SecurityNotWatchedError(
                f"Security '{valid_id}' is not in the project watchlist."
            )
        return get_thesis(self._directory(project_id), valid_id)

    def save_thesis(self, project_id: str, security_id: str, content: str) -> ResearchThesis:
        from .research import SecurityNotWatchedError, save_thesis, validate_security_id

        valid_id = validate_security_id(security_id)
        if not self.is_watched(project_id, valid_id):
            raise SecurityNotWatchedError(
                f"Security '{valid_id}' is not in the project watchlist."
            )
        return save_thesis(self._directory(project_id), valid_id, content)

    def list_theses(self, project_id: str) -> dict[str, ResearchThesis]:
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
                with contextlib.suppress(json.JSONDecodeError, OSError, KeyError, AttributeError):
                    data = json.loads(def_file.read_text(encoding="utf-8"))
                    raw_def = data.get("definition")
                    def_sec_id = (
                        (raw_def.get("security_id") or raw_def.get("target_security_id"))
                        if isinstance(raw_def, dict)
                        else None
                    )
                    if def_sec_id == valid_id:
                        results.append(
                            {
                                "name": data.get("name", model_dir.name),
                                "revision": rev_dir.name,
                                "kind": "valuation",
                                "saved_at": data.get("saved_at", ""),
                            }
                        )
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
                with contextlib.suppress(json.JSONDecodeError, OSError, KeyError, AttributeError):
                    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                    status_data = json.loads(status_file.read_text(encoding="utf-8"))
                    raw_params = manifest.get("parameters")
                    params_sec_id = (
                        (raw_params.get("security_id") or raw_params.get("target_security_id"))
                        if isinstance(raw_params, dict)
                        else None
                    )
                    if params_sec_id == valid_id:
                        results.append(
                            {
                                "id": run_dir.name,
                                "status": status_data.get("status", "unknown"),
                                "parameters": raw_params or {},
                            }
                        )
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
