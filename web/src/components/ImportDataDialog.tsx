import { FormEvent, useState } from "react";
import {
  Dialog,
  DialogHeader,
  VStack,
  HStack,
  Button,
  TextInput,
  Banner,
  FileInput,
} from "@astryxdesign/core";
import { api } from "../api/client";

interface ImportDataDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (version: { id?: string; dataset_version_id?: string }) => void;
}

export function ImportDataDialog({ isOpen, onClose, onSuccess }: ImportDataDialogProps) {
  const [source, setSource] = useState("daily_prices.csv");
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Please choose a file to import (CSV, JSON, or Parquet).");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await api.importDataset(source, file);
      onSuccess(response as { id?: string; dataset_version_id?: string });
      onClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to import dataset file.";
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
        title="Import Market Dataset File"
        subtitle="Upload CSV, JSON, or Parquet data into the local DuckDB catalogue."
      />
      <form onSubmit={handleSubmit}>
        <VStack gap={4}>
          {error && (
            <Banner status="error" title="Import Error">
              {error}
            </Banner>
          )}

          <VStack gap={1}>
            <TextInput
              label="Source Identifier / Name"
              value={source}
              onChange={(val) => setSource(typeof val === "string" ? val : "")}
              placeholder="e.g. daily_prices.csv"
              isRequired
            />
          </VStack>

          <VStack gap={1}>
            <FileInput
              label="Dataset File"
              value={file}
              onChange={(selected) => {
                const singleFile = Array.isArray(selected) ? selected[0] || null : selected;
                setFile(singleFile);
                if (singleFile && (!source || source === "daily_prices.csv")) {
                  setSource(singleFile.name);
                }
              }}
              accept=".csv,.json,.parquet"
              description="Accepted formats: CSV, JSON, Parquet"
              isRequired
            />
          </VStack>

          <HStack justify="end" gap={2}>
            <Button label="Cancel" variant="secondary" onClick={onClose} type="button" isDisabled={isSubmitting} />
            <Button label="Import Dataset" variant="primary" type="submit" isLoading={isSubmitting} isDisabled={!file} />
          </HStack>
        </VStack>
      </form>
    </Dialog>
  );
}

