---
name: vulcan-augment
description: Add fidelity to an existing Vulcan chart — deepen one area of a master or sub chart on request, e.g. "augment the plotting subchart with more detail on animations". Additive by default; never silently removes existing map content.
---

# vulcan-augment — deepen an existing chart

You are increasing the resolution of a **bounded region** of an existing chart.
You are not rebuilding it.

{{include _shared/NOT-DONE.md}}

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
  - **V12 on a `src_*.md` group doc** — adding symbols pushed a sheet over the
    readability limit, so compile clustered it (D13) and scaffolded a doc for
    the new macro block. Write it. Never edit the generated nested chart.

## Completeness for an augmentation

Complete = the stated fidelity axis is at the requested depth **across the whole
bounded subgraph**, not just the first node you touched. If you deepened
`animate_sequence` but left its three children coarse, you are not done.
