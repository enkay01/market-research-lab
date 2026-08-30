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
  const [provider, setProvider] = useState<"massive" | "alpaca" | "tiingo" | "sec_edgar">("massive");
  const [symbols, setSymbols] = useState("AAPL, MSFT");
  const [ciks, setCiks] = useState("0000320193");
  const [massiveType, setMassiveType] = useState<"daily_bars" | "minute_bars" | "option_contracts" | "option_trades">("daily_bars");
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

      let requestPayload: any;
      if (provider === "massive") {
        requestPayload = {
          provider: "massive" as const,
          symbol: parsedSymbols[0] ?? "SPY",
          dataset_type: massiveType,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        };
      } else if (provider === "tiingo") {
        requestPayload = {
          provider: "tiingo" as const,
          symbols: parsedSymbols,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        };
      } else if (provider === "sec_edgar") {
        requestPayload = {
          provider: "sec_edgar" as const,
          ciks: parsedCiks,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        };
      } else {
        requestPayload = {
          provider: "alpaca" as const,
          symbol: parsedSymbols[0] ?? "",
          start_date: startDate,
          end_date: endDate,
        };
      }

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
        title="Download Market Data"
        subtitle="Fetch market data directly into the local catalog from Massive (Polygon), Alpaca, Tiingo, or SEC EDGAR."
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
              layout="fill"
              value={provider}
              onChange={(val) => {
                // SAFETY: Value is constrained by SegmentedControlItem values
                setProvider(val as "massive" | "alpaca" | "tiingo" | "sec_edgar");
              }}
              <SegmentedControlItem value="massive" label="Massive / Polygon (Stocks & Options)" />
              <SegmentedControlItem value="alpaca" label="Alpaca (Options Minutes)" />
              <SegmentedControlItem value="tiingo" label="Tiingo (EOD Prices)" />
              <SegmentedControlItem value="sec_edgar" label="SEC EDGAR" />
            </SegmentedControl>
          </VStack>

          {provider === "massive" && (
            <VStack gap={1}>
              <Text weight="medium">Data Feed Type</Text>
              <SegmentedControl
                label="Select Feed Type"
                value={massiveType}
                onChange={(val) => {
                  // SAFETY: Value is constrained by SegmentedControlItem values
                  setMassiveType(val as "daily_bars" | "minute_bars" | "option_contracts" | "option_trades");
                }}
              >
                <SegmentedControlItem value="daily_bars" label="Daily Bars" />
                <SegmentedControlItem value="minute_bars" label="Minute Bars" />
                <SegmentedControlItem value="option_contracts" label="Put Option Contracts" />
                <SegmentedControlItem value="option_trades" label="Option Minute Trades" />
              </SegmentedControl>
            </VStack>
          )}

          {provider === "tiingo" || provider === "alpaca" || provider === "massive" ? (
            <VStack gap={1}>
              <TextInput
                label={provider === "tiingo" ? "Ticker Symbols (comma-separated)" : "Underlying Symbol"}
                value={symbols}
                onChange={(val) => setSymbols(String(val ?? ""))}
                placeholder="e.g. SPY, AAPL, MSFT"
                isRequired
                description={
                  provider === "massive"
                    ? "Requires MASSIVE_API_KEY or POLYGON_API_KEY in local .env.local or process environment."
                    : provider === "alpaca"
                      ? "Requires ALPACA_API_KEY and ALPACA_API_SECRET in local .env.local."
                      : "Requires TIINGO_API_TOKEN in local .env.local."
                }
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
