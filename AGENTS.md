Write in ASD-STE100 but for a 20 year old.
# Agent workflow

Read `CONTEXT.md` before changing domain language or implementing market logic.

- **Requirements**: Read `docs/functional-requirements.md` before changing user-visible behavior or acceptance criteria.
- **Design**: Read `docs/software-design.md` before changing module seams, data ownership, persistence, or execution flow.
- **Sequence**: Read `docs/implementation-plan.md` when selecting or scoping the next Epic or story.

## Implementing a Modelling Technique

Use this workflow whenever the request supplies a research-paper link, article, summary, or theoretical technique and asks for an implementation.

1. **Summarize**
   - Cite the supplied source or identify the supplied summary.
   - Separate the source's claims from your interpretation.
   - State the hypothesis, required inputs, prediction or holding horizon, and claimed evaluation method.
   - Identify missing information and resolve factual gaps from primary sources where possible.
   - Finish when another engineer could explain what will be tested and what result would falsify it.

2. **Plan**
   - Map the technique to data ingestion, temporal eligibility, features, Predictive Models or Indicators, Strategy rules, a reproducible Run, and reporting.
   - Name every new or changed module, dependency, Definition Revision, and test.
   - Call out look-ahead, survivorship, selection, label, and execution-timing risks explicitly.
   - Keep the technique inactive until the implementation and validation are complete.
   - Finish when every claimed capability maps to an implementation artifact and verification step.

3. **Implement**
   - Implement the technique as ordinary product code; preserve the citation and implementation summary, not a local archive of the source.
   - Integrate through existing module interfaces. Introduce a new interface only when behavior genuinely varies.
   - Add dependencies to the project's locked environment. Keep global Python installations untouched.
   - Create new Definition Revisions instead of rewriting revisions referenced by existing results.
   - Run generated code in a subprocess and expose the technique in the application only after validation.

4. **Validate**
   - Use chronological splits and out-of-sample evaluation.
   - Fit features, preprocessors, and Predictive Models only on information eligible at that simulated time.
   - Add synthetic tests that fail if future observations leak into training, Signals, or fills.
   - Pin random seeds where supported and compare results with a naive benchmark.
   - Report costs, assumptions, warnings, limitations, and unsupported claims alongside performance.
   - Finish when tests pass, the example Run reproduces, and every result identifies its Dataset Versions and Definition Revisions.

5. **Hand off**
   - Summarize changed artifacts, verification evidence, example results, limitations, and the exact command that reproduces the Run.
   - Leave activation to the Analyst. Implemented techniques do not execute or route orders.

<!-- ASTRYX:START -->
Astryx v0.4.1 · 90+ components
CLI: run every command as `npx @astryxdesign/cli <cmd>` (shown below as `astryx ...`).

SETUP (once, in your app entry e.g. main.tsx) — without these, components render unstyled:
  import "@astryxdesign/core/reset.css";
  import "@astryxdesign/core/astryx.css";

WORKFLOW — discover, don't guess. Before writing UI:
1. `astryx build "<idea>"` — START HERE: returns a kit (closest [page] + [block]s + [component]s). No args = full playbook.
2. `astryx template <name> [--skeleton]` — scaffold the [page]/[block]s it named, or study their layout. Templates are reference code.
3. `astryx component <Name>` — props + examples for every component you use.

RULES:
- No <div> — components do all layout/spacing, page frame included.
- Frame first: read `astryx docs layout` before writing any page or screen — page frame, region widths, breakpoint behavior.
- Dense data = rows (Table, List/Item), never Card-wrapped list items; Card is for standalone widgets. Status = StatusDot/Token; Badge = counts only.
- Custom styling: component props first; else style/className with tokens — var(--color-*|--spacing-*|--radius-*). No raw hex/px. (No StyleX/Tailwind compiler here — don't use xstyle/utility classes.)
- Tokens for every value (`astryx docs tokens`). Brand/accent via `astryx theme` — never override --color-* in :root.
- SELF-CHECK before you finish: re-read the file and replace any raw <div>/<span> layout, imported .css/@apply, or hardcoded value (#hex, 16px) with the component or a token (var(--color-*|--spacing-*|…)). If unsure a component/prop exists, run `astryx component <Name>` / `astryx search "<thing>"`; don't hand-roll CSS.

MORE CLI:
  search "<query>"   find any component / hook / doc / template / block
  component --list   90+ components by category
  template --list    page + block recipes
  docs <topic>       color, elevation, icons, illustrations, internationalization, layout, migration, motion, principles, shape, spacing, styling, theme, tokens, typography
  swizzle <Name>     eject component source for deep customization
  upgrade --apply    run after any @astryxdesign/core bump
<!-- ASTRYX:END -->
