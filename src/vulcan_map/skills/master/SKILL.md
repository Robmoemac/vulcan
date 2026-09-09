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

Report only after `--strict` passes, and **paste the literal output of
`vulcan check --strict --proof`** as the first thing in your report. Without that
block your claim is void; with a block reading `verdict : FAIL` it is also void.

Then state: files mapped, nodes, edges, subchart candidates outstanding, and
anything you deliberately excluded and why.

If you are handing over unfinished — because you ran out of context, hit a limit,
or were interrupted — say so plainly, paste the FAIL proof block, and note that
`vulcan_mind/HANDOFF.md` holds the resumable state. That is a good outcome. A
false "done" is not.
