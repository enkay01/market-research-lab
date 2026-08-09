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

## Tests and Comments

- Tests are not required merely because production code changed. Add or modify tests only when they protect meaningful observable behavior, a non-trivial invariant or boundary, or a concrete regression.
- Before adding a test, identify the realistic regression it would catch and why existing coverage would not catch it. If the only rationale is coverage, symmetry, or "the code changed," omit the test.
- Do not add tombstone tests whose only purpose is to assert that removed code, routes, fields, or features remain absent. Negative tests are appropriate when the failure or absence is itself a current API, security, or persistence contract.
- Avoid tests that merely mirror literal values, declarative mappings, obvious control flow, or implementation details. For diagnostics and other structured user-visible output, prefer the repository's established UI, snapshot, or integration coverage over redundant partial-string assertions.
- Prefer extending an existing test at the appropriate behavior boundary over adding a new test file, fixture, helper, or test-only abstraction. Do not build test infrastructure that is more complex or brittle than the behavior under test.
- When fixing a real bug, add focused regression coverage at the level where the bug was observed when practical.
- Do not add comments or doc comments that merely restate the code, symbol name, test name, file or module purpose, or obvious control flow. Prefer clearer naming and structure.
- Comments should explain non-obvious rationale, invariants, safety constraints, compatibility requirements, external quirks, or why an apparently simpler alternative is incorrect. Keep them accurate and remove them when they no longer add information.
- 