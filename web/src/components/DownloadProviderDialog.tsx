import { FormEvent, useEffect, useState } from "react";
import {
  Badge,
  Banner,
  Button,
  CheckboxInput,
  Dialog,
  DialogHeader,
  HStack,
  Spinner,
  Text,
  TextInput,
  VStack,
} from "@astryxdesign/core";
import {
  api,
  type CompositeDownloadRequest,
  type DownloadSnapshotResponse,
  type ProviderDownloadResponse,
  type SecurityListSummary,
} from "../api/client";

interface DownloadProviderDialogProps {
  isOpen: boolean;
  onClose: () => void;
  activeSnapshot?: DownloadSnapshotResponse | null;
  onStartDownload?: (request: CompositeDownloadRequest) => Promise<void>;
  onCancelDownload?: () => Promise<void>;
  isStarting?: boolean;
  isCancelling?: boolean;
  onSuccess?: (response: ProviderDownloadResponse) => void;
}

export function DownloadProviderDialog({
  isOpen,
  onClose,
  activeSnapshot,
  onStartDownload,
  onCancelDownload,
  isStarting = false,
  isCancelling = false,
  onSuccess,
}: DownloadProviderDialogProps) {
  const [securityLists, setSecurityLists] = useState<SecurityListSummary[]>([]);
  const [selectedListId, setSelectedListId] = useState("us-sector-index-etfs");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [tiingoDaily, setTiingoDaily] = useState(false);
  const [massiveMinute, setMassiveMinute] = useState(false);
  const [secFundamentals, setSecFundamentals] = useState(false);
  const [alpacaOptions, setAlpacaOptions] = useState(false);
  const [isSubmittingInternal, setIsSubmittingInternal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    let isCurrent = true;
    api
      .getSecurityLists()
      .then((lists) => {
        if (isCurrent && lists.length > 0) {
          setSecurityLists(lists);
        }
      })
      .catch(() => {
        // Fall back to default lists if fetch fails
      });
    return () => {
      isCurrent = false;
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const isJobActive =
    Boolean(activeSnapshot) &&
    (activeSnapshot?.state === "running" ||
      activeSnapshot?.state === "queued" ||
      activeSnapshot?.state === "cancelling");

  const listOptions = securityLists.map((list) => ({
    value: list.id,
    label: `${list.name} (${list.member_count} symbols)`,
  }));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const downloads: Array<{
      provider: "tiingo" | "massive" | "sec_edgar" | "alpaca";
      data_types: string[];
    }> = [];

    if (tiingoDaily) {
      downloads.push({ provider: "tiingo", data_types: ["daily_bars"] });
    }
    if (massiveMinute) {
      downloads.push({ provider: "massive", data_types: ["minute_bars"] });
    }
    if (secFundamentals) {
      downloads.push({ provider: "sec_edgar", data_types: ["fundamentals"] });
    }
    if (alpacaOptions) {
      downloads.push({ provider: "alpaca", data_types: ["options"] });
    }

    if (downloads.length === 0) {
      setError("Select at least one provider to download.");
      return;
    }

    const payload: CompositeDownloadRequest = {
      security_list_id: selectedListId,
      start_date: startDate,
      end_date: endDate,
      downloads,
    };

    if (onStartDownload) {
      try {
        await onStartDownload(payload);
      } catch (cause: unknown) {
        const message = cause instanceof Error ? cause.message : "Failed to start download.";
        setError(message);
      }
    } else {
      setIsSubmittingInternal(true);
      try {
        const response = await api.downloadDataset(payload);
        if (onSuccess) onSuccess(response);
        onClose();
      } catch (cause: unknown) {
        const message = cause instanceof Error ? cause.message : "Provider download failed.";
        setError(message);
      } finally {
        setIsSubmittingInternal(false);
      }
    }
  }

  const phaseVariant = (
    phase: string
  ): "neutral" | "blue" | "green" | "orange" | "red" | "purple" => {
    switch (phase) {
      case "PLANNING":
        return "blue";
      case "FETCHING":
        return "purple";
      case "VALIDATING":
        return "orange";
      case "STAGING":
        return "blue";
      case "PUBLISHING":
        return "blue";
      case "COMPLETE":
        return "green";
      default:
        return "neutral";
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogHeader
        title={isJobActive ? "Download in Progress" : "Download Market Data"}
        subtitle={
          isJobActive
            ? `Active task for security list: ${activeSnapshot?.security_list_id ?? "Composite"}`
            : "Fetch market data for a fixed Security List across multiple providers in one composite dataset."
        }
      />

      {isJobActive && activeSnapshot ? (
        <VStack gap={4} style={{ width: "100%" }}>
          <HStack justify="between" align="center">
            <HStack gap={2} align="center">
              <Badge
                label={activeSnapshot.phase}
                variant={phaseVariant(activeSnapshot.phase)}
              />
              <Badge
                label={activeSnapshot.state.toUpperCase()}
                variant={activeSnapshot.state === "cancelling" ? "orange" : "blue"}
              />
            </HStack>
            {activeSnapshot.state === "running" && <Spinner size="sm" />}
          </HStack>

          <VStack
            gap={2}
            style={{
              padding: "12px",
              borderRadius: "6px",
              backgroundColor: "rgba(255, 255, 255, 0.04)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
            }}
          >
            <HStack justify="between">
              <Text type="caption">Work Units Completed</Text>
              <Text type="caption">
                {activeSnapshot.completed_logical_units} /{" "}
                {activeSnapshot.total_logical_units || "?"}
              </Text>
            </HStack>
            <HStack justify="between">
              <Text type="caption">HTTP Requests</Text>
              <Text type="caption">
                {activeSnapshot.completed_requests} / {activeSnapshot.total_requests || "?"}
              </Text>
            </HStack>
            {activeSnapshot.active_provider && (
              <HStack justify="between">
                <Text type="caption">Active Provider</Text>
                <Badge label={activeSnapshot.active_provider} variant="neutral" />
              </HStack>
            )}
            {activeSnapshot.active_operation && (
              <HStack justify="between">
                <Text type="caption">Current Operation</Text>
                <Text type="supporting" style={{ fontSize: "12px", maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {activeSnapshot.active_operation}
                </Text>
              </HStack>
            )}
            {activeSnapshot.rate_limit_wait_seconds > 0 && (
              <HStack justify="between">
                <Text type="caption">Rate Gate Wait</Text>
                <Badge
                  label={`${activeSnapshot.rate_limit_wait_seconds.toFixed(1)}s`}
                  variant="orange"
                />
              </HStack>
            )}
          </VStack>

          {activeSnapshot.recent_events.length > 0 && (
            <VStack gap={1}>
              <Text type="caption">Recent Events</Text>
              <div
                style={{
                  maxHeight: "140px",
                  overflowY: "auto",
                  padding: "8px",
                  borderRadius: "4px",
                  backgroundColor: "rgba(0, 0, 0, 0.2)",
                  fontSize: "12px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "4px",
                }}
              >
                {activeSnapshot.recent_events.map((evt, idx) => (
                  <div key={idx} style={{ display: "flex", gap: "6px", alignItems: "baseline" }}>
                    <span style={{ color: "rgba(255, 255, 255, 0.4)", fontSize: "10px" }}>
                      {evt.timestamp.slice(11, 19)}
                    </span>
                    <span style={{ color: "rgba(255, 255, 255, 0.7)", fontWeight: 500 }}>
                      [{evt.phase}]
                    </span>
                    <span style={{ color: "inherit" }}>{evt.message}</span>
                  </div>
                ))}
              </div>
            </VStack>
          )}

          <HStack justify="between" gap={2} style={{ marginTop: "8px" }}>
            <Button
              label="Keep in Background"
              variant="secondary"
              onClick={onClose}
              type="button"
            />
            {onCancelDownload && (
              <Button
                label={
                  activeSnapshot.state === "cancelling"
                    ? "Cancelling..."
                    : activeSnapshot.phase === "PUBLISHING"
                    ? "Publishing (Cannot Cancel)"
                    : "Cancel Download"
                }
                variant="destructive"
                onClick={onCancelDownload}
                isDisabled={
                  activeSnapshot.phase === "PUBLISHING" ||
                  activeSnapshot.state === "cancelling" ||
                  isCancelling
                }
                isLoading={isCancelling}
                type="button"
              />
            )}
          </HStack>
        </VStack>
      ) : (
        <form onSubmit={handleSubmit}>
          <VStack gap={4}>
            {error && (
              <Banner status="error" title="Download Error" description={error} />
            )}
            {activeSnapshot?.state === "failed" && activeSnapshot.error_message && (
              <Banner
                status="error"
                title="Previous Download Failed"
                description={activeSnapshot.error_message}
              />
            )}

            <VStack gap={1}>
              <label
                htmlFor="security-list-select"
                style={{
                  fontSize: "14px",
                  fontWeight: 500,
                  color: "inherit",
                }}
              >
                Security List
              </label>
              <select
                id="security-list-select"
                aria-label="Security List"
                value={selectedListId}
                onChange={(e) => setSelectedListId(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  backgroundColor: "rgba(255, 255, 255, 0.05)",
                  color: "inherit",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  fontSize: "14px",
                  outline: "none",
                }}
              >
                {listOptions.map((opt) => (
                  <option
                    key={opt.value}
                    value={opt.value}
                    style={{ backgroundColor: "#1e293b", color: "#f8fafc" }}
                  >
                    {opt.label}
                  </option>
                ))}
              </select>
            </VStack>

            <HStack gap={3}>
              <VStack gap={1} style={{ flex: 1 }}>
                <TextInput
                  label="Start Date (YYYY-MM-DD)"
                  value={startDate}
                  onChange={(val) => setStartDate(String(val ?? ""))}
                  placeholder="2024-01-01"
                  isRequired
                />
              </VStack>
              <VStack gap={1} style={{ flex: 1 }}>
                <TextInput
                  label="End Date (YYYY-MM-DD)"
                  value={endDate}
                  onChange={(val) => setEndDate(String(val ?? ""))}
                  placeholder="2024-12-31"
                  isRequired
                />
              </VStack>
            </HStack>

            <VStack gap={2}>
              <Text type="caption">Providers</Text>
              <VStack gap={2}>
                <CheckboxInput
                  label="Tiingo daily bars"
                  value={tiingoDaily}
                  onChange={(val) => setTiingoDaily(Boolean(val))}
                />
                <CheckboxInput
                  label="Massive minute bars"
                  value={massiveMinute}
                  onChange={(val) => setMassiveMinute(Boolean(val))}
                />
                <CheckboxInput
                  label="SEC EDGAR fundamentals"
                  value={secFundamentals}
                  onChange={(val) => setSecFundamentals(Boolean(val))}
                />
                <CheckboxInput
                  label="Alpaca options"
                  value={alpacaOptions}
                  onChange={(val) => setAlpacaOptions(Boolean(val))}
                />
              </VStack>
            </VStack>

            <HStack justify="end" gap={2}>
              <Button
                label="Cancel"
                variant="secondary"
                onClick={onClose}
                type="button"
                isDisabled={isStarting || isSubmittingInternal}
              />
              <Button
                label="Download & Ingest"
                variant="primary"
                type="submit"
                isLoading={isStarting || isSubmittingInternal}
              />
            </HStack>
          </VStack>
        </form>
      )}
    </Dialog>
  );
}
