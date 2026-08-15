import { FormEvent, useState } from "react";
import {
  Dialog,
  DialogHeader,
  VStack,
  HStack,
  Button,
  TextInput,
  Text,
  Banner,
  SegmentedControl,
  SegmentedControlItem,
  Table,
  TableHeader,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Token,
  Selector,
} from "@astryxdesign/core";
import { api, type CoverageResponse } from "../api/client";

interface PitQueryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  datasetVersions: CoverageResponse[];
}

export function PitQueryDialog({ isOpen, onClose, datasetVersions }: PitQueryDialogProps) {
  const [selectedVersionId, setSelectedVersionId] = useState(
    datasetVersions[0]?.id || "",
  );
  const [queryType, setQueryType] = useState<"history" | "fundamentals" | "actions">("history");
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 16));
  const [symbol, setSymbol] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [results, setResults] = useState<Record<string, unknown>[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedVersionId) {
      setError("Please select a Dataset Version.");
      return;
    }

    setIsQuerying(true);
    setError(null);
    setResults(null);

    try {
      let data: Record<string, unknown>[] = [];
      const params = { as_of: asOf || undefined, symbol: symbol || undefined };

      if (queryType === "history") {
        data = (await api.getHistory(selectedVersionId, params)) as Record<string, unknown>[];
      } else if (queryType === "fundamentals") {
        data = (await api.getFundamentals(selectedVersionId, params)) as Record<string, unknown>[];
      } else {
        data = (await api.getCorporateActions(selectedVersionId, params)) as Record<string, unknown>[];
      }

      setResults(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Point-in-time query failed.";
      setError(message);
    } finally {
      setIsQuerying(false);
    }
  }

  const columns = results && results.length > 0 ? Object.keys(results[0]).slice(0, 7) : [];

  const versionOptions = datasetVersions.map((v) => ({
    value: v.id,
    label: `${v.source} (${v.id.slice(0, 8)})`,
  }));

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogHeader
        title="Point-in-Time (PIT) As-Of Query"
        subtitle="Verify point-in-time data eligibility and exclude future observations beyond the specified time."
      />
      <form onSubmit={handleQuery}>
        <VStack gap={4}>
          {error && (
            <Banner status="error" title="Query Error">
              {error}
            </Banner>
          )}

          <HStack gap={3}>
            <VStack gap={1} style={{ flex: 1 }}>
              <Selector
                label="Dataset Version"
                options={versionOptions}
                value={selectedVersionId}
                onChange={(val) => setSelectedVersionId(val)}
                isRequired
              />
            </VStack>

            <VStack gap={1} style={{ flex: 1 }}>
              <Text weight="medium">Record Type</Text>
              <SegmentedControl
                label="Record Type"
                value={queryType}
                onChange={(val) => setQueryType(val as "history" | "fundamentals" | "actions")}
              >
                <SegmentedControlItem value="history" label="Daily Bars" />
                <SegmentedControlItem value="fundamentals" label="Facts" />
                <SegmentedControlItem value="actions" label="Actions" />
              </SegmentedControl>
            </VStack>
          </HStack>

          <HStack gap={3}>
            <VStack gap={1} style={{ flex: 1 }}>
              <TextInput
                label="As-Of Timestamp (ISO)"
                value={asOf}
                onChange={(val) => setAsOf(typeof val === "string" ? val : "")}
                placeholder="2024-01-01T00:00:00"
              />
            </VStack>
            <VStack gap={1} style={{ flex: 1 }}>
              <TextInput
                label="Filter Symbol (optional)"
                value={symbol}
                onChange={(val) => setSymbol(typeof val === "string" ? val : "")}
                placeholder="e.g. AAPL"
              />
            </VStack>
          </HStack>

          <HStack justify="end" gap={2}>
            <Button label="Close" variant="secondary" onClick={onClose} type="button" />
            <Button label="Run As-Of Query" variant="primary" type="submit" isLoading={isQuerying} />
          </HStack>

          {results !== null && (
            <VStack gap={2}>
              <HStack justify="between" align="center">
                <Text weight="semibold">Query Results</Text>
                <Token label={`${results.length} records eligible`} color="blue" />
              </HStack>

              {results.length === 0 ? (
                <Banner status="info" title="No Eligible Records">
                  No records found with availability time earlier than or equal to {asOf}.
                </Banner>
              ) : (
                <div style={{ maxHeight: "240px", overflow: "auto" }}>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {columns.map((col) => (
                          <TableHeaderCell key={col}>{col}</TableHeaderCell>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {results.slice(0, 15).map((row, idx) => (
                        <TableRow key={idx}>
                          {columns.map((col) => (
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
          )}
        </VStack>
      </form>
    </Dialog>
  );
}

