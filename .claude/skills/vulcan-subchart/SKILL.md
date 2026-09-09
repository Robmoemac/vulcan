---
name: vulcan-subchart
description: Produce a focused sub-flowchart isolating one workflow from an existing Vulcan master map — e.g. "chart the plotting workflow" or "show me just the ADCS control loop". Requires an existing vulcan_mind/ master chart.
---

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
