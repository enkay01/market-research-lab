# Protect Run provenance during cleanup

## Context

Dataset Versions are shared by Projects. Completed and failed Runs store Dataset Version IDs in their manifests. Removing a Dataset Version that a Run uses would leave the Run unable to explain or reproduce its inputs.

## Decision

Allow the Analyst to delete a Dataset Version only when no Project Run references it. Delete the catalogue row and the Parquet files owned by that Dataset Version together. Delete a Run as one Project directory, including its reports, manifest, logs, and artifacts.

The interface reports the blocking Run references and asks the Analyst to delete those Runs first. Whole Project deletion remains available when the Analyst wants to remove all files owned by one Project.

## Consequences

Run provenance stays valid until the Analyst removes the Run. Unused local data can be cleaned without manual filesystem work. A Dataset Version can remain after a definition or thesis stops using it, because those files do not provide the same reproducibility guarantee as a Run manifest.
