---
name: vulcan-subchart
description: Produce a focused sub-flowchart isolating one workflow from an existing Vulcan master map — e.g. "chart the plotting workflow" or "show me just the ADCS control loop". Requires an existing vulcan_mind/ master chart.
---

# vulcan-subchart — isolate one workflow

You are extracting a single workflow from the master map into its own readable
chart, at finer granularity than the master carries.

{{include _shared/NOT-DONE.md}}

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
