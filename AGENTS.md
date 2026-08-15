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
