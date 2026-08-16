import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";

import { createRoot } from "react-dom/client";
import { defineTheme, Theme } from "@astryxdesign/core";
import { App } from "./App";

const terminalTheme = defineTheme({
  name: "terminal",
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
