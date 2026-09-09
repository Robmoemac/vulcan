---
name: vulcan-augment
description: Add fidelity to an existing Vulcan chart — deepen one area of a master or sub chart on request, e.g. "augment the plotting subchart with more detail on animations". Additive by default; never silently removes existing map content.
---

# vulcan-augment — deepen an existing chart

You are increasing the resolution of a **bounded region** of an existing chart.
You are not rebuilding it.

## COMPLETION CONTRACT — read before you begin

Your work is NOT complete when the scaffolding exists.
Your work is NOT complete when a first draft exists.
Your work is NOT complete when the structure "looks right."
Your work is NOT complete when you have mapped the interesting parts.
Your work is NOT complete when you are running low on context.

Your work is complete when, and only when, this command exits 0:

    vulcan check --strict

That is the entire definition of done. It is not a judgement call, and it is not
yours to make. Run the command. Read the exit code.

### Forbidden stopping points

Do NOT end your turn with any of the following, or any paraphrase:

  - "initial scaffolding is complete"
  - "this provides a good starting point"
  - "the core structure is in place; remaining files follow the same pattern"
  - "I've mapped the main workflows"
  - "let me know if you'd like me to continue"

If you catch yourself composing a sentence like these, you are stopping early.
The correct action is to open `vulcan_mind/_build/worklist.json` and keep working.

"The remaining files follow the same pattern" is never a reason to skip them.
The map's value is precisely that it is exhaustive. A 70%-complete map is not 70%
as useful as a complete one — it is actively misleading, because a reader cannot
tell which absences mean "not present in the codebase" and which mean "not yet
done."

### Context exhaustion is not completion

This task is expected to exceed your context window. That is normal and planned
for. Progress is stored on disk in `vulcan_mind/_build/worklist.json`, not in
your context.

When context runs short:

  1. Finish the file you are on.
  2. Run `vulcan compile` to checkpoint.
  3. State plainly: "Checkpoint: N of M files mapped. Resuming from worklist."
  4. Continue. Do not summarise and stop.

Never report a partial map as a finished one.

### The batch loop

Work in batches of 5-10 source files:

  1. `vulcan worklist --next 8`      → the next files to map
  2. Read each file **completely**. Do not skim; do not infer from filenames.
  3. Write one node doc per mapped symbol; add edges to the chart JSON.
  4. `vulcan compile`
  5. `vulcan check` → fix every error before taking the next batch
  6. Repeat until `vulcan worklist --remaining` reports 0.
  7. `vulcan check --strict` → must exit 0.

### Grounding is checked mechanically — you cannot talk your way past it

Every node names a real file and a real symbol. `vulcan check` **opens the file
and looks for the symbol** (rule V6). Every edge cites a real file where the
connection is observable (rule V7). Node prose is linted against a banned-phrase
list (rule V12).

  REQUIRED:  label `propagate_orbit`, source `src/simulation/propagator.jl:142`
  FORBIDDEN: "a helper function", "the main solver routine", "various utilities"

If you have not opened the file and seen the symbol, you may not write it down.
Invented names fail the gate and you will have to redo the work.

### Do not silence a failing check

If a rule fires, fix the map. Do not edit `vulcan.config.yaml` to remove a banned
phrase, lower `min_doc_words`, disable coverage, or narrow a region so that
unmapped files fall out of scope. If you believe a rule is genuinely wrong, say
so explicitly and ask — changing the gate to pass the gate is the one failure
mode this whole design exists to prevent.
## Step 1 — Bound the augmentation, explicitly

From the request ("augment the plotting subchart with additional fidelity
regarding animations"), identify and state back:

  - target chart: `plotting`
  - target subgraph: nodes reachable from `viz.animate_sequence`
  - fidelity axis: animation frame lifecycle, timing, and state
  - out of scope: static plotting path (already mapped)

Get agreement before editing. Ambiguous augmentation requests produce sprawl.

## Step 2 — Augment

Fidelity is added in four ways. Use whichever the request calls for:

  a. **Decomposition** — expand a coarse node into finer nodes (`expands` set).
  b. **Socket refinement** — split an over-general socket into the real distinct
     inputs/outputs, with real parameter names and types.
  c. **Edge refinement** — replace one vague edge with the several specific
     dataflows it was standing in for; each needs its own `evidence`.
  d. **Doc deepening** — fill in the math, assumptions, and limitations sections
     with real detail: actual equations, actual numerical tolerances, actual
     failure modes.

## Step 3 — Additive discipline (D6)

Augmentation is **additive by default**.

  - Never delete a node or edge whose `origin` is `"human"` — those are the
    user's own edits. Removing them requires `--allow-removal` and an explicit
    instruction.
  - Never reposition existing nodes. The layout engine leaves `ui.pos` alone and
    so do you.
  - If existing content is genuinely *wrong*, do not silently overwrite it.
    State what is wrong, why, and what you propose — then change it only with
    agreement.

## Step 4 — Converge

`vulcan compile && vulcan check --strict` must exit 0.

Augmentation frequently breaks two rules in particular:

  - **V10 (socket parity)** — you refined sockets in frontmatter but an edge
    still references the old socket id. Update the edge.
  - **V5 (acyclicity)** — a finer decomposition can expose a real cycle. If it is
    genuine recursion, classify the back-edge as `kind: "feedback"` (D5). If it
    is not, the decomposition is wrong. Do not disable the rule.

## Completeness for an augmentation

Complete = the stated fidelity axis is at the requested depth **across the whole
bounded subgraph**, not just the first node you touched. If you deepened
`animate_sequence` but left its three children coarse, you are not done.
