import {
  Banner,
  Button,
  Dialog,
  DialogHeader,
  HStack,
  VStack,
} from "@astryxdesign/core";

interface DeleteConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  isDeleting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export function DeleteConfirmationDialog({
  isOpen,
  title,
  description,
  confirmLabel = "Delete",
  isDeleting,
  error,
  onClose,
  onConfirm,
}: DeleteConfirmationDialogProps) {
  if (!isOpen) return null;

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
          <Banner status="error" title="Delete failed" description={error} />
        )}
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
            isDisabled={isDeleting}
          />
        </HStack>
      </VStack>
    </Dialog>
  );
}

