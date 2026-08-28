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
} from "@astryxdesign/core";
import { api, type ProviderDownloadResponse } from "../api/client";

interface DownloadProviderDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (response: ProviderDownloadResponse) => void;
}

export function DownloadProviderDialog({ isOpen, onClose, onSuccess }: DownloadProviderDialogProps) {
  const [provider, setProvider] = useState<"tiingo" | "sec_edgar" | "alpaca">("tiingo");
  const [symbols, setSymbols] = useState("AAPL, MSFT");
  const [ciks, setCiks] = useState("0000320193");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const parsedSymbols = symbols
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const parsedCiks = ciks
        .split(",")
        .map((c) => c.trim())
        .filter(Boolean);

      const requestPayload =
        provider === "tiingo"
          ? {
              provider: "tiingo" as const,
              symbols: parsedSymbols,
              start_date: startDate || undefined,
              end_date: endDate || undefined,
            }
          : provider === "sec_edgar"
            ? {
                provider: "sec_edgar" as const,
                ciks: parsedCiks,
                start_date: startDate || undefined,
                end_date: endDate || undefined,
              }
            : {
                provider: "alpaca" as const,
                symbol: parsedSymbols[0] ?? "",
                start_date: startDate,
                end_date: endDate,
              };

      const response = await api.downloadDataset(requestPayload);

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
        title="Download Provider Data"
        subtitle="Fetch market data directly into the local catalogue. Credentials stay in local configuration."
      />
      <form onSubmit={handleSubmit}>
        <VStack gap={4}>
          {error && (
            <Banner status="error" title="Download Error">
              {error}
            </Banner>
          )}

          <VStack gap={1}>
            <Text weight="medium">Data Provider</Text>
            <SegmentedControl
              label="Select Provider"
              value={provider}
              onChange={(val) => {
                // SAFETY: Value is constrained by SegmentedControlItem values
                setProvider(val as "tiingo" | "sec_edgar" | "alpaca");
              }}
            >
              <SegmentedControlItem value="tiingo" label="Tiingo (EOD Prices & Actions)" />
              <SegmentedControlItem value="sec_edgar" label="SEC EDGAR (Fundamentals)" />
              <SegmentedControlItem value="alpaca" label="Alpaca (Options Minutes)" />
            </SegmentedControl>
          </VStack>

          {provider === "tiingo" || provider === "alpaca" ? (
            <VStack gap={1}>
              <TextInput
                label={provider === "alpaca" ? "Underlying Symbol" : "Ticker Symbols (comma-separated)"}
                value={symbols}
                onChange={(val) => setSymbols(String(val ?? ""))}
                placeholder="e.g. AAPL, MSFT, SPY"
                isRequired
                description={provider === "alpaca" ? "Requires ALPACA_API_KEY and ALPACA_API_SECRET in local .env.local or process environment." : "Requires TIINGO_API_TOKEN in local .env.local or process environment."}
              />
            </VStack>
          ) : (
            <VStack gap={1}>
              <TextInput
                label="SEC CIKs or Tickers (comma-separated)"
                value={ciks}
                onChange={(val) => setCiks(String(val ?? ""))}
                placeholder="e.g. 0000320193, 0000789019"
                isRequired
                description="Identified via SEC_EDGAR_USER_AGENT in local configuration."
              />
            </VStack>
          )}

          <HStack gap={3}>
            <VStack gap={1} style={{ flex: 1 }}>
              <TextInput
                label="Start Date (YYYY-MM-DD)"
                value={startDate}
                onChange={(val) => setStartDate(String(val ?? ""))}
                placeholder="2024-01-01"
              />
            </VStack>
            <VStack gap={1} style={{ flex: 1 }}>
              <TextInput
                label="End Date (YYYY-MM-DD)"
                value={endDate}
                onChange={(val) => setEndDate(String(val ?? ""))}
                placeholder="2024-12-31"
              />
            </VStack>
          </HStack>

          <HStack justify="end" gap={2}>
            <Button label="Cancel" variant="secondary" onClick={onClose} type="button" isDisabled={isSubmitting} />
            <Button label="Download & Ingest" variant="primary" type="submit" isLoading={isSubmitting} />
          </HStack>
        </VStack>
      </form>
    </Dialog>
  );
}
