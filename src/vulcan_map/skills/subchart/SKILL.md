---
name: vulcan-subchart
description: Produce a focused chart from an existing Vulcan map — either a module's internals, or a named cross-cutting workflow that spans several modules ("give me a model of the RL workflow", "chart the plotting pipeline", "show me just the ADCS control loop"). Reuses already-mapped nodes rather than remodelling them. Requires an existing vulcan_mind/ master chart.
---

# vulcan-subchart — focused views over an existing map

You produce a readable chart for one thing a person actually asked about. There
are two shapes, and picking the right one is the first decision.

{{include _shared/NOT-DONE.md}}

## Which shape are you building?

| The request | Shape | Chart kind |
|---|---|---|
| "chart the vehicle module", "expand dynamics" | **Module detail** — one module, finer grain | `sub` |
| "model the RL workflow", "show me the aerobraking pipeline" | **Workflow view** — one behaviour, across modules | `workflow` |

A workflow almost never lives inside one module. An RL workflow plausibly touches
dynamics, GNC, simulation and analysis. If you build it as a module subchart you
will either truncate it at the module boundary or start remodelling other
modules inside it — both wrong.

## Prerequisite

A master chart must exist. If `vulcan_mind/graph/master.graph.json` is absent,
stop and tell the user to run the `vulcan-map` skill first. Do not invent a
master.

---

# Shape A — module detail (`chart_kind: sub`)

Members are the module's own symbol nodes; `expands` points each at the module
node it refines. See the granularity rules in the completion contract: every
significant symbol in the module's files already needs a node (V13e), so this
chart is mostly assembling what exists rather than creating.

---

# Shape B — cross-cutting workflow view (`chart_kind: workflow`)

## The mechanism, and why it is split this way

Deciding *what counts as "the RL workflow"* is a reading of intent. No traversal
can derive it, and pretending otherwise would produce confident nonsense. But
deciding *what that workflow touches* is not a judgement call at all — it follows
from the call graph.

So the work splits:

- **You choose the seeds.** The entry points where the workflow begins. This is
  the semantic step, it is yours, and it gets written into the chart file where a
  human can read and correct it.
- **The compiler computes membership.** From the seeds it walks the traced call
  edges and generates `member_nodes`. You never type that list. It is regenerated
  on every compile, so the view cannot drift away from the code it describes.

This is the same pattern as sockets and the Connections block: a human-authored
input, a generated projection, and a rule that fails if they disagree.

## Procedure

### 1. Find what is already mapped — do not start from the source

    vulcan find rl
    vulcan find policy
    vulcan find reward

`find` searches node ids, labels, tags, file paths and doc prose, and tells you
which of those matched. **Read the results before creating anything.** If a
dynamics pipeline is already mapped with real depth, the RL view must reference
those nodes, not build a second, shallower model of dynamics inside itself.

Creating a duplicate node for a symbol another chart already owns is rejected by
rule V19. The map must not disagree with itself about what a symbol is.

### 2. Choose and justify the seeds

Pick the entry points — usually the top-level functions a person would name if
asked "where does this workflow start?". State them back to the user with your
reasoning before creating the chart:

    workflow "rl": seeds
      gnc.rl_train_policy    — the training entry point
      gnc.rl_rollout         — the rollout loop the trainer drives
    traversal: both, depth 4
    → reaches 31 nodes across gnc, dynamics, simulation, analysis. Proceed?

Seeds must already be mapped nodes. If the workflow's entry point is not on the
map yet, map it first with `vulcan-map` — a workflow view borrows nodes, it does
not invent them.

### 3. Create it

    vulcan workflow add rl \
      --title "Reinforcement-learning training workflow" \
      --seed gnc.rl_train_policy \
      --seed gnc.rl_rollout \
      --why "training entry point and the rollout loop it drives" \
      --direction both --depth 4

`--direction downstream` follows what the seeds call; `upstream` follows what
calls them; `both` gives the whole neighbourhood. `--depth` bounds the reach —
raise it if the view stops short of the real terminus, lower it if it swallows
half the repo.

### 4. Compile and read the result

    vulcan compile

Membership is generated here. Then open it and check it against your
understanding of the workflow:

- **Too small?** The call edges may not be traced yet, or the direction is wrong.
- **Too large?** Reduce `--depth`, or use narrower seeds.
- **Missing a real step?** That step may genuinely not be mapped. Map it with
  `vulcan-map`, then recompile — the workflow picks it up automatically, because
  membership is computed rather than fixed.

### 5. Only now, create nodes — and only for genuine gaps

If part of the workflow is real but nothing on the map covers it, add it as a
`local_node` on the workflow chart with full grounding and a real doc, exactly as
in the master skill. That node then belongs to this chart and is borrowed by any
other view that reaches it.

Never add a local node for a symbol that already has one elsewhere. Borrow it.

## Completeness

For a **module detail** chart: every significant symbol in the module's files has
a node, and the traced call edges between them are present.

For a **workflow view**: the traced closure covers the behaviour end to end, from
the seeds to its terminal effects. If it stops at a boundary, either follow it by
raising the depth, or terminate deliberately at a `kind: external` stub and say
so. Every dangling thread is followed or explicitly marked — there is no third
option.

`vulcan check --strict --proof` must pass before you report either as done.
