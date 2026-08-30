import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Banner,
  Button,
  Card,
  CheckboxInput,
  EmptyState,
  Heading,
  HStack,
  Layout,
  LayoutContent,
  LayoutHeader,
  SegmentedControl,
  SegmentedControlItem,
  StatusDot,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  TextInput,
  Token,
  VStack,
} from "@astryxdesign/core";
import { api, type CoverageResponse, type Project, type RunSummary } from "../api/client";
import { DeleteConfirmationDialog } from "../components/DeleteConfirmationDialog";

interface DatasetManagementViewProps {
  project?: Project;
  onProjectDeleted: (projectId: string) => void;
}

type DeletionTarget =
  | {
      kind: "dataset";
      id: string;
      title: string;
      description: string;
    }
  | {
      kind: "bulk_datasets";
      ids: string[];
      title: string;
      description: string;
    }
  | {
      kind: "run";
      id: string;
      title: string;
      description: string;
    }
  | {
      kind: "bulk_runs";
      ids: string[];
      title: string;
      description: string;
    }
  | {
      kind: "project";
      id: string;
      title: string;
      description: string;
    };

function runStatusVariant(status: string): "success" | "error" | "warning" | "neutral" {
  if (status === "completed") return "success";
  if (status === "failed") return "error";
  if (status === "pending") return "warning";
  return "neutral";
}

