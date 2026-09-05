import { FormEvent, useEffect, useState } from "react";
import {
  Banner,
  Button,
  CheckboxInput,
  Dialog,
  DialogHeader,
  HStack,
  Spinner,
  StatusDot,
  Text,
  TextInput,
  Token,
  VStack,
} from "@astryxdesign/core";
import {
  api,
  type CompositeDownloadRequest,
  type DownloadSnapshotResponse,
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
  onSuccess?: () => void;
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
  const [massiveDaily, setMassiveDaily] = useState(true);
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
  const selectedList = securityLists.find((list) => list.id === selectedListId);
  const calendarDays = Math.max(
    1,
    Math.round((Date.parse(endDate) - Date.parse(startDate)) / 86_400_000) + 1,
  );
  const sessions = Math.max(1, Math.ceil(calendarDays * 5 / 7));
  const memberCount = selectedList?.member_count ?? 0;
  const dailyRequests = massiveDaily ? Math.min(memberCount, sessions) : 0;
  const minuteRequests = massiveMinute ? memberCount : 0;
  const estimatedRequests = dailyRequests + minuteRequests;
  const estimatedSeconds = estimatedRequests * 12.25;
  const dailyAcquisitionSummary = sessions < memberCount
    ? `${dailyRequests.toLocaleString()} grouped-date requests`
    : `${dailyRequests.toLocaleString()} per-symbol range requests`;

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
    if (massiveDaily) {
      downloads.push({ provider: "massive", data_types: ["daily_bars"] });
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
        await api.startDownload(payload);
        if (onSuccess) onSuccess();
        onClose();
      } catch (cause: unknown) {
        const message = cause instanceof Error ? cause.message : "Provider download failed.";
        setError(message);
      } finally {
        setIsSubmittingInternal(false);
      }
    }
  }

  const phaseTokenColor = (
    phase: string
  ): "gray" | "blue" | "green" | "orange" | "purple" => {
    switch (phase.toUpperCase()) {
      case "PLANNING":
        return "blue";
      case "FETCHING":
        return "purple";
      case "VALIDATING":
        return "orange";
      case "STAGING":
      case "PUBLISHING":
        return "blue";
      case "COMPLETE":
        return "green";
      default:
        return "gray";
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
              <StatusDot
                variant={
                  activeSnapshot.state === "failed"
                    ? "error"
                    : activeSnapshot.state === "succeeded"
                    ? "success"
                    : activeSnapshot.state === "cancelling"
                    ? "warning"
                    : "accent"
                }
                label={activeSnapshot.state}
                isPulsing={activeSnapshot.state === "running"}
              />
              <Token
                label={activeSnapshot.phase}
                color={phaseTokenColor(activeSnapshot.phase)}
              />
              <Token
                label={activeSnapshot.state.toUpperCase()}
                color={activeSnapshot.state === "cancelling" ? "orange" : "default"}
              />
            </HStack>
            {activeSnapshot.state === "running" && <Spinner size="sm" />}
          </HStack>

          <VStack
            gap={2}
            style={{
              padding: "12px",
              borderRadius: "var(--radius-sm, 6px)",
              backgroundColor: "var(--color-background-muted)",
              border: "1px solid var(--color-border)",
            }}
          >
            <HStack justify="between">
              <Text type="supporting">Work Units Completed</Text>
              <Text type="supporting">
                {activeSnapshot.completed_logical_units} /{" "}
                {activeSnapshot.total_logical_units}
              </Text>
            </HStack>
            <HStack justify="between">
              <Text type="supporting">HTTP Requests</Text>
              <Text type="supporting">
                {activeSnapshot.completed_requests} / {activeSnapshot.total_requests}
              </Text>
            </HStack>
            {activeSnapshot.active_provider && (
              <HStack justify="between">
                <Text type="supporting">Active Provider</Text>
                <Token label={activeSnapshot.active_provider} />
              </HStack>
            )}
            {activeSnapshot.active_operation && (
              <HStack justify="between">
                <Text type="supporting">Current Operation</Text>
                <Text
                  type="supporting"
                  style={{
                    fontSize: "12px",
                    maxWidth: "260px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {activeSnapshot.active_operation}
                </Text>
              </HStack>
            )}
            {activeSnapshot.rate_limit_wait_seconds > 0 && (
              <HStack justify="between">
                <Text type="supporting">Rate Gate Wait</Text>
                <Token
                  label={`${activeSnapshot.rate_limit_wait_seconds.toFixed(1)}s`}
                  color="orange"
                />
              </HStack>
            )}
          </VStack>

          {(activeSnapshot.recent_events ?? []).length > 0 && (
            <VStack gap={1}>
              <Text type="supporting">Recent Events</Text>
              <VStack
                gap={1}
                style={{
                  maxHeight: "140px",
                  overflowY: "auto",
                  padding: "8px",
                  borderRadius: "var(--radius-sm, 4px)",
                  backgroundColor: "var(--color-background-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                {(activeSnapshot.recent_events ?? []).map((evt, idx) => (
                  <HStack key={idx} gap={2} align="center">
                    <Text
                      type="supporting"
                      style={{
                        color: "var(--color-text-muted)",
                        fontSize: "10px",
                        fontFamily: "var(--font-mono, monospace)",
                      }}
                    >
                      {evt.timestamp.slice(11, 19)}
                    </Text>
                    <Text
                      type="supporting"
                      style={{
                        color: "var(--color-text-secondary)",
                        fontWeight: 600,
                      }}
                    >
                      [{evt.phase}]
                    </Text>
                    <Text type="supporting" style={{ color: "var(--color-text-primary)" }}>
                      {evt.message}
                    </Text>
                  </HStack>
                ))}
              </VStack>
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
                    : activeSnapshot.phase.toUpperCase() === "PUBLISHING"
                    ? "Publishing (Cannot Cancel)"
                    : "Cancel Download"
                }
                variant="destructive"
                onClick={onCancelDownload}
                isDisabled={
                  activeSnapshot.phase.toUpperCase() === "PUBLISHING" ||
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
              <Text type="supporting">Providers</Text>
              <VStack gap={2}>
                <CheckboxInput
                  label="Tiingo daily bars"
                  value={tiingoDaily}
                  onChange={(val) => setTiingoDaily(Boolean(val))}
                />
                <CheckboxInput
                  label="Massive daily bars (recommended broad-market choice)"
                  value={massiveDaily}
                  onChange={(val) => setMassiveDaily(Boolean(val))}
                />
                <CheckboxInput
                  label="Massive minute bars (intraday only)"
                  value={massiveMinute}
                  onChange={(val) => setMassiveMinute(Boolean(val))}
                />
                <Text type="supporting">
                  Minute data is for intraday analysis, not needed for daily Backtests.
                </Text>
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

            {estimatedRequests > 0 && (
              <VStack gap={1}>
                <Text type="supporting">Estimated acquisition time</Text>
                <Text type="supporting">
                  About {Math.ceil(estimatedSeconds / 60)} minutes for {estimatedRequests.toLocaleString()} initial requests at the configured free 12.25-second pacing{massiveDaily ? ` (${dailyAcquisitionSummary} for daily bars)` : ""}. Minute ranges use one initial request per symbol. Pagination, retries, and provider limits can add more time.
                </Text>
              </VStack>
            )}

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
