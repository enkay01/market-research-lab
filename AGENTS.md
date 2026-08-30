Write in ASD-STE100 but for a 20 year old.
# Agent workflow

Read `CONTEXT.md` before changing domain language or implementing market logic.

- **Requirements**: Read `docs/functional-requirements.md` before changing user-visible behavior or acceptance criteria.
- **Design**: Read `docs/software-design.md` before changing module seams, data ownership, persistence, or execution flow.
- **Sequence**: Read `docs/implementation-plan.md` when selecting or scoping the next Epic or story.
- **Modelling**: Read `docs/modelling-techniques.md` when implementing a research paper, theoretical technique, predictive model, or indicator.
- **UI & Astryx**: Read `docs/ui-design.md` when designing, creating, or modifying user interfaces, components, styling, or Astryx design tokens.

# Shell and CLI execution rules

- **PowerShell strings**: Never interpolate Markdown backticks or text inside double-quoted PowerShell strings (`"..."` or `@"..."@`). PowerShell parses backticks as escape sequences and inserts non-printable ASCII control characters.
- **Git and CLI text payloads**: Pass multi-line text, PR comments, and Markdown through UTF-8 standard input or Python scripts using JSON payloads.
- **File encodings**: Write all files and payloads in UTF-8 without Byte Order Mark (BOM).

