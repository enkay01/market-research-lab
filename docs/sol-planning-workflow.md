# Sol planning workflow

Use this workflow only after relevant inspection and before the first high-judgment decision.

## Route the task

Ask Sol for a plan when one or more of these conditions apply:

- Architecture, ownership, or a module boundary has material alternatives.
- A cross-module change has interface, behavior, or sequence tradeoffs.
- A tricky bug still has competing causes or fix strategies.
- Reasoning quality is the main risk to the result.

Keep routine searches, file inspection, bounded diagnostics, known-pattern local changes, documentation, configuration, mechanical edits, command execution, tests, and verification with Luna.

## Prepare the packet

Start one isolated planning agent with model `gpt-5.6-sol`. Give it no inherited turns. Send only a packet of 1,000 to 3,000 tokens with these exact headings:

1. `Sol role`
2. `Current goal`
3. `Relevant files, modules, and behavior`
4. `Hard constraints`
5. `Evidence from attempted approaches`
6. `Pending problems or decisions`

Under `Sol role`, require a structured plan only. Tell Sol not to inspect files, call tools, edit files, run commands or tests, or claim verification.

Include small code excerpts only when they affect the pending decision. Exclude full repository context, unrelated history, secrets, full files, raw command logs, repeated instructions, and completed work that does not affect the decision.

## Require the Sol response

Sol must use these exact headings:

1. `Recommendation`
2. `Assumptions`
3. `Implementation plan`
4. `Verification plan`
5. `Risks, conflicts, and open questions`

Each implementation step must contain `Target`, `Change`, `Reason`, and `Done when`. The verification plan must name checks and expected results without claiming that Sol ran them. Sol must write `None` under an empty section.

## Continue with Luna

Luna checks Sol's assumptions and targets against the current repository state and all active user and project instructions. Hard constraints and repository evidence override the plan.

Luna applies valid steps and performs all edits, commands, tests, and verification. Luna can correct a factual or local mismatch and record the reason. Sol's verification plan is proposed work, not proof. Only Luna's results count.

If new evidence changes the high-judgment decision, send only the evidence delta and affected decision to the same Sol agent. Do not resend the full packet.

Finish when the relevant checks pass. If a check cannot pass, report the unresolved failure and its evidence. If the runtime cannot select `gpt-5.6-sol` or isolate its context, stop before the high-judgment decision and report the blocker.
