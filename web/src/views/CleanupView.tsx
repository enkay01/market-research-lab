import { useEffect, useState } from "react";
import {
  Badge,
  Banner,
  Button,
  Card,
  EmptyState,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  Token,
  VStack,
} from "@astryxdesign/core";
import { api, type CoverageResponse, type Project, type RunSummary } from "../api/client";
import { DeleteConfirmationDialog } from "../components/DeleteConfirmationDialog";

interface CleanupViewProps {
  project?: Project;
  onProjectDeleted: (projectId: string) => void;
}

type DeletionTarget = {
  kind: "dataset" | "run" | "project";
  id: string;
  title: string;
  description: string;
  confirmationPhrase: string;
  confirmLabel: string;
};

function runStatusVariant(status: string): "success" | "error" | "warning" | "neutral" {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "pending") return "warning";
  return "neutral";
}

function datasetTypeLabel(dataset: CoverageResponse): string {
  if (dataset.is_fundamentals) return "Fundamentals";
  if (dataset.is_corporate_actions) return "Corporate actions";
  return "Daily bars";
}

export function CleanupView({ project, onProjectDeleted }: CleanupViewProps) {
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeletion, setPendingDeletion] = useState<DeletionTarget | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  async function loadWorkspace() {
    setIsLoading(true);
    setError(null);
    try {
      const [availableDatasets, projectRuns] = await Promise.all([
        api.listDatasets(),
        project ? api.listRuns(project.id) : Promise.resolve<RunSummary[]>([]),
      ]);
      setDatasets(availableDatasets);
      setRuns(projectRuns);
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Failed to load cleanup records.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkspace();
  }, [project?.id]);

  function requestDelete(target: DeletionTarget) {
    setDeleteError(null);
    setPendingDeletion(target);
  }

  async function confirmDelete() {
    if (!pendingDeletion) return;

    setIsDeleting(true);
    setDeleteError(null);
    try {
      if (pendingDeletion.kind === "dataset") {
        await api.deleteDataset(pendingDeletion.id);
        setDatasets((current) => current.filter((dataset) => dataset.id !== pendingDeletion.id));
      } else if (pendingDeletion.kind === "run" && project) {
        await api.deleteRun(project.id, pendingDeletion.id);
        setRuns((current) => current.filter((run) => run.id !== pendingDeletion.id));
      } else if (pendingDeletion.kind === "project" && project) {
        await api.deleteProject(project.id);
        onProjectDeleted(project.id);
      }
      setPendingDeletion(null);
    } catch (cause: unknown) {
      setDeleteError(cause instanceof Error ? cause.message : "The item could not be deleted.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <Layout
      height="fill"
      header={
        <LayoutHeader hasDivider padding={2}>
          <HStack justify="between" align="center" style={{ width: "100%" }}>
            <HStack align="center" gap={3}>
              <Heading level={2}>Workspace cleanup</Heading>
              <Badge label={`${datasets.length} Dataset Versions`} variant="purple" />
              {project && <Badge label={`${runs.length} Runs`} variant="purple" />}
            </HStack>
            <Button label="Refresh" variant="secondary" size="sm" onClick={() => void loadWorkspace()} />
          </HStack>
        </LayoutHeader>
      }
      content={
        <>
          <LayoutContent padding={3} isScrollable>
          <VStack gap={5}>
            {error && (
              <Banner status="error" title="Cleanup error" description={error} />
            )}

            <VStack gap={2}>
              <HStack justify="between" align="center">
                <VStack gap={0}>
                  <Heading level={3}>Shared Dataset Versions</Heading>
                  <Text type="supporting">
                    Imported and downloaded data stored in the local catalogue.
                  </Text>
                </VStack>
                <Text type="supporting">Runs protect the data they reference.</Text>
              </HStack>

              {isLoading ? (
                <Text type="supporting">Loading Dataset Versions...</Text>
              ) : datasets.length === 0 ? (
                <EmptyState
                  title="No Dataset Versions"
                  description="Imported or downloaded market data will appear here."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>Source</TableHeaderCell>
                      <TableHeaderCell>Type</TableHeaderCell>
                      <TableHeaderCell>Rows</TableHeaderCell>
                      <TableHeaderCell>Coverage</TableHeaderCell>
                      <TableHeaderCell>Retrieved</TableHeaderCell>
                      <TableHeaderCell>Version ID</TableHeaderCell>
                      <TableHeaderCell>Action</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {datasets.map((dataset) => (
                      <TableRow key={dataset.id}>
                        <TableCell><Text weight="medium">{dataset.source}</Text></TableCell>
                        <TableCell><Token label={datasetTypeLabel(dataset)} color="blue" /></TableCell>
                        <TableCell>{dataset.row_count.toLocaleString()}</TableCell>
                        <TableCell>
                          {dataset.coverage_start && dataset.coverage_end
                            ? `${dataset.coverage_start} to ${dataset.coverage_end}`
                            : "Not available"}
                        </TableCell>
                        <TableCell>
                          <Text type="supporting">
                            {new Date(dataset.retrieval_time).toLocaleString()}
                          </Text>
                        </TableCell>
                        <TableCell><Text hasTabularNumbers>{dataset.id}</Text></TableCell>
                        <TableCell>
                          <Button
                            label="Delete"
                            variant="secondary"
                            size="sm"
                            onClick={() =>
                              requestDelete({
                                kind: "dataset",
                                id: dataset.id,
                                title: "Delete Dataset Version",
                                description:
                                  "This removes the catalogue record and the Parquet file owned by this Dataset Version.",
                                confirmationPhrase: dataset.id,
                                confirmLabel: "Delete Dataset",
                              })
                            }
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </VStack>

            <VStack gap={2}>
              <HStack justify="between" align="center">
                <VStack gap={0}>
                  <Heading level={3}>Generated Runs</Heading>
                  <Text type="supporting">
                    Reports, manifests, logs, and result files owned by the selected Project.
                  </Text>
                </VStack>
                {project && <Text type="supporting">Project: {project.name}</Text>}
              </HStack>

              {!project ? (
                <EmptyState
                  title="Select a Project"
                  description="Create or select a Project to manage its generated Runs."
                />
              ) : isLoading ? (
                <Text type="supporting">Loading Runs...</Text>
              ) : runs.length === 0 ? (
                <EmptyState
                  title="No Generated Runs"
                  description="Completed and failed analysis Runs will appear here."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>Run ID</TableHeaderCell>
                      <TableHeaderCell>Kind</TableHeaderCell>
                      <TableHeaderCell>Status</TableHeaderCell>
                      <TableHeaderCell>Dataset Versions</TableHeaderCell>
                      <TableHeaderCell>Created</TableHeaderCell>
                      <TableHeaderCell>Action</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell><Text hasTabularNumbers>{run.id}</Text></TableCell>
                        <TableCell><Token label={run.kind} color="purple" /></TableCell>
                        <TableCell>
                          <StatusDot variant={runStatusVariant(run.status)} label={run.status} />
                        </TableCell>
                        <TableCell>
                          <Text type="supporting">
                            {run.dataset_version_ids.length > 0
                              ? run.dataset_version_ids.join(", ")
                              : "None recorded"}
                          </Text>
                        </TableCell>
                        <TableCell>
                          <Text type="supporting">
                            {run.created_at ? new Date(run.created_at).toLocaleString() : "Older Run"}
                          </Text>
                        </TableCell>
                        <TableCell>
                          <Button
                            label="Delete"
                            variant="secondary"
                            size="sm"
                            onClick={() =>
                              requestDelete({
                                kind: "run",
                                id: run.id,
                                title: "Delete Run",
                                description:
                                  "This removes the Run directory, including its reports, manifest, logs, and generated artifacts.",
                                confirmationPhrase: run.id,
                                confirmLabel: "Delete Run",
                              })
                            }
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </VStack>

            {project && (
              <Card padding={3}>
                <VStack gap={2}>
                  <Heading level={3}>Delete Project</Heading>
                  <Text type="supporting">
                    Delete the Project to remove its research, definitions, Runs, reports, and Alerts together.
                  </Text>
                  <HStack justify="start">
                    <Button
                      label="Delete Project and All Files"
                      variant="secondary"
                      onClick={() =>
                        requestDelete({
                          kind: "project",
                          id: project.id,
                          title: "Delete Project",
                          description:
                            "This permanently removes the Project directory and everything stored inside it.",
                          confirmationPhrase: project.name,
                          confirmLabel: "Delete Project",
                        })
                      }
                    />
                  </HStack>
                </VStack>
              </Card>
            )}
          </VStack>
          </LayoutContent>
          <DeleteConfirmationDialog
            isOpen={pendingDeletion !== null}
            title={pendingDeletion?.title ?? "Delete item"}
            description={pendingDeletion?.description ?? "This action cannot be undone."}
            confirmationPhrase={pendingDeletion?.confirmationPhrase ?? ""}
            confirmLabel={pendingDeletion?.confirmLabel ?? "Delete"}
            isDeleting={isDeleting}
            error={deleteError}
            onClose={() => {
              if (!isDeleting) {
                setPendingDeletion(null);
                setDeleteError(null);
              }
            }}
            onConfirm={() => void confirmDelete()}
          />
        </>
      }
    />
  );
}
