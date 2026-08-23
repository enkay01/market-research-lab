import { useEffect, useState } from "react";
import {
  Banner,
  Button,
  Dialog,
  DialogHeader,
  HStack,
  Text,
  TextInput,
  VStack,
} from "@astryxdesign/core";

interface DeleteConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmationPhrase: string;
  confirmLabel: string;
  isDeleting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteConfirmationDialog({
  isOpen,
  title,
  description,
  confirmationPhrase,
  confirmLabel,
  isDeleting,
  error,
  onClose,
  onConfirm,
}: DeleteConfirmationDialogProps) {
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    if (!isOpen) setConfirmation("");
  }, [isOpen]);

  if (!isOpen) return null;

  const canConfirm = confirmation.trim() === confirmationPhrase;

  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open && !isDeleting) onClose();
      }}
    >
      <DialogHeader title={title} subtitle={description} />
      <VStack gap={4}>
        {error && (
          <Banner status="error" title="Delete failed">
            {error}
          </Banner>
        )}
        <VStack gap={1}>
          <Text type="supporting">
            Type <Text weight="bold">{confirmationPhrase}</Text> to confirm.
          </Text>
          <TextInput
            label="Confirmation"
            value={confirmation}
            onChange={(value) => setConfirmation(String(value ?? ""))}
            isDisabled={isDeleting}
            hasAutoFocus
          />
        </VStack>
        <HStack justify="end" gap={2}>
          <Button
            label="Cancel"
            variant="secondary"
            onClick={onClose}
            type="button"
            isDisabled={isDeleting}
          />
          <Button
            label={confirmLabel}
            variant="primary"
            onClick={onConfirm}
            type="button"
            isLoading={isDeleting}
            isDisabled={!canConfirm || isDeleting}
          />
        </HStack>
      </VStack>
    </Dialog>
  );
}
