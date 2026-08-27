import { useEffect } from "react";
import { Button, HStack, Text } from "@astryxdesign/core";

export type DesignVariant = "1" | "2" | "3" | "4" | "5";

interface PrototypeSwitcherProps {
  current: DesignVariant;
  onChange: (variant: DesignVariant) => void;
}

const DESIGN_LABELS = {
  "1": {
    name: "Design 1: Quant Multi-Pane",
    desc: "Stacked Synchronized Panes + Expandable Table Tray (Image 3 Style)",
  },
  "2": {
    name: "Design 2: Candlestick Master",
    desc: "Candle Chart with Strike Channel & Overlaid Ratchet (Image 1 & 4 Style)",
  },
  "3": {
    name: "Design 3: Hybrid Split-Canvas",
    desc: "Side-by-Side Macro Equity & Micro Trade Corridor (Image 2 Style)",
  },
  "4": {
    name: "Design 4: Gantt Lifecycle Matrix",
    desc: "Horizontal Lifecycle Swimlanes + Blocked Ghosts + Table Tray",
  },
  "5": {
    name: "Design 5: Dense Ledger Tear-Sheet",
    desc: "Institutional Table-First Workbench with Deep Inspection Cockpit",
  },
} as const satisfies Record<DesignVariant, { name: string; desc: string }>;

const VARIANTS: DesignVariant[] = ["1", "2", "3", "4", "5"];

export function PrototypeSwitcher({ current, onChange }: PrototypeSwitcherProps) {
  const currentIndex = VARIANTS.indexOf(current);

  const cycleNext = () => {
    const nextIdx = (currentIndex + 1) % VARIANTS.length;
    onChange(VARIANTS[nextIdx]);
  };

  const cyclePrev = () => {
    const prevIdx = (currentIndex - 1 + VARIANTS.length) % VARIANTS.length;
    onChange(VARIANTS[prevIdx]);
  };

  // Keyboard navigation: Left / Right arrow keys
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const activeEl = document.activeElement;
      const isInput =
        activeEl instanceof HTMLInputElement ||
        activeEl instanceof HTMLTextAreaElement ||
        activeEl?.getAttribute("contenteditable") === "true";

      if (isInput) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        cyclePrev();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        cycleNext();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentIndex]);

  const info = DESIGN_LABELS[current] || DESIGN_LABELS["1"];

  return (
    <div
      style={{
        position: "fixed",
        bottom: "20px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 9999,
        backgroundColor: "var(--color-background-card)",
        border: "1px solid var(--color-border-emphasized)",
        borderRadius: "var(--radius-container, 8px)",
        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.36)",
        padding: "8px 16px",
      }}
    >
      <HStack align="center" gap={3}>
        <Button
          label="←"
          variant="secondary"
          size="sm"
          onClick={cyclePrev}
          tooltip="Previous Design (Left Arrow)"
        />

        <HStack align="center" gap={2}>
          <Text weight="bold" style={{ color: "var(--color-text-primary)" }}>
            {info.name}
          </Text>
          <Text type="supporting" style={{ color: "var(--color-text-secondary)" }}>
            — {info.desc}
          </Text>
        </HStack>

        <Button
          label="→"
          variant="secondary"
          size="sm"
          onClick={cycleNext}
          tooltip="Next Design (Right Arrow)"
        />
      </HStack>
    </div>
  );
}
