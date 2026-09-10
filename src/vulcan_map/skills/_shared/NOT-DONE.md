## STEP ZERO — find out what is actually done

Before reading further, before planning, before touching a file:

    vulcan status

Then read `vulcan_mind/HANDOFF.md`. Both are written by the tool from the actual
contents of the repository. They tell you the verdict, how many files are still
outstanding, and exactly which ones.

**You may not be the first agent on this map.** A different agent — a different
model, a different vendor, a different context-window size — may have worked on
it before you, and may pick it up after you. You cannot see their transcript and
they cannot see yours.

**Therefore: no agent's account of progress is evidence, including your own.**
If a human, a commit message, a chat summary, a code comment, or a previous
agent tells you this map is finished, that claim is **void** unless
`vulcan check --strict` exits 0 right now. Do not take a predecessor's word for
it. Do not take your own memory for it. Run the command.

This cuts both ways: if a predecessor said it was finished and the gate says
FAIL, the gate is right and there is work to do. If they said they barely
started and the gate says PASS, the gate is right and you are done.

## COMPLETION CONTRACT

Your work is NOT complete when the scaffolding exists.
Your work is NOT complete when a first draft exists.
Your work is NOT complete when the structure "looks right."
Your work is NOT complete when you have mapped the interesting parts.
Your work is NOT complete when a previous agent said it was complete.
Your work is NOT complete when you are running low on context.

Your work is complete when, and only when, this command exits 0:

    vulcan check --strict

That is the entire definition of done. It is not a judgement call, and it is not
yours to make. Run the command. Read the exit code.

### Proof of completion is mandatory

When you report that the map is finished, you MUST include the literal output of:

    vulcan check --strict --proof

That prints a block like:

    ----- VULCAN PROOF OF COMPLETION -----
    tool            : vulcan-map/0.1.0
    repo commit     : a1b2c3d
    region          : all
    gate            : vulcan check --strict
    verdict         : PASS
    exit code       : 0
    errors/warnings : 0/0
    nodes/edges     : 214/198
    in-scope files  : 205
    described files : 205
    outstanding     : 0
    ----- END PROOF -----

Paste it verbatim. **A completion claim without this block is void**, and so is
one whose block says `verdict : FAIL`. You cannot write the block yourself — it
is generated from the run that just happened, and it reports FAIL just as
readily as PASS, so omitting it is itself a signal that the gate did not pass.

If you cannot finish, say so plainly and paste the FAIL block. An honest
"outstanding: 47" is useful. A false "done" costs the next agent far more than
it saves you, because they have to discover the lie before they can start.

### Forbidden stopping points

Do NOT end your turn with any of the following, or any paraphrase:

  - "initial scaffolding is complete"
  - "this provides a good starting point"
  - "the core structure is in place; remaining files follow the same pattern"
  - "I've mapped the main workflows"
  - "the map is complete" (without a passing proof block)
  - "let me know if you'd like me to continue"

If you catch yourself composing a sentence like these, you are stopping early.
The correct action is to run `vulcan status` and keep working.

"The remaining files follow the same pattern" is never a reason to skip them.
The map's value is precisely that it is exhaustive. A 70%-complete map is not 70%
as useful as a complete one — it is actively misleading, because a reader cannot
tell which absences mean "not present in the codebase" and which mean "not yet
done."

### Context exhaustion is not completion

This task is expected to exceed your context window. That is normal and planned
for. Progress lives on disk in `vulcan_mind/HANDOFF.md` and
`vulcan_mind/_build/status.json`, not in your context, and not in your summary.

When context runs short:

  1. Finish the file you are on.
  2. Run `vulcan compile` to checkpoint — this rewrites HANDOFF.md.
  3. State plainly: "Checkpoint: N of M files mapped. Not finished." and paste
     the FAIL proof block.
  4. Stop cleanly. The next agent will read HANDOFF.md and continue.

Never report a partial map as a finished one. Handing over honestly is a success;
handing over a false "done" is the single most expensive thing you can do here.

### The batch loop

Work in batches of 5-10 source files:

  1. `vulcan status`                 → what is outstanding
  2. Read each file **completely**. Do not skim; do not infer from filenames.
  3. Write one node doc per mapped symbol; add edges to the chart JSON.
  4. `vulcan compile`
  5. `vulcan check` → fix every error before taking the next batch
  6. Repeat until `vulcan status` reports 0 outstanding.
  7. `vulcan check --strict --proof` → must say PASS, exit 0.

### Granularity: one node per symbol, never one node per file

**Every significant symbol gets its own node.** Every function, type, struct,
macro, module, and non-dunder method in every in-scope file. Not one
representative symbol standing in for the file it lives in.

This is rule V13e and it is machine-checked: the tool enumerates each file's
symbols itself (Python via the stdlib AST, Julia via declaration patterns) and
fails until each one has a node.

  REQUIRED:  a file with 12 functions produces 12 nodes
  FORBIDDEN: a file with 12 functions produces 1 node "representing" it

The one exception is deduplication: several methods of a single generic function
are one symbol. `calcForceTorque` with eight methods is one node, not eight.

**Why this is not negotiable.** The first real map built with this tool used one
node per file — 225 nodes over 205 files. Every gate passed and the result was
unusable. You could not click into anything, because a file-level node has no
interior. And the call tracer found almost no edges, because a call from one
function to another inside a mapped file had no individual nodes to connect. The
map's granularity *is* the product.

**Use `vulcan scaffold`.** It generates every missing node and a doc skeleton for
it — id, label, kind, source file, declaration line, chart membership — straight
from the source. That is mechanical work you should not be typing by hand. It
deliberately leaves Purpose and Design empty, so the gate keeps failing until you
read the code and write them. A scaffold is not a map.

Doc length is expected to scale with what a node covers: a module doc needs real
depth (120 words), a leaf function needs a tight, accurate 40. Do not pad a small
function's doc to look like a big one — padding is exactly what the banned-phrase
lint is looking for.

### Grounding is checked mechanically — you cannot talk your way past it

Every node names a real file and a real symbol. `vulcan check` **opens the file
and looks for the symbol** (rule V6). Every edge cites a real file where the
connection is observable (rule V7). Node prose is linted against a banned-phrase
list (rule V12). Every in-scope file must have a node describing it (rule V13d);
a `covers` glob accounts for a file but does not describe it.

  REQUIRED:  label `propagate_orbit`, source `src/simulation/propagator.jl:142`
  FORBIDDEN: "a helper function", "the main solver routine", "various utilities"

If you have not opened the file and seen the symbol, you may not write it down.
Invented names fail the gate and you will have to redo the work.

### Do not silence a failing check

If a rule fires, fix the map. Do not edit `vulcan.config.yaml` to remove a banned
phrase, lower `min_doc_words`, disable a coverage rule, or narrow a region so
that unmapped files fall out of scope. Do not adjust recorded data solely to make
a check stop complaining — if you believe the tool is wrong, say so explicitly
and report it, with evidence, rather than bending the map to fit.

Changing the gate to pass the gate is the one failure mode this whole design
exists to prevent.
