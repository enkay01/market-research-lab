import { FormEvent, useEffect, useState } from "react";
import {
  Banner,
  Button,
  CheckboxInput,
  Dialog,
  DialogHeader,
  HStack,
  Text,
  TextInput,
  VStack,
} from "@astryxdesign/core";
import { api, type ProviderDownloadResponse, type SecurityListSummary } from "../api/client";

interface DownloadProviderDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (response: ProviderDownloadResponse) => void;
}

export function DownloadProviderDialog({ isOpen, onClose, onSuccess }: DownloadProviderDialogProps) {
  const [securityLists, setSecurityLists] = useState<SecurityListSummary[]>([]);
  const [selectedListId, setSelectedListId] = useState("us-sector-index-etfs");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [tiingoDaily, setTiingoDaily] = useState(false);
  const [massiveMinute, setMassiveMinute] = useState(false);
  const [secFundamentals, setSecFundamentals] = useState(false);
  const [alpacaOptions, setAlpacaOptions] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
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

    setIsSubmitting(true);
    try {
      const response = await api.downloadDataset({
        security_list_id: selectedListId,
        start_date: startDate,
        end_date: endDate,
        downloads,
      });
      onSuccess(response);
      onClose();
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : "Provider download failed.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogHeader
        title="Download Market Data"
        subtitle="Fetch market data for a fixed Security List across multiple providers in one composite dataset."
      />
      <form onSubmit={handleSubmit}>
        <VStack gap={4}>
          {error && (
            <Banner status="error" title="Download Error" description={error} />
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
                <option key={opt.value} value={opt.value} style={{ backgroundColor: "#1e293b", color: "#f8fafc" }}>
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
              isDisabled={isSubmitting}
            />
            <Button
              label="Download & Ingest"
              variant="primary"
              type="submit"
              isLoading={isSubmitting}
            />
          </HStack>
        </VStack>
      </form>
    </Dialog>
  );
}
