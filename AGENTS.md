# Communication
Always follow responding-to-prompts.md

# Project context and user ergonomics

- **Single user and local environment**: This is a local research tool for Enkay01. It is not multi-tenant enterprise software and is not deployed to the public.
- **No security theatre**: Never add confirmation prompts that require typing random UUIDs, entity names, or confirmation phrases.
- **No defensive warning walls**: Avoid obstructive modal walls or warning banners for local destructive actions like deleting datasets or runs.
- **Fast direct controls**: Prioritize frictionless workflows, checkbox multi-selection, and single-click actions.

# Agent workflow

Read `CONTEXT.md` before changing domain language or implementing market logic.

- **Requirements**: Read `docs/functional-requirements.md` before changing user-visible behavior or acceptance criteria.
- **Design**: Read `docs/software-design.md` before changing module seams, data ownership, persistence, or execution flow.
- **Sequence**: Read `docs/implementation-plan.md` when selecting or scoping the next Epic or story.
- **Modelling**: Read `docs/modelling-techniques.md` when implementing a research paper, theoretical technique, predictive model, or indicator.
- **UI & Astryx**: Read `docs/ui-design.md` when designing, creating, or modifying user interfaces, components, styling, or Astryx design tokens.

## Sol planning handoff

Luna handles ordinary repository work. After relevant inspection, use the Sol planning handoff only when the next decision concerns complex architecture or a module boundary, a cross-module change, a tricky bug, or work where reasoning quality is the main risk. Before Luna selects or edits the approach, read and follow `docs/sol-planning-workflow.md`. Luna performs every command, edit, test, and verification step.

# Shell and CLI execution rules

- **PowerShell strings**: Never interpolate Markdown backticks or text inside double-quoted PowerShell strings (`"..."` or `@"..."@`). PowerShell parses backticks as escape sequences and inserts non-printable ASCII control characters.
- **Git and CLI text payloads**: Pass multi-line text, PR comments, and Markdown through UTF-8 standard input or Python scripts using JSON payloads.
- **File encodings**: Write all files and payloads in UTF-8 without Byte Order Mark (BOM).

