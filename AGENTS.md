<!-- vulcan-map:begin -->
# Vulcan Map

This repository is mapped with Vulcan Map. The instructions below are the
full skill set — follow them exactly when asked to map, chart, or deepen
the map of this codebase.

**The definition of done is `vulcan check --strict` exiting 0.** Nothing else.

## Skill: `vulcan-map`

*Build the complete Vulcan map of this repository — every in-scope file, function, and dataflow — as a master DAG plus per-node design/ICD documents. Use when the user asks to map, chart, or diagram a codebase, or asks "how does this repo work" at whole-system scale. Produces vulcan_mind/.*

# vulcan-map — build the master map

You are producing a **complete, grounded map** of this repository: a master DAG of
its workflows, and one detailed design+ICD document per node.

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
## Procedure

### Step 1 — Establish scope

Run `vulcan init` if `vulcan_mind/` does not exist.

If the user gave a scope in natural language ("only map the sim code, ignore RL
and GNC"), you must **translate it into an explicit region** before mapping
anything:

  1. Inspect the real directory structure — do not guess at paths.
  2. Draft a concrete region block with literal globs.
  3. Show it to the user and get confirmation:

         region "sim":
           include: src/simulation/**, src/dynamics/**, src/environment/**
           exclude: src/gnc/**, src/rl/**
         → 47 files in scope, 212 excluded. Proceed?

  4. Write it to `vulcan_mind/vulcan.config.yaml` under `regions:`
     (or `vulcan region add sim --include ... --exclude ...`).
  5. Run everything afterwards with `--region sim`.

Never map from an unwritten interpretation of scope. The config file is the
record of what you were asked to do, and rule V11 enforces it.

Excluded regions are not deleted from the map. Where in-scope code calls into
excluded code, create a node with `kind: external` so the boundary is visible
rather than silently truncated.

### Step 2 — Build the worklist

    vulcan worklist --build --region <name>

This enumerates every in-scope file. It is your ledger. It outlives your context.

### Step 3 — Map, batch by batch

Follow the batch loop in the completion contract. For each file:

  - Read the whole file.
  - Identify every public symbol and every significant internal one.
  - Create a node doc from `vulcan_mind/templates/node.md`, filling **every**
    section. Sections are not optional; `min_doc_words` is enforced on prose
    only, so generated tables cannot pad a stub past the floor.
  - Declare real inputs/outputs in frontmatter — actual argument names and types.
    Sockets are authored here and lifted into the chart JSON by the compiler;
    never hand-write sockets into JSON.
  - Add edges to `graph/master.graph.json` for every connection you can *point
    at*: a call site, an argument passed, a struct field written. Each edge needs
    `evidence` naming the file and lines where it is observable.

**Granularity (D3).** The master chart is module-level by default so it stays
readable. A module node must declare `covers:` globs listing the files it
accounts for — that is how rule V13 verifies coverage without one node per file.
A module node may not claim files outside its own module root (V13a), so you
cannot satisfy coverage with one catch-all node.

Every module node must eventually be expanded by a subchart that reaches function
granularity (V13b). Record subchart candidates as you go; the master being
complete does **not** mean the map is complete.

### Step 4 — Converge

Repeat until `vulcan worklist --remaining` reports 0 **and**
`vulcan check --strict` exits 0.

Common failures and what they mean:

| Rule | Meaning | Fix |
|---|---|---|
| V6 | A symbol you named is not in the file you named | Open the file; use the real name |
| V7 | An edge cites a file that does not exist | Point at real code, or drop the edge |
| V10 | A socket is in JSON but not in frontmatter | Declare it in the doc; frontmatter is canonical |
| V12 | Vague prose, or too few words | Write the real content |
| V13 | Files are unaccounted for | You are not finished — keep mapping |
| V13b | A module has no function-level subchart | Run the `vulcan-subchart` skill for it |

### Step 5 — Report

Report only after `--strict` passes. State: files mapped, nodes, edges, subchart
candidates outstanding, and anything you deliberately excluded and why.

## Skill: `vulcan-subchart`

*Produce a focused sub-flowchart isolating one workflow from an existing Vulcan master map — e.g. "chart the plotting workflow" or "show me just the ADCS control loop". Requires an existing vulcan_mind/ master chart.*

# vulcan-subchart — isolate one workflow

You are extracting a single workflow from the master map into its own readable
chart, at finer granularity than the master carries.

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
## Prerequisite

A master chart must exist. If `vulcan_mind/graph/master.graph.json` is absent,
stop and tell the user to run the `vulcan-map` skill first. Do not invent a
master.

## Key constraint — a subchart is a VIEW, not a fork (D9)

Subcharts reference master nodes by ID in `member_nodes`. You may add finer nodes
in `local_nodes`, but each must declare `expands: <master-node-id>`. You may
**not** restate a master node under a new ID (rule V2 rejects duplicate ids), and
you may not contradict the master. If the master is wrong, fix the master.

This is what keeps the maps consistent with each other.

## Procedure

1. **Trace the workflow.** Start from the entry point the user named. Follow real
   call sites and real dataflow through the code — not the master chart alone;
   the master is coarser than what you are producing. Record the member node IDs.

2. **Decide the decomposition.** For each master node in the workflow, judge
   whether function-level detail is warranted. If yes, create local nodes with
   `expands` set, each with its own doc and real source grounding.

3. **Write `graph/subcharts/<id>.graph.json`:**

   ```json
   {
     "schema_version": "1.0.0",
     "chart_id": "plotting",
     "chart_kind": "sub",
     "derives_from": "master",
     "title": "Plotting & Visualisation Workflow",
     "member_nodes": ["viz.plot_trajectory", "io.read_telemetry"],
     "local_nodes": [],
     "local_edges": []
   }
   ```

4. **Edges.** Master edges between two members are inherited automatically — do
   not copy them into the subchart. Add `local_edges` only for connections the
   master does not carry (which is most of them, since you are working at finer
   grain). Every one needs `evidence`.

5. `vulcan compile && vulcan check --strict`.

## Completeness for a subchart

"Complete" means the traced workflow is followed **end to end** — from its entry
point to its terminal effects (file written, state mutated, value returned to
caller).

A subchart that stops at "and then it calls the renderer" is not finished. Follow
it into the renderer, or terminate deliberately at a `kind: external` stub node
and say so. Every dangling thread is either followed or explicitly marked. There
is no third option.

Note that building subcharts is also how the master map becomes complete: rule
V13b fails while any module node has no subchart expanding it to function
granularity.

## Skill: `vulcan-augment`

*Add fidelity to an existing Vulcan chart — deepen one area of a master or sub chart on request, e.g. "augment the plotting subchart with more detail on animations". Additive by default; never silently removes existing map content.*

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
<!-- vulcan-map:end -->