export function DatasetManagementView({ project, onProjectDeleted }: DatasetManagementViewProps) {
  const [datasets, setDatasets] = useState<CoverageResponse[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selection states
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<Set<string>>(new Set());
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());

  // Search & Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<"all" | "bars" | "fundamentals" | "corporate">("all");

  // Deletion modal state
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
      // Clean selections for items that no longer exist
      const validDatasetIds = new Set(availableDatasets.map((d) => d.id));
      setSelectedDatasetIds((prev) => new Set([...prev].filter((id) => validDatasetIds.has(id))));
      const validRunIds = new Set(projectRuns.map((r) => r.id));
      setSelectedRunIds((prev) => new Set([...prev].filter((id) => validRunIds.has(id))));
    } catch (cause: unknown) {
      setError(cause instanceof Error ? cause.message : "Failed to load datasets.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkspace();
  }, [project?.id]);

  const filteredDatasets = useMemo(() => {
    return datasets.filter((dataset) => {
      if (typeFilter === "bars" && (dataset.is_fundamentals || dataset.is_corporate_actions)) {
        return false;
      }
      if (typeFilter === "fundamentals" && !dataset.is_fundamentals) {
        return false;
      }
      if (typeFilter === "corporate" && !dataset.is_corporate_actions) {
        return false;
      }
      if (!searchQuery.trim()) return true;
      const q = searchQuery.toLowerCase().trim();
      return (
        dataset.id.toLowerCase().includes(q) ||
        dataset.source.toLowerCase().includes(q) ||
        (dataset.coverage_start && dataset.coverage_start.toLowerCase().includes(q)) ||
        (dataset.coverage_end && dataset.coverage_end.toLowerCase().includes(q))
      );
    });
  }, [datasets, typeFilter, searchQuery]);

  const totalRows = useMemo(() => {
    return datasets.reduce((sum, d) => sum + (d.row_count || 0), 0);
  }, [datasets]);

  // Dataset Selection Handlers
  const allFilteredSelected =
    filteredDatasets.length > 0 &&
    filteredDatasets.every((d) => selectedDatasetIds.has(d.id));
  const someFilteredSelected =
    filteredDatasets.some((d) => selectedDatasetIds.has(d.id)) && !allFilteredSelected;

  function toggleSelectAllDatasets() {
    if (allFilteredSelected) {
      const filteredSet = new Set(filteredDatasets.map((d) => d.id));
      setSelectedDatasetIds((prev) => new Set([...prev].filter((id) => !filteredSet.has(id))));
    } else {
      setSelectedDatasetIds((prev) => {
        const next = new Set(prev);
        filteredDatasets.forEach((d) => next.add(d.id));
        return next;
      });
    }
  }

  function toggleSelectDataset(id: string) {
    setSelectedDatasetIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // Run Selection Handlers
  const allRunsSelected = runs.length > 0 && runs.every((r) => selectedRunIds.has(r.id));
  const someRunsSelected = runs.some((r) => selectedRunIds.has(r.id)) && !allRunsSelected;

  function toggleSelectAllRuns() {
    if (allRunsSelected) {
      setSelectedRunIds(new Set());
    } else {
      setSelectedRunIds(new Set(runs.map((r) => r.id)));
    }
  }

  function toggleSelectRun(id: string) {
    setSelectedRunIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // Execution of Deletions
  async function confirmDelete() {
    if (!pendingDeletion) return;

    setIsDeleting(true);
    setDeleteError(null);
    try {
      if (pendingDeletion.kind === "dataset") {
        await api.deleteDataset(pendingDeletion.id, true);
        setDatasets((current) => current.filter((dataset) => dataset.id !== pendingDeletion.id));
        setSelectedDatasetIds((prev) => {
          const next = new Set(prev);
          next.delete(pendingDeletion.id);
          return next;
        });
      } else if (pendingDeletion.kind === "bulk_datasets") {
        const result = await api.bulkDeleteDatasets(pendingDeletion.ids, true);
        const deletedSet = new Set(result.deleted_ids);
        setDatasets((current) => current.filter((d) => !deletedSet.has(d.id)));
        setSelectedDatasetIds((prev) => new Set([...prev].filter((id) => !deletedSet.has(id))));
      } else if (pendingDeletion.kind === "run" && project) {
        await api.deleteRun(project.id, pendingDeletion.id);
        setRuns((current) => current.filter((run) => run.id !== pendingDeletion.id));
        setSelectedRunIds((prev) => {
          const next = new Set(prev);
          next.delete(pendingDeletion.id);
          return next;
        });
      } else if (pendingDeletion.kind === "bulk_runs" && project) {
        const result = await api.bulkDeleteRuns(project.id, pendingDeletion.ids);
        const deletedSet = new Set(result.deleted_ids);
        setRuns((current) => current.filter((r) => !deletedSet.has(r.id)));
        setSelectedRunIds((prev) => new Set([...prev].filter((id) => !deletedSet.has(id))));
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
              <Heading level={2}>Dataset management</Heading>
              <Badge label={`${datasets.length} Datasets`} variant="purple" />
              <Badge label={`${totalRows.toLocaleString()} Rows`} variant="neutral" />
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
                <Banner status="error" title="Dataset error">
                  {error}
                </Banner>
              )}

              {/* Shared Datasets Section */}
              <VStack gap={3}>
                <HStack justify="between" align="center">
                  <VStack gap={0}>
                    <Heading level={3}>Shared Market Datasets</Heading>
                    <Text type="supporting">
                      DuckDB catalogue records and owned Parquet files.
                    </Text>
                  </VStack>

                  <HStack align="center" gap={2}>
                    <SegmentedControl
                      label="Dataset type filter"
                      isLabelHidden
                      size="sm"
                      value={typeFilter}
                      onChange={(val) => {
                        // SAFETY: Value is constrained by SegmentedControlItem options
                        setTypeFilter(val as typeof typeFilter);
                      }}
                    >
                      <SegmentedControlItem value="all" label="All types" />
                      <SegmentedControlItem value="bars" label="Daily bars" />
                      <SegmentedControlItem value="fundamentals" label="Fundamentals" />
                      <SegmentedControlItem value="corporate" label="Corporate actions" />
                    </SegmentedControl>
                    <TextInput
                      label="Search datasets"
                      isLabelHidden
                      size="sm"
                      placeholder="Search source, date, ID..."
                      value={searchQuery}
                      onChange={(val) => setSearchQuery(String(val ?? ""))}
                      width={220}
                    />
                  </HStack>
                </HStack>

                {/* Bulk Actions Bar for Datasets */}
                {selectedDatasetIds.size > 0 && (
                  <Card padding={2}>
                    <HStack justify="between" align="center">
                      <HStack align="center" gap={2}>
                        <Badge
                          label={`${selectedDatasetIds.size} Selected`}
                          variant="purple"
                        />
                        <Text type="supporting">
                          Ready to delete selected datasets and remove their Parquet files.
                        </Text>
                      </HStack>
                      <HStack align="center" gap={2}>
                        <Button
                          label="Deselect All"
                          variant="secondary"
                          size="sm"
                          onClick={() => setSelectedDatasetIds(new Set())}
                        />
                        <Button
                          label={`Delete Selected (${selectedDatasetIds.size})`}
                          variant="primary"
                          size="sm"
                          onClick={() =>
                            setPendingDeletion({
                              kind: "bulk_datasets",
                              ids: Array.from(selectedDatasetIds),
                              title: `Delete ${selectedDatasetIds.size} Datasets`,
                              description: `This permanently unlinks all Parquet files and deletes catalogue rows for ${selectedDatasetIds.size} dataset versions.`,
                            })
                          }
                        />
                      </HStack>
                    </HStack>
                  </Card>
                )}

                {isLoading ? (
                  <Text type="supporting">Loading datasets...</Text>
                ) : filteredDatasets.length === 0 ? (
                  <EmptyState
                    title="No Datasets Found"
                    description={
                      searchQuery || typeFilter !== "all"
                        ? "No datasets match the current filter criteria."
                        : "Import or download market data to view and manage datasets here."
                    }
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell style={{ width: "40px", minWidth: "40px" }}>
                          <CheckboxInput
                            label="Select all datasets"
                            isLabelHidden
                            size="sm"
                            value={allFilteredSelected ? true : someFilteredSelected ? "indeterminate" : false}
                            onChange={() => toggleSelectAllDatasets()}
                          />
                        </TableHeaderCell>
                        <TableHeaderCell>Source</TableHeaderCell>
                        <TableHeaderCell>Version ID</TableHeaderCell>
                        <TableHeaderCell>Dataset Type</TableHeaderCell>
                        <TableHeaderCell>Valid Rows</TableHeaderCell>
                        <TableHeaderCell>Date Coverage</TableHeaderCell>
                        <TableHeaderCell>Files</TableHeaderCell>
                        <TableHeaderCell>Retrieved At</TableHeaderCell>
                        <TableHeaderCell style={{ textAlign: "end" }}>Action</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredDatasets.map((v) => {
                        const isSelected = selectedDatasetIds.has(v.id);
                        return (
                          <TableRow key={v.id}>
                            <TableCell>
                              <CheckboxInput
                                label={`Select ${v.id}`}
                                isLabelHidden
                                size="sm"
                                value={isSelected}
                                onChange={() => toggleSelectDataset(v.id)}
                              />
                            </TableCell>
                            <TableCell>
                              <Text weight="medium">{v.source}</Text>
                            </TableCell>
                            <TableCell>
                              <Text hasTabularNumbers>{v.id.slice(0, 8)}</Text>
                            </TableCell>
                            <TableCell>
                              <HStack gap={1}>
                                {v.is_corporate_actions ? (
                                  <Token label="Corporate Actions" color="purple" />
                                ) : v.is_fundamentals ? (
                                  <Token label="Fundamentals" color="blue" />
                                ) : (
                                  <Token label="Daily Bars" color="green" />
                                )}
                              </HStack>
                            </TableCell>
                            <TableCell>{v.row_count.toLocaleString()}</TableCell>
                            <TableCell>
                              {v.coverage_start && v.coverage_end
                                ? `${v.coverage_start} → ${v.coverage_end}`
                                : "—"}
                            </TableCell>
                            <TableCell>
                              <Text type="supporting">
                                {v.files?.length ?? 1} Parquet
                              </Text>
                            </TableCell>
                            <TableCell>
                              <Text type="supporting">
                                {new Date(v.retrieval_time).toLocaleString()}
                              </Text>
                            </TableCell>
                            <TableCell style={{ textAlign: "end" }}>
                              <Button
                                label="Delete"
                                variant="secondary"
                                size="sm"
                                onClick={() =>
                                  setPendingDeletion({
                                    kind: "dataset",
                                    id: v.id,
                                    title: "Delete Dataset Version",
                                    description: `Delete dataset ${v.id} and unlink its Parquet files from disk.`,
                                  })
                                }
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </VStack>

              {/* Generated Runs Section */}
              <VStack gap={3}>
                <HStack justify="between" align="center">
                  <VStack gap={0}>
                    <Heading level={3}>Generated Runs</Heading>
                    <Text type="supporting">
                      Reports, manifests, logs, and artifacts owned by the active project.
                    </Text>
                  </VStack>
                  {project && (
                    <Text type="supporting">Project: {project.name}</Text>
                  )}
                </HStack>

                {/* Bulk Actions Bar for Runs */}
                {selectedRunIds.size > 0 && project && (
                  <Card padding={2}>
                    <HStack justify="between" align="center">
                      <HStack align="center" gap={2}>
                        <Badge
                          label={`${selectedRunIds.size} Selected`}
                          variant="purple"
                        />
                        <Text type="supporting">
                          Ready to delete selected runs and remove their artifacts.
                        </Text>
                      </HStack>
                      <HStack align="center" gap={2}>
                        <Button
                          label="Deselect All"
                          variant="secondary"
                          size="sm"
                          onClick={() => setSelectedRunIds(new Set())}
                        />
                        <Button
                          label={`Delete Selected (${selectedRunIds.size})`}
                          variant="primary"
                          size="sm"
                          onClick={() =>
                            setPendingDeletion({
                              kind: "bulk_runs",
                              ids: Array.from(selectedRunIds),
                              title: `Delete ${selectedRunIds.size} Runs`,
                              description: `This permanently deletes all reports, manifests, and artifact files for ${selectedRunIds.size} runs.`,
                            })
                          }
                        />
                      </HStack>
                    </HStack>
                  </Card>
                )}

                {!project ? (
                  <EmptyState
                    title="Select a Project"
                    description="Create or select a Project to view and manage its generated Runs."
                  />
                ) : isLoading ? (
                  <Text type="supporting">Loading runs...</Text>
                ) : runs.length === 0 ? (
                  <EmptyState
                    title="No Generated Runs"
                    description="Completed and failed analysis runs will appear here."
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHeaderCell style={{ width: "40px", minWidth: "40px" }}>
                          <CheckboxInput
                            label="Select all runs"
                            isLabelHidden
                            size="sm"
                            value={allRunsSelected ? true : someRunsSelected ? "indeterminate" : false}
                            onChange={() => toggleSelectAllRuns()}
                          />
                        </TableHeaderCell>
                        <TableHeaderCell>Run ID</TableHeaderCell>
                        <TableHeaderCell>Kind</TableHeaderCell>
                        <TableHeaderCell>Status</TableHeaderCell>
                        <TableHeaderCell>Datasets Used</TableHeaderCell>
                        <TableHeaderCell>Created At</TableHeaderCell>
                        <TableHeaderCell style={{ textAlign: "end" }}>Action</TableHeaderCell>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.map((r) => {
                        const isSelected = selectedRunIds.has(r.id);
                        return (
                          <TableRow key={r.id}>
                            <TableCell>
                              <CheckboxInput
                                label={`Select ${r.id}`}
                                isLabelHidden
                                size="sm"
                                value={isSelected}
                                onChange={() => toggleSelectRun(r.id)}
                              />
                            </TableCell>
                            <TableCell>
                              <Text hasTabularNumbers>{r.id.slice(0, 8)}</Text>
                            </TableCell>
                            <TableCell>
                              <Token label={r.kind} color="purple" />
                            </TableCell>
                            <TableCell>
                              <StatusDot
                                variant={runStatusVariant(r.status)}
                                label={r.status}
                              />
                            </TableCell>
                            <TableCell>
                              <Text type="supporting">
                                {r.dataset_version_ids.length > 0
                                  ? r.dataset_version_ids.map((id) => id.slice(0, 8)).join(", ")
                                  : "None"}
                              </Text>
                            </TableCell>
                            <TableCell>
                              <Text type="supporting">
                                {r.created_at
                                  ? new Date(r.created_at).toLocaleString()
                                  : "Legacy Run"}
                              </Text>
                            </TableCell>
                            <TableCell style={{ textAlign: "end" }}>
                              <Button
                                label="Delete"
                                variant="secondary"
                                size="sm"
                                onClick={() =>
                                  setPendingDeletion({
                                    kind: "run",
                                    id: r.id,
                                    title: "Delete Run",
                                    description: `Delete run ${r.id} and remove its reports, logs, and artifacts.`,
                                  })
                                }
                              />
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </VStack>

              {/* Project Deletion Section */}
              {project && (
                <Card padding={3}>
                  <VStack gap={2}>
                    <Heading level={3}>Delete Project</Heading>
                    <Text type="supporting">
                      Remove the project directory and all contained research theses, definitions, runs, and alerts.
                    </Text>
                    <HStack justify="start">
                      <Button
                        label="Delete Project"
                        variant="secondary"
                        onClick={() =>
                          setPendingDeletion({
                            kind: "project",
                            id: project.id,
                            title: `Delete Project "${project.name}"`,
                            description:
                              "This removes the project directory and all contained files.",
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
            description={pendingDeletion?.description ?? "This action removes the files immediately."}
            confirmLabel="Delete"
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
