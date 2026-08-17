# UI Design and Astryx Design System

Astryx v0.4.1 · 90+ accessible components for React and TypeScript.

---

## 1. Discovery and Workflow

Discover components and layouts before hand-rolling UI:

1. **Build Recipe**: `npx @astryxdesign/cli build "<idea>"` — returns the closest page template, blocks, and components.
2. **Scaffold Template**: `npx @astryxdesign/cli template <name> [--skeleton]` — inspect or scaffold reference layouts.
3. **Inspect Component**: `npx @astryxdesign/cli component <Name>` — view props, variations, and usage examples.
4. **Search System**: `npx @astryxdesign/cli search "<query>"` — find components, hooks, docs, or blocks.
5. **Read Docs**: `npx @astryxdesign/cli docs <topic>` — color, layout, tokens, typography, shape, spacing, theme.

---

## 2. Global Setup

The application entrypoint (`web/src/main.tsx`) must import reset and base styles:

```tsx
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
```

When defining custom themes with `defineTheme`, provide explicit `[light, dark]` token pairs so the CSS `light-dark()` engine resolves correctly in both modes:

```tsx
const terminalTheme = defineTheme({
  name: "terminal",
  tokens: {
    "--color-background-body": ["#F1F4F7", "#0B0F19"],
    "--color-background-surface": ["#FFFFFF", "#111827"],
    "--color-background-card": ["#FFFFFF", "#182234"],
    "--color-text-primary": ["#0A1317", "#F8FAFC"],
    "--color-text-secondary": ["#4E606F", "#CBD5E1"],
    "--color-text-supporting": ["#64748B", "#94A3B8"],
    "--color-border": ["#E2E8F0", "#334155"],
  },
});
```

---

## 3. Core Layout & Component Rules

- **No raw `<div>` or `<span>`**: Astryx layout components (`Layout`, `LayoutHeader`, `LayoutContent`, `LayoutPanel`, `VStack`, `HStack`, `Grid`, `Card`) control all geometry and spacing.
- **Frame First**: Consult `astryx docs layout` before writing screens to structure page regions, panels, and responsive breakpoints.
- **Dense Data**:
  - Render tabular or dense time-series data using `Table`, `TableHeader`, `TableRow`, `TableCell`, or `List`/`Item`.
  - Never wrap repeating list items inside standalone `Card` components.
  - Use `Card` exclusively for isolated metric widgets, parameter panels, or chart containers.
- **Badges vs Tokens**:
  - `Badge` is reserved for numeric counts only.
  - `Token` and `StatusDot` represent entity categories, strategy names, project labels, or lifecycle states.

---

## 4. Design Tokens and WCAG AA/AAA Contrast

- **Component Props First**: Always configure component variants and sizes via props first (e.g. `variant="primary"`, `size="sm"`).
- **Exact Token Names**: Use verified Astryx CSS custom property names. Never invent token names:
  - Surface & Card: `var(--color-background-surface)`, `var(--color-background-card)`, `var(--color-background-muted)`, `var(--color-background-wash)`
  - Text: `var(--color-text-primary)`, `var(--color-text-secondary)`, `var(--color-text-supporting)`, `var(--color-text-green)`, `var(--color-text-red)`, `var(--color-text-blue)`, `var(--color-text-orange)`
  - Icons & Strokes: `var(--color-icon-blue)`, `var(--color-icon-orange)`, `var(--color-icon-red)`, `var(--color-icon-green)`
  - Borders: `var(--color-border)`, `var(--color-border-emphasized)`
  - Spacing & Radii: `var(--spacing-1)` through `var(--spacing-8)`, `var(--radius-element)`, `var(--radius-container)`
- **No Hardcoded Hex Fallbacks in `var()`**:
  - **Never** write `var(--color-bg-surface, #ffffff)` or `var(--color-text-danger, #991b1b)`. Light hex fallbacks break contrast when rendered in dark mode.
- **Contrast Ratios**:
  - Ensure all body copy, inputs, headings, and data cells achieve at least **4.5:1** contrast ratio (WCAG AA), and prominent KPIs/charts achieve at least **7:1** (WCAG AAA) in dark terminal mode.

---

## 5. Visual Verification Loop

Before completing frontend modifications:
1. Re-read edited files to eliminate raw `<div>`, non-existent token names, or hardcoded hex colors.
2. Run `npm run check` in `web/` to ensure full TypeScript type safety and OpenAPI client synchronization.
3. Run automated UI screenshot capture (e.g. `node web/scripts/capture_ui.js`) to visually verify layout contrast, theme styling, and interaction flows.
