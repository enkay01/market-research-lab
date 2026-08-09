import json

import pytest

from market_research_lab.projects import (
    DefinitionRevisionReference,
    ProjectStore,
    RevisionNotFoundError,
)


def test_revisions_are_immutable_snapshots_and_runs_publish_artifacts_on_completion(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Quality compounders")

    store.save_draft(
        project.id,
        kind="valuation",
        name="Acme DCF",
        definition={"method": "fcff_dcf", "wacc": 0.09},
    )
    assert store.save_draft_as_revision(project.id, kind="valuation", name="Acme DCF") == "v1"
    store.save_draft(
        project.id,
        kind="valuation",
        name="Acme DCF",
        definition={"method": "fcff_dcf", "wacc": 0.1},
    )
    assert store.save_draft_as_revision(project.id, kind="valuation", name="Acme DCF") == "v2"

    revision_root = tmp_path / "projects" / project.id / "definitions" / "valuation" / "acme-dcf"
    v1 = json.loads((revision_root / "v1" / "definition.json").read_text(encoding="utf-8"))
    v2 = json.loads((revision_root / "v2" / "definition.json").read_text(encoding="utf-8"))
    assert v1["definition"] == {
        "method": "fcff_dcf",
        "wacc": 0.09,
    }
    assert v2["definition"] == {
        "method": "fcff_dcf",
        "wacc": 0.1,
    }

    run_id = store.create_run(
        project.id,
        definition_revisions=[
            DefinitionRevisionReference(kind="valuation", name="Acme DCF", revision="v2")
        ],
        dataset_versions=["prices-2026-08-09"],
        parameters={"starting_cash": 10_000},
        software_revision="abc123",
        environment={"python": "3.12"},
    )
    assert not (tmp_path / "projects" / project.id / "runs" / run_id / "artifacts").exists()

    staging = store.artifact_staging_directory(project.id, run_id)
    (staging / "summary.json").write_text('{"return": 0.12}\n', encoding="utf-8")
    store.complete_run(project.id, run_id)

    run_root = tmp_path / "projects" / project.id / "runs" / run_id
    run_status = json.loads((run_root / "status.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert run_status["status"] == "completed"
    assert manifest == {
        "id": run_id,
        "definition_revisions": [{"kind": "valuation", "name": "Acme DCF", "revision": "v2"}],
        "dataset_versions": ["prices-2026-08-09"],
        "parameters": {"starting_cash": 10_000},
        "software_revision": "abc123",
        "environment": {"python": "3.12"},
    }
    assert (run_root / "artifacts" / "summary.json").is_file()
    assert store.read_run(project.id, run_id).artifacts == ["summary.json"]


def test_failed_run_keeps_its_error_and_logs_without_publishing_partial_artifacts(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Quality compounders")
    run_id = store.create_run(project.id)

    staging = store.artifact_staging_directory(project.id, run_id)
    (staging / "partial.csv").write_text("not complete\n", encoding="utf-8")
    store.append_run_log(project.id, run_id, "Started calculation\n")
    store.fail_run(project.id, run_id, error="Insufficient eligible observations")

    run_root = tmp_path / "projects" / project.id / "runs" / run_id
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["status"] == "failed"
    assert json.loads((run_root / "status.json").read_text(encoding="utf-8"))["error"] == (
        "Insufficient eligible observations"
    )
    assert (run_root / "logs.txt").read_text(encoding="utf-8") == "Started calculation\n"
    assert not (run_root / "artifacts").exists()
    assert not staging.exists()


def test_runs_can_only_reference_existing_immutable_revisions(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("Quality compounders")

    with pytest.raises(RevisionNotFoundError):
        store.create_run(
            project.id,
            definition_revisions=[
                DefinitionRevisionReference(kind="valuation", name="Acme DCF", revision="v1")
            ],
        )
