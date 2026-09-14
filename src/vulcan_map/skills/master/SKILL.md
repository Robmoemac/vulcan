---
name: vulcan-map
description: Build the complete Vulcan map of this repository — every in-scope file, function, and dataflow — as a master DAG plus per-node design/ICD documents. Use when the user asks to map, chart, or diagram a codebase, or asks "how does this repo work" at whole-system scale. Produces vulcan_mind/.
---

# vulcan-map — build the master map

You are producing a **complete, grounded map** of this repository: a master DAG of
its workflows, and one detailed design+ICD document per node.

{{include _shared/NOT-DONE.md}}

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

### Step 2b — Scaffold the symbol nodes

    vulcan scaffold

This creates a node and a doc skeleton for every significant symbol the tool can
enumerate — potentially thousands. Structure comes from the source; the prose is
left empty on purpose, so the gate keeps failing until you write it.

Do this before writing any prose. Hand-typing node entries for a real codebase is
slow and gets ids, line numbers and chart membership wrong.

### Step 3 — Trace a run: build the master as the operational flow

The master chart is **not** a diagram of which module includes which. It is the
program in operation, read left to right:

    inputs  →  configure  →  set up run  →  solve loop  →  outputs

Build it by tracing, not by listing directories:

  1. **Start at the entrypoint** the user actually invokes — the CLI `main`, the
     `run_*` function an example script calls, the campaign runner. Read it
     completely.
  2. **Follow the data forward.** At every call that hands work to another
     subsystem, ask: what enters, what is it turned into, what leaves. Each such
     stage is a candidate **phase block** — a `kind: group` node on the master
     named by what it *does* ("Set up run", "Solve loop", "Write results"), never
     by where it lives ("simulation/").
  3. **Make every input explicit.** Every file, dataset, kernel, asset or
     configuration object the program reads is a `kind: external` node with only
     outgoing edges. If a stage reads it, draw the edge, with evidence at the
     read site.
  4. **Make every output explicit.** Every artefact the program writes — result
     tables, bundles, checkpoints, plots, reports, caches — is a `kind: external`
     node with only incoming edges. Its doc states the format, the schema and who
     consumes it. This is how a reader learns what the program *can produce*.
  5. **Give every block a way in.** Each phase block carries
     `opens: <chart_id>` naming the sheet that shows how it works: a module
     subchart, a workflow view, or a generated block sheet. A block that opens
     nothing is a dead end and fails V21.
  6. **Edges are dataflow between phases**, each with `evidence` at the call site
     where the handoff is observable. Containment ("includes", "using") is not an
     edge on the master.

Rule V21 checks all of this mechanically: a source and a sink must exist, every
block must open something, and no node may be a hub. A package tree fails.

**The package structure still exists** — it is just not the master. Put the
module nodes with their `covers:` globs on a `structure` subchart
(`graph/subcharts/structure.graph.json`, `derives_from: master`). Rule V13 reads
coverage from wherever those nodes live, and every module node must still be
expanded to function granularity by a subchart (V13b). A module node may not
claim files outside its own root (V13a).

### Step 3b — Map the symbols, batch by batch

Follow the batch loop in the completion contract. For each file:

  - Read the whole file.
  - Every significant symbol in it already has a scaffolded node (V13e). Your
    job is the prose for each: what it does, its real inputs and outputs, its
    assumptions and limits. One node per symbol — never one standing in for
    the file.
  - Fill **every** section of the node doc. Sections are not optional;
    `min_doc_words` is enforced on prose only, so generated tables cannot pad a
    stub past the floor.
  - Declare real inputs/outputs in frontmatter — actual argument names and types.
    Sockets are authored here and lifted into the chart JSON by the compiler;
    never hand-write sockets into JSON.
  - Add edges for every connection you can *point at*: a call site, an argument
    passed, a struct field written. Each edge needs `evidence` naming the file
    and lines where it is observable.

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
| V13d | A file is claimed but not described | Give it a real node |
| V13e | Symbols in a file have no node of their own | `vulcan scaffold`, then write their prose |
| V12 on `nodes/<module>/src_*.md` | A macro block (group node) generated by compile has no prose | Write what the block *is* — the role of that directory or file |
| V20 | A sheet still renders more than the readability limit | Split it by hand with an explicit subchart; never raise the limit |
| V21 | The master is a package tree, lacks an input/output node, or has an unclickable block | Rebuild it as the operational flow (Step 3); add `external` sources/sinks; set `opens` on every block |

### Step 5 — Report

Report only after `--strict` passes, and **paste the literal output of
`vulcan check --strict --proof`** as the first thing in your report. Without that
block your claim is void; with a block reading `verdict : FAIL` it is also void.

Then state: files mapped, nodes, edges, subchart candidates outstanding, and
anything you deliberately excluded and why.

If you are handing over unfinished — because you ran out of context, hit a limit,
or were interrupted — say so plainly, paste the FAIL proof block, and note that
`vulcan_mind/HANDOFF.md` holds the resumable state. That is a good outcome. A
false "done" is not.
