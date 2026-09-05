import { useEffect, useState } from "react";
import {
  Layout,
  LayoutHeader,
  LayoutContent,
  LayoutPanel,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  VStack,
  HStack,
  Button,
  Heading,
  Text,
  Badge,
  Token,
  Banner,
  EmptyState,
  Spinner,
} from "@astryxdesign/core";
import {
  api,
  type CompositeDownloadRequest,
  type CoverageResponse,
  type DownloadSnapshotResponse,
} from "../api/client";
import { ImportDataDialog } from "../components/ImportDataDialog";
import { DownloadProviderDialog } from "../components/DownloadProviderDialog";
import { PitQueryDialog } from "../components/PitQueryDialog";

const ACTIVE_DOWNLOAD_STORAGE_KEY = "active_download_id";

export function DataView() {
  const [datasetVersions, setDatasetVersions] = useState<CoverageResponse[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedCoverage, setSelectedCoverage] = useState<CoverageResponse | null>(null);
  const [previewRows, setPreviewRows] = useState<Record<string, string | number | boolean | null>[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isInspectorLoading, setIsInspectorLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Background Download Progress State
  const [activeDownloadId, setActiveDownloadId] = useState<string | null>(() =>
    localStorage.getItem(ACTIVE_DOWNLOAD_STORAGE_KEY)
  );
  const [activeSnapshot, setActiveSnapshot] = useState<DownloadSnapshotResponse | null>(null);
  const [isStartingDownload, setIsStartingDownload] = useState(false);
  const [isCancellingDownload, setIsCancellingDownload] = useState(false);

  // Dialogs
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [isDownloadOpen, setIsDownloadOpen] = useState(false);
  const [isPitOpen, setIsPitOpen] = useState(false);

  async function loadDatasets() {
    setIsLoading(true);
    setError(null);
    try {
      const versions = await api.listDatasets();
      setDatasetVersions(versions);
      if (versions.length > 0) {
        const firstId = versions[0].id;
        setSelectedVersionId(firstId);
        await selectVersion(firstId);
      } else {
        setSelectedVersionId(null);
        setSelectedCoverage(null);
        setPreviewRows([]);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load market datasets.");
    } finally {
      setIsLoading(false);
    }
  }

  async function selectVersion(versionId: string) {
    setSelectedVersionId(versionId);
    setIsInspectorLoading(true);
    try {
      const [cov, rows] = await Promise.all([
        api.getCoverage(versionId),
        api.getPreview(versionId),
      ]);
      setSelectedCoverage(cov);
      setPreviewRows(rows);
    } catch (err: unknown) {
      console.error("Failed to inspect version:", err);
    } finally {
      setIsInspectorLoading(false);
    }
  }

  // Check for active download on mount
  useEffect(() => {
    void loadDatasets();

    const savedId = localStorage.getItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
    if (savedId) {
      api
        .getDownloadStatus(savedId)
        .then((snap) => {
          setActiveSnapshot(snap);
          if (
            snap.state === "succeeded" ||
            snap.state === "failed" ||
            snap.state === "cancelled"
          ) {
            localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
          } else {
            setActiveDownloadId(savedId);
          }
        })
        .catch(() => {
          localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
        });
    } else {
      api
        .getLatestDownload()
        .then((snap) => {
          if (
            snap.state === "running" ||
            snap.state === "queued" ||
            snap.state === "cancelling"
          ) {
            setActiveDownloadId(snap.download_id);
            setActiveSnapshot(snap);
            localStorage.setItem(ACTIVE_DOWNLOAD_STORAGE_KEY, snap.download_id);
          }
        })
        .catch(() => {
          // No latest download found
        });
    }
  }, []);

  // Poll active download
  useEffect(() => {
    if (!activeDownloadId) return;

    let isMounted = true;
    const interval = setInterval(async () => {
      try {
        const snap = await api.getDownloadStatus(activeDownloadId);
        if (!isMounted) return;
        setActiveSnapshot(snap);

        if (snap.state === "succeeded") {
          localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
          setActiveDownloadId(null);
          void loadDatasets();
        } else if (snap.state === "failed" || snap.state === "cancelled") {
          localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
          setActiveDownloadId(null);
        }
      } catch {
        localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
        if (isMounted) setActiveDownloadId(null);
      }
    }, 750);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [activeDownloadId]);

  async function handleStartDownload(req: CompositeDownloadRequest) {
    setIsStartingDownload(true);
    try {
      const resp = await api.startDownload(req);
      setActiveDownloadId(resp.download_id);
      setActiveSnapshot(resp.snapshot);
      localStorage.setItem(ACTIVE_DOWNLOAD_STORAGE_KEY, resp.download_id);
    } finally {
      setIsStartingDownload(false);
    }
  }

  async function handleCancelDownload() {
    if (!activeSnapshot?.download_id) return;
    setIsCancellingDownload(true);
    try {
      const snap = await api.cancelDownload(activeSnapshot.download_id);
      setActiveSnapshot(snap);
    } catch {
      // If cancellation call fails (e.g. 409 already finished), refresh current status immediately
      try {
        const currentSnap = await api.getDownloadStatus(activeSnapshot.download_id);
        setActiveSnapshot(currentSnap);
        if (
          currentSnap.state === "succeeded" ||
          currentSnap.state === "failed" ||
          currentSnap.state === "cancelled"
        ) {
          localStorage.removeItem(ACTIVE_DOWNLOAD_STORAGE_KEY);
          setActiveDownloadId(null);
        }
      } catch {
        // ignore secondary error
      }
    } finally {
      setIsCancellingDownload(false);
    }
  }

  const previewCols = previewRows.length > 0 ? Object.keys(previewRows[0]).slice(0, 6) : [];

  const isDownloadRunning =
    Boolean(activeSnapshot) &&
    (activeSnapshot?.state === "running" ||
      activeSnapshot?.state === "queued" ||
      activeSnapshot?.state === "cancelling");

  return (
    <>
      <Layout
        height="fill"
        header={
          <LayoutHeader hasDivider padding={2}>
            <HStack justify="between" align="center" style={{ width: "100%" }}>
              <HStack align="center" gap={3}>
                <Heading level={2}>
                  Market Data Catalogue
                </Heading>
                <Badge label={`${datasetVersions.length} Datasets`} variant="purple" />
              </HStack>

              <HStack gap={2}>
                <Button
                  label="Point-in-Time Query"
                  variant="secondary"
                  size="sm"
                  onClick={() => setIsPitOpen(true)}
                  isDisabled={datasetVersions.length === 0}
                />
                <Button
                  label={isDownloadRunning ? "View Download Progress" : "Download Provider Data"}
                  variant={isDownloadRunning ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => setIsDownloadOpen(true)}
                />
                <Button
                  label="Import File"
                  variant="primary"
                  size="sm"
                  onClick={() => setIsImportOpen(true)}
                />
              </HStack>
            </HStack>
          </LayoutHeader>
        }
        content={
          <LayoutContent padding={0} isScrollable>
            {/* Background Download Status Notification */}
            {isDownloadRunning && activeSnapshot && (
              <VStack
                style={{
                  padding: "10px 16px",
                  backgroundColor: "var(--color-background-muted)",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                <HStack justify="between" align="center">
                  <HStack gap={3} align="center">
                    <Spinner size="sm" />
                    <Text style={{ fontWeight: 600 }}>
                      Downloading {activeSnapshot.security_list_id ?? "Composite"}:
                    </Text>
                    <Token label={activeSnapshot.phase} color="blue" />
                    <Text type="supporting">
                      ({activeSnapshot.completed_requests}/{activeSnapshot.total_requests || "?"} reqs)
                    </Text>
                    {activeSnapshot.active_operation && (
                      <Text
                        type="supporting"
                        style={{
                          fontSize: "12px",
                          maxWidth: "300px",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {activeSnapshot.active_operation}
                      </Text>
                    )}
                  </HStack>
                  <Button
                    label="Open Progress Dialog"
                    size="sm"
                    variant="secondary"
                    onClick={() => setIsDownloadOpen(true)}
                  />
                </HStack>
              </VStack>
            )}

            {error && (
              <div style={{ padding: "var(--spacing-3, 12px)" }}>
                <Banner status="error" title="Data Catalogue Error" description={error} />
              </div>
            )}

            {isLoading ? (
              <VStack align="center" justify="center" style={{ height: "300px" }}>
                <Spinner size="lg" />
                <Text type="supporting">Loading Market Datasets…</Text>
              </VStack>
            ) : datasetVersions.length === 0 ? (
              <EmptyState
                title="No Market Datasets Available"
                description="Import CSV, JSON, or Parquet files, or download data from Tiingo, Massive, or SEC EDGAR to populate the DuckDB catalogue."
                actions={
                  <HStack gap={2}>
                    <Button
                      label="Download Provider Data"
                      variant="primary"
                      onClick={() => setIsDownloadOpen(true)}
                    />
                    <Button
                      label="Import Dataset File"
                      variant="secondary"
                      onClick={() => setIsImportOpen(true)}
                    />
                  </HStack>
                }
              />
            ) : (
              <Table isStriped>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Dataset ID</TableHeaderCell>
                    <TableHeaderCell>Source</TableHeaderCell>
                    <TableHeaderCell>Dataset Type</TableHeaderCell>
                    <TableHeaderCell>Coverage Range</TableHeaderCell>
                    <TableHeaderCell>Row Count</TableHeaderCell>
                    <TableHeaderCell>Security List</TableHeaderCell>
                    <TableHeaderCell>Temporal Provenance</TableHeaderCell>
                    <TableHeaderCell>Retrieval Time</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {datasetVersions.map((version) => (
                    <TableRow
                      key={version.id}
                      onClick={() => void selectVersion(version.id)}
                      style={{
                        cursor: "pointer",
                        backgroundColor:
                          selectedVersionId === version.id
                            ? "var(--color-background-muted)"
                            : undefined,
                      }}
                    >
                      <TableCell>
                        <Text style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "12px" }}>
                          {version.id.slice(0, 8)}…
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Badge label={version.source} variant="neutral" />
                      </TableCell>
                      <TableCell>
                        <Token label={version.dataset_type || "daily_bars"} />
                      </TableCell>
                      <TableCell>
                        <Text type="supporting">
                          {version.coverage_start && version.coverage_end
                            ? `${version.coverage_start} to ${version.coverage_end}`
                            : "N/A"}
                        </Text>
                      </TableCell>
                      <TableCell>
                        <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                          {version.row_count.toLocaleString()}
                        </Text>
                      </TableCell>
                      <TableCell>
                        {version.security_list_id ? (
                          <Badge label={version.security_list_id} variant="purple" />
                        ) : (
                          <Text type="supporting">—</Text>
                        )}
                      </TableCell>
                      <TableCell>
                        {version.has_temporal_provenance ? (
                          <Badge label="Complete" variant="green" />
                        ) : (
                          <Badge label="Incomplete" variant="orange" />
                        )}
                      </TableCell>
                      <TableCell>
                        <Text type="supporting" style={{ fontSize: "12px" }}>
                          {new Date(version.retrieval_time).toLocaleString()}
                        </Text>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </LayoutContent>
        }
        end={
          <LayoutPanel width={400} isScrollable>
            {isInspectorLoading ? (
              <VStack align="center" justify="center" style={{ height: "200px" }}>
                <Spinner size="md" />
              </VStack>
            ) : selectedCoverage ? (
              <VStack gap={4}>
                <Heading level={3}>Dataset Version Inspector</Heading>
                <VStack gap={2}>
                  <HStack justify="between">
                    <Text type="supporting">ID</Text>
                    <Text style={{ fontFamily: "var(--font-mono, monospace)", fontSize: "12px" }}>
                      {selectedCoverage.id}
                    </Text>
                  </HStack>
                  <HStack justify="between">
                    <Text type="supporting">Source</Text>
                    <Token label={selectedCoverage.source} />
                  </HStack>
                  <HStack justify="between">
                    <Text type="supporting">Type</Text>
                    <Token label={selectedCoverage.dataset_type || "daily_bars"} />
                  </HStack>
                  {(selectedCoverage.coverage_start || selectedCoverage.coverage_end) && (
                    <HStack justify="between">
                      <Text type="supporting">Coverage Range</Text>
                      <Text type="supporting">
                        {selectedCoverage.coverage_start ?? "—"} to {selectedCoverage.coverage_end ?? "—"}
                      </Text>
                    </HStack>
                  )}
                  <HStack justify="between">
                    <Text type="supporting">Temporal Provenance</Text>
                    <Text type="supporting">
                      {selectedCoverage.has_temporal_provenance ? "Complete" : "Incomplete"}
                    </Text>
                  </HStack>
                  <HStack justify="between">
                    <Text type="supporting">Row Count</Text>
                    <Text>{selectedCoverage.row_count.toLocaleString()}</Text>
                  </HStack>
                  <HStack justify="between">
                    <Text type="supporting">Rejected Rows</Text>
                    <Text>{selectedCoverage.rejected_count}</Text>
                  </HStack>
                </VStack>

                {/* DATA-007: Missing Fields */}
                {selectedCoverage.missing_fields &&
                  Object.keys(selectedCoverage.missing_fields).length > 0 && (
                  <VStack gap={2}>
                    <Heading level={4}>Missing Fields</Heading>
                    <HStack gap={1} style={{ flexWrap: "wrap" }}>
                      {Object.entries(selectedCoverage.missing_fields).map(([field, count]) => (
                        <Token key={field} label={`${field} (${count})`} color="yellow" />
                      ))}
                    </HStack>
                  </VStack>
                )}

                {/* DATA-007: Validation Warnings */}
                {selectedCoverage.warnings && selectedCoverage.warnings.length > 0 && (
                  <VStack gap={2}>
                    <Heading level={4}>Validation Warnings</Heading>
                    <VStack gap={2}>
                      {selectedCoverage.warnings.map((warning, idx) => (
                        <Banner
                          key={idx}
                          status="warning"
                          title={`Warning ${idx + 1}`}
                          description={warning}
                        />
                      ))}
                    </VStack>
                  </VStack>
                )}

                {selectedCoverage.parts && selectedCoverage.parts.length > 0 && (
                  <VStack gap={2}>
                    <Heading level={4}>Composite Parts</Heading>
                    {selectedCoverage.parts.map((part) => (
                      <VStack
                        key={part.id}
                        gap={1}
                        style={{
                          padding: "8px",
                          borderRadius: "var(--radius-sm, 4px)",
                          backgroundColor: "var(--color-background-muted)",
                          border: "1px solid var(--color-border)",
                        }}
                      >
                        <HStack justify="between">
                          <Token label={part.source} />
                          <Token label={part.dataset_type} />
                        </HStack>
                        <HStack justify="between">
                          <Text type="supporting">Rows</Text>
                          <Text type="supporting">{part.row_count.toLocaleString()}</Text>
                        </HStack>
                        {(part.coverage_start || part.coverage_end) && (
                          <HStack justify="between">
                            <Text type="supporting">Coverage</Text>
                            <Text type="supporting">
                              {part.coverage_start ?? "—"} to {part.coverage_end ?? "—"}
                            </Text>
                          </HStack>
                        )}
                        {part.warnings && part.warnings.length > 0 && (
                          <VStack gap={1}>
                            <Text type="supporting" style={{ fontWeight: 600 }}>Part Warnings:</Text>
                            {part.warnings.map((w, wIdx) => (
                              <Text key={wIdx} type="supporting" style={{ fontSize: "11px" }}>• {w}</Text>
                            ))}
                          </VStack>
                        )}
                      </VStack>
                    ))}
                  </VStack>
                )}

                <VStack gap={2}>
                  <Heading level={4}>Data Preview</Heading>
                  {previewRows.length === 0 ? (
                    <Text type="supporting">No preview rows available.</Text>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {previewCols.map((col) => (
                              <TableHeaderCell key={col}>{col}</TableHeaderCell>
                            ))}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {previewRows.slice(0, 10).map((row, idx) => (
                            <TableRow key={idx}>
                              {previewCols.map((col) => (
                                <TableCell key={col}>
                                  <Text>
                                    {row[col] !== null && row[col] !== undefined
                                      ? String(row[col])
                                      : "—"}
                                  </Text>
                                </TableCell>
                              ))}
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </VStack>
              </VStack>
            ) : (
              <EmptyState title="Select a Dataset" description="Click a row in the catalogue to view coverage and details." />
            )}
          </LayoutPanel>
        }
      />

      {/* Modals */}
      <ImportDataDialog
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onSuccess={() => void loadDatasets()}
      />

      <DownloadProviderDialog
        isOpen={isDownloadOpen}
        onClose={() => setIsDownloadOpen(false)}
        activeSnapshot={activeSnapshot}
        onStartDownload={handleStartDownload}
        onCancelDownload={handleCancelDownload}
        isStarting={isStartingDownload}
        isCancelling={isCancellingDownload}
        onSuccess={() => void loadDatasets()}
      />

      <PitQueryDialog
        isOpen={isPitOpen}
        onClose={() => setIsPitOpen(false)}
        datasetVersions={datasetVersions}
      />
    </>
  );
}
