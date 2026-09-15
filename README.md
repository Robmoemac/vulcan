# vulcan_map

Agent-driven codebase mapping. Three parts:

| Part | What it is |
|---|---|
| **skills** | Markdown instruction docs an AI coding agent reads and follows — no LLM API, the agent is the runtime |
| **UI** | A PySide6 desktop node-graph editor: nodes, sockets, noodles |
| **vulcan_mind** | The knowledge base: one linked markdown design/ICD doc per node, plus canonical JSON topology |

Design and rationale: [PLAN.md](PLAN.md). Decisions D1–D9 there are locked.

---

## The core idea

Agents stop early because *"done" is a judgement they make about their own work*.
So vulcan removes the judgement:

> **Done is `vulcan check --strict` exiting 0.** Nothing else.

Everything the spec asks for is reformulated as a machine-checkable rule:

- **Grounding (V6)** — every node names a real file and symbol; the validator
  *opens the file and confirms the symbol occurs in it*. Invented names fail.
- **Evidence (V7)** — every edge cites a real file where the connection is
  observable. "These are probably connected" is unwriteable.
- **Anti-vagueness (V12)** — node prose is linted against a banned-phrase list
  ("a helper function", "various", …) with a word floor that generated tables
  cannot pad.
- **Coverage (V13/V13a/V13b)** — every in-scope file must be accounted for, no
  node may claim files outside its module root, and every module node needs a
  function-level subchart. A 70%-done map fails, and prints what is missing.

---

## Install

Conda only — no pip (D1). If your conda has the Anaconda ToS gate, `--override-channels`
avoids it entirely:

```bash
conda create -n vulcan --override-channels -c conda-forge -y python=3.12 pyyaml jsonschema networkx pyside6 matplotlib-base markdown-it-py pytest
```

Then make `vulcan` available from bash, PowerShell, and cmd:

```bash
python -m vulcan_map.cli install-shim --path
```

On Windows this writes `vulcan.cmd` (callable from **both** cmd and PowerShell)
plus `vulcan.ps1`; on POSIX a shell script in `~/.local/bin`. The shim invokes the
env's interpreter directly, so `vulcan` works with no env activated. `--path` is
required to modify PATH — it is never changed without asking.

Verify with `vulcan doctor`.

---

## Use

```bash
cd /path/to/your/repo     # vulcan scopes to the repo you are standing in
vulcan init               # creates vulcan_mind/, installs skill docs
```

Then point a coding agent at the `vulcan-map` skill. It will scope the region,
build a worklist, and map batch by batch until `vulcan check --strict` passes.

```bash
vulcan                    # open the UI, scoped to cwd
vulcan check --strict     # the completion gate
vulcan worklist --next 8  # next files to map
vulcan region show sim    # what a region actually covers
vulcan export             # one HTML file anyone can open — no install, view-only
```

### Sharing a map

`vulcan export` writes a single self-contained HTML file (default:
`vulcan_mind/_build/export/<project>.html`). Send it to anyone; it opens in any
browser with no network and nothing installed. It has the same read path as the
app — chart list, node sheets with sockets and noodles, the design document for
every node, double-click drill-in, search, and shareable deep links
(`#chart=…&node=…`). It is a **view-only snapshot**: it carries the repo commit
and the gate verdict at export time, and it has no way to edit the map.

### Scoping by region

Natural language ("only map sim code, ignore RL and GNC") is never acted on
directly — the skill translates it into explicit globs, writes them to
`vulcan_mind/vulcan.config.yaml`, and shows you before mapping. Rule V11 then
enforces it.

```bash
vulcan region add sim --include "src/simulation/**" --exclude "src/gnc/**"
vulcan check --region sim
```

Excluded code is not silently truncated: calls into it become `external` boundary
nodes.

---

## How it fits together

```
vulcan_mind/pending.json   ──┐   (queued UI edits)
vulcan_mind/graph/*.json   ──┤
vulcan_mind/nodes/**/*.md  ──┤
                             ├─► vulcan compile ─► _build/*.resolved.json ─► UI renders
                             │                                                    │
                             └──────── UI appends an intent to the queue ◄────────┘
```

Markdown owns *what a thing is* (prose, maths, ICD, socket declarations). JSON
owns *how things connect and lay out*. Sockets are lifted md→json; the ICD table
and Connections wikilinks are regenerated json→md inside marker fences, so author
prose is byte-preserved.

**`compile` is the only writer of chart files.** The UI has no independent graph
state and no write access to canonical JSON. Dragging a noodle appends an intent
to `pending.json`; compile folds the queue in and clears it, and the edge appears
because the resolved graph now contains it. So a hand-drawn edge and an
agent-written one reach disk by the same deterministic path — one authority, one
place to test.

An unbacked connection is therefore unrepresentable, not merely invalid. Hand-drawn
edges are held to the same grounding standard as agent ones: the UI asks for the
evidence file and rejects a path that does not exist, and V7 checks again at
validation time.

Node positions are the deliberate exception and are written directly — they are
layout the compiler preserves rather than derives, and a drag would otherwise queue
an intent per mouse-move.

---

## Agent adapters

`vulcan init` installs the skills for Claude Code, Codex, Devin, and generic
`AGENTS.md` (D7). Three of the four converge on `AGENTS.md`, so that is one
well-tested path rather than four. Includes are resolved at install time, so
emitted skill files are self-contained.

---

## This repo maps itself

`vulcan_mind/` here is a real, passing map of vulcan's own grounding subsystem —
7 nodes over 5 files, region `grounding`. Open it:

```bash
vulcan
```

The `all` region is defined but not yet mapped, so `vulcan check --region all`
fails by design: that is V13 telling the truth about what is finished.

---

## Development

```bash
python -m pytest tests -q
```

97 tests. Every validator rule has a test proving it fires — a rule that cannot
fail is not a gate. Compile idempotence is a tested invariant, because a compile
that churned the tree would put spurious diffs in every agent run, and the
UI-draw path is tested end to end: draw, compile, then replay the identical
gesture from a clean state and compare the trees byte for byte.
