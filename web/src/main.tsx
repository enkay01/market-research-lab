import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";

import { createRoot } from "react-dom/client";
import { defineTheme, Theme } from "@astryxdesign/core";
import { App } from "./App";

const terminalTheme = defineTheme({
  name: "terminal",
  tokens: {
    "--color-background-body": ["#F1F4F7", "#0B0F19"],
    "--color-background-surface": ["#FFFFFF", "#111827"],
    "--color-background-card": ["#FFFFFF", "#182234"],
    "--color-background-popover": ["#FFFFFF", "#182234"],
    "--color-background-muted": ["#F8FAFC", "#0F172A"],
    "--color-text-primary": ["#0A1317", "#F8FAFC"],
    "--color-text-secondary": ["#4E606F", "#CBD5E1"],
    "--color-text-supporting": ["#64748B", "#94A3B8"],
    "--color-border": ["#E2E8F0", "#334155"],
    "--color-border-emphasized": ["#CBD5E1", "#475569"],
  },
});

const container = document.getElementById("root");
if (container) {
  const root = createRoot(container);
  root.render(
    <Theme theme={terminalTheme} mode="dark">
      <App />
    </Theme>,
  );
}
