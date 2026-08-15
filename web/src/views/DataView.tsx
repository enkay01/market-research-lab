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
  type CoverageResponse,
} from "../api/client";
import { ImportDataDialog } from "../components/ImportDataDialog";
import { DownloadProviderDialog } from "../components/DownloadProviderDialog";
import { PitQueryDialog } from "../components/PitQueryDialog";

export function DataView() {
  const [datasetVersions, setDatasetVersions] = useState<CoverageResponse[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedCoverage, setSelectedCoverage] = useState<CoverageResponse | null>(null);
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isInspectorLoading, setIsInspectorLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    void loadDatasets();
  }, []);

  const previewCols = previewRows.length > 0 ? Object.keys(previewRows[0]).slice(0, 6) : [];

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
                  label="Download Provider Data"
                  variant="secondary"
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
            {error && (
              <div style={{ padding: "var(--spacing-3, 12px)" }}>
                <Banner status="error" title="Data Catalogue Error">
                  {error}
                </Banner>
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
                description="Import CSV, JSON, or Parquet files, or download data from Tiingo or SEC EDGAR to populate the DuckDB catalogue."
                actions={
                  <Button
                    label="Import Dataset File"
                    variant="primary"
                    onClick={() => setIsImportOpen(true)}
                  />
                }
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>Source</TableHeaderCell>
                    <TableHeaderCell>Version ID</TableHeaderCell>
                    <TableHeaderCell>Dataset Type</TableHeaderCell>
                    <TableHeaderCell>Valid Rows</TableHeaderCell>
                    <TableHeaderCell>Date Coverage</TableHeaderCell>
                    <TableHeaderCell>Temporal Provenance</TableHeaderCell>
                    <TableHeaderCell>Retrieved At</TableHeaderCell>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {datasetVersions.map((v) => {
                    const isSelected = v.id === selectedVersionId;
                    return (
                      <TableRow
                        key={v.id}
                        onClick={() => void selectVersion(v.id)}
                        style={{
                          cursor: "pointer",
                          backgroundColor: isSelected
                            ? "var(--color-background-wash, rgba(255, 255, 255, 0.08))"
                            : undefined,
                        }}
                      >
                        <TableCell>
                          <Text weight="medium">{v.source}</Text>
                        </TableCell>
                        <TableCell>
                          <Text hasTabularNumbers>
                            {v.id.slice(0, 8)}
                          </Text>
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
                          {v.has_temporal_provenance ? (
                            <Token label="Eligible (PIT)" color="green" />
                          ) : (
                            <Token label="Research Only" color="yellow" />
                          )}
                        </TableCell>
                        <TableCell>
                          <Text type="supporting">
                            {new Date(v.retrieval_time).toLocaleString()}
                          </Text>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </LayoutContent>
        }
        end={
          <LayoutPanel
            width={400}
            hasDivider
            isScrollable
            label="Dataset Details"
          >
            {isInspectorLoading ? (
              <VStack align="center" justify="center" style={{ height: "200px" }}>
                <Spinner size="md" />
                <Text type="supporting">Loading version details…</Text>
              </VStack>
            ) : selectedCoverage ? (
              <VStack gap={4} style={{ padding: "16px" }}>
                <VStack gap={1}>
                  <Heading level={3}>
                    {selectedCoverage.source}
                  </Heading>
                  <Text type="supporting" hasTabularNumbers>
                    ID: {selectedCoverage.id}
                  </Text>
                </VStack>

                {/* Validation Banner */}
                {selectedCoverage.rejected_count > 0 ? (
                  <Banner status="warning" title="Rejected Rows Detected">
                    {selectedCoverage.rejected_count} rows rejected during ingestion.
                    {selectedCoverage.warnings.map((w: string, i: number) => (
                      <Text key={i}>{w}</Text>
                    ))}
                  </Banner>
                ) : (
                  <Banner status="success" title="Validated Point-in-Time Dataset">
                    All {selectedCoverage.row_count} rows parsed and verified against point-in-time rules.
                  </Banner>
                )}

                {/* Record Summary Table */}
                <VStack gap={2}>
                  <Text weight="semibold">
                    Record Breakdown
                  </Text>
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell><Text weight="medium">Total Rows</Text></TableCell>
                        <TableCell>{selectedCoverage.row_count.toLocaleString()}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="medium">Rejected Rows</Text></TableCell>
                        <TableCell>{selectedCoverage.rejected_count.toLocaleString()}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="medium">Total Warnings</Text></TableCell>
                        <TableCell>{selectedCoverage.total_warnings}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text weight="medium">Dataset Type</Text></TableCell>
                        <TableCell>{selectedCoverage.dataset_type}</TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </VStack>

                {/* Time Coverage */}
                <VStack gap={2}>
                  <Text weight="semibold">
                    Temporal Provenance Bounds
                  </Text>
                  <Table>
                    <TableBody>
                      <TableRow>
                        <TableCell><Text type="supporting">Coverage Start</Text></TableCell>
                        <TableCell><Text>{selectedCoverage.coverage_start || "—"}</Text></TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text type="supporting">Coverage End</Text></TableCell>
                        <TableCell><Text>{selectedCoverage.coverage_end || "—"}</Text></TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell><Text type="supporting">Retrieval Time</Text></TableCell>
                        <TableCell><Text>{new Date(selectedCoverage.retrieval_time).toLocaleString()}</Text></TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </VStack>

                {/* Raw Preview Rows */}
                <VStack gap={2}>
                  <HStack justify="between" align="center">
                    <Text weight="semibold">Data Preview</Text>
                    <Text type="supporting">{previewRows.length} sample rows</Text>
                  </HStack>

                  {previewRows.length === 0 ? (
                    <Text type="supporting">No preview records available.</Text>
                  ) : (
                    <div style={{ overflow: "auto", maxHeight: "200px" }}>
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

