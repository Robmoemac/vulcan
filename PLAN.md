# vulcan_map — Architecture & Design Plan

**Status:** design only. No implementation is authorized by this document.
**Target:** a portable, agent-driven codebase-mapping tool installable into any repository.
**Date:** 2026-09-08

---

## 0. What this document is

A design spec for turning `vulcan_map` into a three-part tool:

| Part | Name | What it is |
|---|---|---|
| (a) | **skills** | Markdown instruction docs an AI coding agent reads and follows |
| (b) | **UI** | A Python desktop node-graph editor (nodes / sockets / noodles) |
| (c) | **vulcan_mind** | The backend: Obsidian-style linked markdown + canonical JSON |

Sections 1–2 establish principles and flag every place the spec admits more than one
reading. Everything after depends on those choices, so read them first.

---

## 1. Design principles

These are load-bearing. Each later decision traces back to one of them.

### P1 — Completion must be machine-checkable, not self-assessed

The spec asks that the skill "not stop until fully done." Emphatic prose alone does not
fix this; agents stop early because *"done" is a judgement call they are making about
their own work*. The fix is to remove the judgement:

> **Done is defined as: `vulcan check --strict` exits 0.**

The skill docs still contain strong anti-stopping language (§9), because it demonstrably
helps at the margin. But the load-bearing mechanism is an external, deterministic gate
the agent cannot rationalise its way past. Every "vagueness" and "coverage" requirement
in the spec is therefore reformulated as a validator rule in §8.

### P2 — Grounding is enforced mechanically, not requested politely

"No vague descriptions of 'a helper function'" becomes two validator rules:

- every node declares `source.file` + `source.symbol`; the validator **opens the file and
  confirms the symbol occurs in it** (V6);
- node prose is linted against a configurable banned-phrase list (V12).

An agent that hallucinates a function name fails the gate. This is the single most
important anti-hallucination device in the design.

### P3 — The UI cannot represent an edge that isn't in the JSON

The bidirectional invariant is architectural, not a post-hoc check. Data flows in exactly
one direction, and **the compiler is the only writer of canonical chart files**:

```
   pending.json (queued UI intents)
        │
        ▼
canonical JSON ──► compiler ──► _build/<chart>.resolved.json ──► UI renders
      ▲                                                              │
      └──────── UI appends an intent to the queue ◄──────────────────┘
```

The UI has **no independent graph-construction logic and no write access to chart
files**. It renders `resolved.json` and nothing else. A user dragging a noodle appends
an *intent* to `vulcan_mind/pending.json`; the compiler folds that queue into canonical
JSON, and the new edge appears only after the round trip. It is therefore *impossible*
by construction for the UI to display an unbacked connection, and equally impossible for
it to persist one by a path the compiler did not take.

Routing hand edits through the queue rather than letting the UI write directly means a
human-drawn edge and an agent-written one reach disk by the same deterministic code
path. There is one authority on what a chart file contains, so there is one place where
that behaviour can drift — and one place to test it.

The queue is authored input, not generated output, so it lives beside the charts rather
than under `_build/` and survives anything that clears the build directory. It carries no
timestamps or wall-clock ordering, and folding is idempotent: edge identity is derived
from endpoints, so re-folding an applied intent is a no-op rather than a duplicate.

The validator (V3/V4/V15) remains a second line of defence against hand-edited files.

### P4 — Long runs must survive context exhaustion

Mapping a large repo will exceed any agent's context window. The design assumes this and
externalises progress into `_build/worklist.json` — a durable per-file ledger the agent
re-reads after every batch. Running out of context becomes a *resumable interruption*
rather than a silent early stop.

### P5 — The tool ships no LLM client

"NO APIs" is read as: `vulcan_map` never calls an external model. The agent is the
runtime; `vulcan_map` provides instructions, storage, validation, and visualisation. This
also rules out embedding-based similarity search — all retrieval is grep/AST/glob.

---

## 2. Ambiguities in the spec, and the interpretation I am planning around

Flagged rather than silently resolved, per the brief. Each has my chosen reading and the
reason. **All of these are now resolved** — each carries a ✅ and a pointer to its decision
row in §14.1. The prose below preserves the reasoning, including alternatives considered and
rejected, so the *why* survives even though the *what* is settled.

### A1 — "DAG" vs. the fact that real call graphs contain cycles ✅ D5

Recursion and mutually-recursive modules are cycles. A strict DAG cannot represent them.

**Chosen:** edges carry `kind`. Edges of `kind: "feedback"` are excluded from the
acyclicity check (V5) and rendered as dashed noodles. The graph is a DAG *over
non-feedback edges*, which preserves layered layout while keeping the map truthful.
Rejected: silently dropping back-edges (produces a map that lies), and allowing general
cycles (breaks layered layout and the mental model the spec asks for).

### A2 — What is a node? ✅ D3

Function, file, module, and subsystem are all plausible granularities.

**Chosen:** **function-level by default**, with `kind ∈ {function, file, module, struct,
external, group}` so coarser nodes are expressible, and a per-region
`granularity` setting. Rationale: the spec demands explicit real function names, which
implies function-level; but a 3,000-function repo produces an unreadable master chart,
so the master chart defaults to `module`/`file` granularity and subcharts drill to
`function`. See A9.

### A3 — Canonical source of truth: JSON or markdown?

The spec says "one canonical source gets compiled into the other (or both from a shared
source)" — explicitly leaving this open.

**Chosen: split ownership by concern**, declared in an explicit ownership table (§7.1):

- **topology** (which nodes exist, which edges connect them, layout) — canonical in JSON;
- **semantics** (prose, math, ICD descriptions, socket declarations) — canonical in markdown.

Rationale: the UI must *write* topology (dragging noodles), and rewriting YAML frontmatter
across 200 files on every drag is fragile. Conversely the agent authors prose one file at
a time, and a single monolithic JSON holding all prose would be a merge-conflict magnet
and would defeat the "Obsidian-style linked markdown" requirement. Sockets are the seam:
they are ICD content (so authored in frontmatter) but referenced by edges (so needed in
JSON), and are therefore **lifted md → json** by the compiler and never hand-written in JSON.

Rejected: single-file-canonical in either direction, for the reasons above.

### A4 — Do `[[wikilinks]]` in the markdown count as edges?

"Obsidian-style linked markdowns" implies wikilinks; the spec separately says every edge
lives in JSON. If both were authoritative they could disagree — a third drift surface.

**Chosen:** wikilinks are **derived, never authoritative**. The compiler regenerates a
fenced `## Connections` block in each node doc from the JSON, so the Obsidian graph view
always mirrors the real graph. Wikilinks the author writes in *prose* are permitted and
are not edges; if a prose wikilink targets a node with no corresponding edge, the
validator emits a **warning** (V16) because that usually means a missing edge.

### A5 — Is `vulcan_mind/` committed to the target repo? ✅ D4

**Chosen: yes, committed** (with `vulcan_mind/_build/` gitignored). The map is
documentation with standalone review value, it needs to diff in PRs, and "installable into
any new repository" reads as *becoming part of* that repo. Flagged because a team that
regards it as regenerable cache would want the opposite.

### A6 — "Only conda" — does that forbid `pip install` inside the conda env? ✅ DECIDED

**Resolved by the owner, 2026-09-08: strict conda-only. No pip fallback.** Every
dependency must resolve from conda channels. This is no longer an open question.

Consequence, verified rather than assumed: `NodeGraphQt` — the most obvious off-the-shelf
node editor — **is not on conda-forge** (`conda search -c conda-forge nodegraphqt` returns
no match), while `pyside6` **is** (6.11.2). The strict constraint therefore rules
NodeGraphQt out as a dependency.

**Locked design:** the node editor is built on **PySide6 + a custom `QGraphicsView`/
`QGraphicsScene` implementation** (§11.1). Vendoring NodeGraphQt's source was considered
and **rejected** — see §11.1. This decision is final for v1 and downstream sections should
be read as settled, not provisional.

### A7 — "Install conda if not present"

**Chosen:** never silently. `vulcan doctor` detects absence, prints the exact Miniconda
installer command for the platform, and requires explicit confirmation. Installing a
package manager system-wide without consent is not an acceptable default.

### A8 — Subchart: filtered view of the master, or an independent graph? ✅ D9

**Chosen: a view over the master node set.** A subchart references master nodes by ID,
may add *finer* local nodes (via `expands`), and stores its own layout. The compiler
resolves master + subchart into one `resolved.json`. Rationale: independent graphs
inevitably drift from the master and from each other, and the spec's whole premise is a
single coherent map. Cost: a subchart cannot contradict the master — which I consider a
feature.

### A9 — Master chart readability at scale

"Everything, all functionality and flows together" is unreadable at function granularity
for a large repo.

**Chosen:** master defaults to `module`/`file` granularity with `group` nodes; every master
node links to the subchart(s) that expand it. Function-level detail lives in subcharts.
The `--granularity function` flag overrides for small repos.

### A10 — "Augment" semantics: mutate in place or version?

**Chosen:** mutate in place. Git is the version history; a bespoke versioning scheme would
duplicate it badly. Augmentation is additive by default and requires `--allow-removal` to
delete existing nodes/edges.

### A11 — Multi-language / polyglot repos

**Chosen:** pluggable "grounders" keyed by file extension. v1 ships a regex grounder
(sufficient for the symbol-existence check of V6) plus a Julia-aware and Python-aware
grounder. Full AST parsing (tree-sitter) is deferred.

Now that A6 is decided as strict conda-only, this hardens into a constraint rather than a
note: **any future grounder may only use parsers installable from conda channels.** Python
gets AST grounding free via the stdlib `ast` module. Julia has no conda-installable Python
parser I would rely on, so the Julia grounder stays regex-based over `function` / `struct` /
`macro` / `const` declaration forms — adequate for V6, which asks only whether a symbol
occurs in a file, not for a full parse tree. Verify conda-forge availability before
adopting any parser dependency.

### A12 — Conflict between UI edits and agent regeneration ✅ D6

If a human repositions nodes and adds an edge, then the agent re-runs, whose version wins?

**Chosen:** every node/edge carries `origin ∈ {agent, human}`. Agent runs must preserve
`ui.pos` and must not delete `origin: human` elements without `--allow-removal`. Human
edits are sticky.

---

## 3. Layout: the `vulcan_map` tool repository

This is what lives at `github.com/Robmoemac/vulcan`.

```
vulcan_map/
  README.md
  PLAN.md                         # this document
  LICENSE
  pyproject.toml                  # console_scripts entry point → vulcan
  environment.yml                 # conda env definition (the only dep manifest)
  schemas/
    graph.schema.json             # JSON Schema for chart files
    config.schema.json            # JSON Schema for vulcan.config.yaml
    node-frontmatter.schema.json
  src/vulcan_map/
    __init__.py
    cli/
      __main__.py                 # arg parsing, subcommand dispatch
      cmd_init.py  cmd_compile.py  cmd_check.py  cmd_ui.py
      cmd_worklist.py  cmd_region.py  cmd_doctor.py  cmd_install_shim.py
    core/
      config.py                   # load/validate vulcan.config.yaml, region resolution
      model.py                    # dataclasses: Chart, Node, Edge, Socket
      frontmatter.py              # YAML frontmatter read/write, block-marker rewriting
      pending.py                  # queued UI edits + the deterministic fold (§11.3)
      mutations.py                # UI edit intents; enqueue, never write (§11.3)
      compile.py                  # the compile pipeline (§7.2)
      validate.py                 # rules V1–V16 (§8)
      grounding/                  # symbol-existence checkers
        base.py  regex.py  julia.py  python.py
      layout.py                   # deterministic layered DAG layout
      worklist.py                 # durable progress ledger (P4)
      resolve.py                  # master + subchart → resolved.json
    ui/
      app.py                      # QApplication bootstrap, window shell
      sidebar.py                  # chart list (master + subcharts)
      graph_scene.py              # QGraphicsScene, hit-testing, rubber-band
      graph_view.py               # QGraphicsView, pan/zoom
      items/
        node_item.py  socket_item.py  edge_item.py  group_item.py
      doc_panel.py                # renders the selected node's markdown
      mathtext.py                 # LaTeX → QPixmap via matplotlib mathtext
      commands.py                 # QUndoCommand set; every mutation writes canonical JSON
    skills/
      master/SKILL.md
      subchart/SKILL.md
      augment/SKILL.md
      adapters/                   # per-agent install shims (§9.4)
        claude_code.py  agents_md.py  codex.py  devin.py
    templates/
      node.md.j2
      vulcan.config.yaml.j2
  tests/
    test_compile_roundtrip.py
    test_validator_rules.py
    test_resolve_subchart.py
    fixtures/
```

---

## 4. Layout: `vulcan_mind` inside a target repository

What `vulcan init` deposits. Example shown for this repo (SpaceAGORA.jl).

```
<target-repo>/
  vulcan_mind/
    vulcan.config.yaml            # regions, granularity, lint config — committed
    pending.json                   # queued UI edits awaiting compile; absent when empty
    graph/
      master.graph.json           # canonical topology, master chart
      subcharts/
        plotting.graph.json
        adcs-control.graph.json
    nodes/                        # one markdown per node, mirrors source tree
      simulation/
        propagate_orbit.md
        integrate_step.md
      io/
        write_telemetry.md
    _build/                       # generated — gitignored
      master.resolved.json        # what the UI actually renders
      plotting.resolved.json
      index.json                  # denormalised lookup for UI startup speed
      worklist.json               # durable progress ledger (P4)
      validation-report.json
    .gitignore                    # contains: _build/
  .claude/skills/vulcan-map/SKILL.md          # agent entry points, per adapter
  .claude/skills/vulcan-subchart/SKILL.md
  .claude/skills/vulcan-augment/SKILL.md
  AGENTS.md                                    # appended section — serves Codex, Devin,
                                               # and any other AGENTS.md-aware agent
```

`nodes/` mirrors the source tree so a node's doc is findable by path intuition, and so
Obsidian's folder view is meaningful when the vault root is set to `vulcan_mind/`.

---

## 5. Configuration and regions

Regions are the scoping mechanism ("only map sim code, ignore RL and GNC"). The spec asks
how they are specified. **All three input routes exist, but the config file is the only
authority** — CLI flags select a region, and natural language is *compiled into* the config
rather than interpreted ad hoc. That gives auditability (you can read what got excluded)
and makes exclusions enforceable by a validator rule (V11).

### 5.1 `vulcan_mind/vulcan.config.yaml`

```yaml
version: 1
project: SpaceAGORA.jl
languages: [julia]

default_region: all

regions:
  all:
    description: "Entire source tree."
    include: ["src/**", "ext/**"]
    exclude: ["**/test/**", "**/*_test.jl", "deps/**"]
    granularity: module

  sim:
    description: "Simulation core only: propagation, dynamics, environment."
    include:
      - "src/simulation/**"
      - "src/dynamics/**"
      - "src/environment/**"
    exclude:
      - "src/gnc/**"        # explicitly out of scope
      - "src/rl/**"         # explicitly out of scope
    granularity: function

grounding:
  require_symbol_match: true      # V6
  symbol_search: regex            # regex | julia | python

lint:
  banned_phrases:                 # V12 — the anti-vagueness list
    - "a helper function"
    - "various"
    - "and so on"
    - "etc."
    - "some kind of"
    - "handles the logic"
    - "TODO"
    - "TBD"
  min_doc_words: 120              # per node doc body, excluding generated blocks

coverage:
  require_every_in_scope_file_mapped: true    # V13
```

### 5.2 The three input routes

| Route | Form | Authority |
|---|---|---|
| Config file | `regions:` block above | **canonical** |
| CLI | `vulcan map --region sim`, or ad-hoc `--only 'src/sim/**' --ignore 'src/rl/**'` | selects/overrides for one run; `--save-region NAME` persists it |
| Natural language | "only map sim code, ignore RL and GNC" | **not** interpreted directly — the skill translates it into a `regions:` block, writes it, and echoes it back for confirmation before mapping |

The NL route is the one that needs care. The skill's procedure (§9.1, step 2) is: propose
the concrete glob block, show it, get confirmation, write it, then map. This prevents an
agent from silently deciding what "sim code" means and mapping the wrong third of the repo.

### 5.3 How exclusions are respected

Enforcement is at three layers, so an exclusion cannot leak through:

1. **Discovery** — file walking applies include/exclude globs before the agent sees anything.
2. **Validation (V11)** — any node whose `source.file` is outside the active region is an
   ERROR, so an agent that maps an excluded file fails the gate.
3. **Rendering** — resolved graphs are region-tagged; the UI shows the active region and
   greys out-of-region nodes rather than hiding them (so you can *see* the boundary).

Edges crossing the region boundary are kept and terminate in a `kind: "external"` stub node
— an excluded region is a black box with a labelled interface, not a silent truncation.

---

## 6. JSON schema — nodes and edges

### 6.1 Chart file (`graph/master.graph.json`)

```json
{
  "schema_version": "1.0.0",
  "chart_id": "master",
  "chart_kind": "master",
  "title": "SpaceAGORA.jl — Master Flow",
  "region": "all",
  "provenance": {
    "repo_commit": "e8dd610d",
    "generated_at": "2026-09-08T18:40:00Z",
    "generator": "vulcan-map/0.1.0",
    "agent": "claude-code"
  },
  "nodes": [
    {
      "id": "simulation.propagate_orbit",
      "label": "propagate_orbit",
      "kind": "function",
      "doc": "nodes/simulation/propagate_orbit.md",
      "source": {
        "file": "src/simulation/propagator.jl",
        "symbol": "propagate_orbit",
        "lines": [142, 219]
      },
      "sockets": {
        "inputs":  [{ "id": "state0", "type": "StateVector", "required": true }],
        "outputs": [{ "id": "traj",   "type": "Trajectory" }]
      },
      "expands": null,
      "ui": { "pos": [340, 120], "color": "#4C9A7A", "collapsed": false },
      "tags": ["sim", "dynamics"],
      "origin": "agent"
    }
  ],
  "edges": [
    {
      "id": "e:simulation.propagate_orbit:traj->io.write_telemetry:data",
      "from": { "node": "simulation.propagate_orbit", "socket": "traj" },
      "to":   { "node": "io.write_telemetry",         "socket": "data"  },
      "kind": "dataflow",
      "label": "Trajectory",
      "evidence": { "file": "src/simulation/runner.jl", "lines": [88, 91] },
      "origin": "agent"
    }
  ]
}
```

### 6.2 Field reference

**Node**

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string | ✔ | `^[a-z0-9_]+(\.[a-z0-9_]+)*$`, globally unique across all charts |
| `label` | string | ✔ | display name; must be the **real** symbol name |
| `kind` | enum | ✔ | `function \| file \| module \| struct \| external \| group` |
| `doc` | path | ✔ | relative to `vulcan_mind/`; must exist (V8) |
| `source.file` | path | ✔¹ | must exist on disk (V6) |
| `source.symbol` | string | ✔¹ | must occur in that file (V6) |
| `source.lines` | `[int,int]` | — | advisory; drift is a warning, not an error |
| `sockets` | object | ✔ | **generated** — lifted from markdown frontmatter, never hand-written |
| `expands` | node id \| null | — | this node is a finer decomposition of that master node (A9) |
| `covers` | `[glob]` | ✔² | files this node accounts for. Required on `module`/`group` nodes so V13 can verify coverage without a node per file (D3) |
| `ui.pos` | `[x,y]` | — | absent ⇒ computed by layout engine; preserved across agent runs (A12) |
| `origin` | enum | ✔ | `agent \| human` — governs deletion rights (A12) |

¹ not required for `kind ∈ {group, external}`.
² required for `kind ∈ {module, group}`; ignored for `function`/`struct` nodes, whose
`source.file` already establishes what they cover.

**Edge**

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | string | ✔ | **derived**: `e:<from.node>:<from.socket>-><to.node>:<to.socket>` — deterministic, so compiles are idempotent and git diffs are stable |
| `from` / `to` | `{node, socket}` | ✔ | both must resolve (V3, V4) |
| `kind` | enum | ✔ | `dataflow \| call \| mutates \| reads \| feedback` — `feedback` is exempt from acyclicity (A1) |
| `label` | string | — | shown on the noodle |
| `evidence.file` | path | ✔ | **the anti-hallucination hook** — the file where this connection is observable |
| `evidence.lines` | `[int,int]` | — | advisory |
| `origin` | enum | ✔ | as above |

Requiring `evidence` on **every** edge is deliberate: it makes "I think these are probably
connected" unwriteable. An agent must point at a line of real code.

### 6.3 Subchart file

```json
{
  "schema_version": "1.0.0",
  "chart_id": "plotting",
  "chart_kind": "sub",
  "derives_from": "master",
  "title": "Plotting & Visualisation Workflow",
  "member_nodes": ["viz.plot_trajectory", "viz.render_frame", "io.read_telemetry"],
  "local_nodes": [ /* finer nodes, each with "expands": "<master node id>" */ ],
  "local_edges": [ /* same edge schema */ ],
  "ui": { "pos_overrides": { "viz.plot_trajectory": [120, 200] } }
}
```

Resolution rule: the resolved subchart contains `member_nodes` + `local_nodes`, plus every
master edge whose endpoints are both members, plus `local_edges`. Deterministic, so the
UI's view is a pure function of canonical files (P3).

---

## 7. Canonical source of truth and the compile step

### 7.1 Ownership table

The precise answer to "what is canonical" (A3):

| Data | Owner file | Direction | Notes |
|---|---|---|---|
| Queued UI edits | `pending.json` | queue → json | authored intent; folded and cleared by compile (§11.3) |
| Node existence, `id`, `kind` | markdown frontmatter | md → json | agent creates a doc; compiler registers the node |
| Node prose, math, ICD text | markdown body | md only | never in JSON |
| **Socket declarations** | markdown frontmatter | md → json | lifted; JSON copy is a mirror |
| **Edges** | chart JSON | json only | never in markdown |
| Node positions / colour | chart JSON | json only | written by UI |
| Subchart membership | subchart JSON | json only | |
| `## Connections` block | *generated* | json → md | fenced, machine-owned region of the doc |
| Everything in `_build/` | *generated* | — | never hand-edited, gitignored |

Concisely: **markdown owns what a thing *is*; JSON owns how things *connect and lay out*.**

### 7.2 `vulcan compile` — the algorithm

Deterministic, idempotent, no network, no model calls.

```
 1. LOAD CONFIG        parse vulcan.config.yaml, validate against config.schema.json,
                       resolve the active region into concrete include/exclude globs.

 2. DISCOVER           glob vulcan_mind/graph/**.json  and  vulcan_mind/nodes/**/*.md.

 3. PARSE              JSON → dataclasses (schema-validated, V1).
                       markdown → (frontmatter dict, body, generated-block spans).
                       Parse failures are hard errors; nothing is written.

 4a. FOLD PENDING      apply queued UI edits (vulcan_mind/pending.json) to the in-memory
                       charts, in queue order. Edge identity is derived from endpoints,
                       so re-applying an already-folded intent is a no-op.
                       Runs in --check mode too, so `check` validates exactly what
                       `compile` would persist; only the write and the clear are
                       suppressed. The queue is cleared in step 10, after the charts
                       are safely on disk.

 4b. LIFT SOCKETS      for each node doc, project frontmatter inputs/outputs into the
                       chart JSON's sockets field.
                         - md declares a socket JSON lacks     → add    (silent)
                         - JSON has a socket md lacks          → ERROR V10 (never auto-delete;
                                                                 an edge may depend on it)
                         - type/required mismatch              → md wins, WARN

 5. RESOLVE            for each chart, build resolved graph (master, or master+subchart
                       per §6.3). Assign deterministic edge IDs. Dedupe.

 6. GROUND             for every node: does source.file exist? does source.symbol occur
                       in it (per the configured grounder)?  → V6
                       for every edge: does evidence.file exist? → V7
                       Filesystem reads only — no interpretation.

 7. LAYOUT             any node lacking ui.pos gets one from a deterministic layered
                       algorithm (longest-path layering over non-feedback edges, then
                       barycentre crossing reduction, fixed RNG seed). Existing positions
                       are never overwritten (A12).

 8. VALIDATE           run V1–V16 (§8), collect {errors, warnings} with file:line.

 9. REGENERATE MD      rewrite, inside marker fences only:
                         <!-- vulcan:icd:begin --> … <!-- vulcan:icd:end -->
                         <!-- vulcan:connections:begin --> … <!-- vulcan:connections:end -->
                       Author prose outside the fences is byte-preserved.

10. EMIT               write the canonical charts, then _build/*.resolved.json,
                       index.json, validation-report.json, worklist.json — atomically
                       (tmp file + os.replace). Clear pending.json last, once the
                       charts are on disk. Validation errors do not block the clear:
                       the intent now lives in canonical JSON where the findings point
                       at it, and replaying the queue would duplicate intent, not fix it.

11. EXIT               0 if no errors; 1 if any error. --strict promotes warnings to errors.
```

`vulcan check` = steps 1–8 and 11 with all writes suppressed, **plus** a step-9 dry-run
that diffs what *would* be regenerated against what is on disk — so a hand-edited
`Connections` block is caught rather than silently repaired (V15).

Idempotence is a tested invariant: `compile; compile` must produce a byte-identical tree
(`tests/test_compile_roundtrip.py`). Without it, every agent run creates spurious diffs.

---

## 8. Validator rules

Severity: **E** = error (blocks), **W** = warning (promoted to error under `--strict`).

| # | Sev | Rule |
|---|---|---|
| V1 | E | Every chart JSON validates against `graph.schema.json`; every frontmatter against `node-frontmatter.schema.json` |
| V2 | E | Node IDs unique across all charts and match the ID pattern |
| V3 | E | Every edge endpoint references an existing node — *no JSON connection that can't be rendered* |
| V4 | E | Every edge endpoint references a socket that exists on that node |
| V5 | E | The graph is acyclic over non-`feedback` edges (A1) |
| V6 | E | **Grounding:** `source.file` exists and `source.symbol` occurs in it |
| V7 | E | Every edge has `evidence.file` and that file exists |
| V8 | E | Every node's `doc` path exists |
| V9 | E | Every node doc under `nodes/` is registered in some chart (no orphan docs) |
| V10 | E | Socket parity between frontmatter and chart JSON |
| V11 | E | No node's `source.file` falls outside the active region's globs (§5.3) |
| V12 | E | **Anti-vagueness:** no banned phrase in doc prose; body ≥ `min_doc_words` |
| V13 | E¹ | **Coverage:** every in-region source file is *accounted for* — either it is some node's `source.file`, or it matches the `covers` globs of a `module`/`group` node (D3) |
| V14 | W | No isolated nodes (degree 0) unless `kind: group` |
| V15 | E | Generated blocks on disk match what the compiler would emit (drift detection) |
| V16 | W | A prose wikilink to another node with no corresponding edge (A4) |
| V17 | W | `source.lines` no longer bracket the symbol (map is stale vs. current code) |

¹ E when `coverage.require_every_in_scope_file_mapped: true` (the default), else W.

V13 is the rule that makes "don't stop early" enforceable: an agent that maps 40 of 300
files fails, with the exact remaining list printed.

**V13 under D3 (module-level master).** Because the master chart is module-level, requiring
one node per file would contradict D3. Coverage is instead satisfied by *accounting*: a
`module`/`group` node declares `covers: ["src/simulation/**"]`, and every in-region file
matching it is accounted for. The rule still cannot be trivially satisfied — a bare
`covers: ["src/**"]` on a single node would pass V13 but fail V14 (isolated node), V12
(`min_doc_words` on a doc that would have to describe the whole tree), and the subchart
obligations below. Two additional constraints close the loophole:

- **V13a (E)** — a `covers` glob may not match files outside the node's own module root
  (no node may claim the entire tree);
- **V13b (E)** — every `module` node must be expanded by at least one subchart reaching
  function granularity before the map is considered complete for that module.

Function-level completeness is therefore a per-subchart obligation, exactly as D3 states,
and "the master is done" never means "the map is done."

### 8.1 Where validation runs — and where it does not

**Decided 2026-09-08: `vulcan check` runs at map-authoring time only. It is never a CI
merge gate.**

| Context | Runs? | Notes |
|---|---|---|
| Agent batch loop, after every batch | ✔ | `vulcan check` — fix errors before the next batch (§9.0) |
| Agent completion gate | ✔ | `vulcan check --strict` must exit 0; this *is* the definition of done (P1) |
| UI, on every mutation | ✔ | round-trips through the compiler; status bar shows pass/fail (§11.3) |
| Developer, on demand | ✔ | `vulcan check` any time |
| **CI / merge gate** | **✘** | **not installed, by decision** |
| **Pre-commit hook** | **✘** | same rationale |

Rationale: the map is documentation, and blocking unrelated PRs on documentation drift
makes the tool something people route around. V17 (staleness) still *reports* drift
whenever anyone runs `check`, and the augment skill exists precisely to repair it — but
repair is a deliberate act, not a merge blocker. Validation is concentrated where the map
is being written, which is where errors are cheap to fix and the author has full context.

Consequence to accept honestly: **maps can go stale without anything failing.** That is the
chosen trade. Adopters who disagree can wire `vulcan check` into CI themselves — nothing
prevents it — but `vulcan init` will not do it for them.

---

## 9. The skill documents

Three skills, as specified. Real drafts follow. They share a common preamble
(`_shared/NOT-DONE.md`) that carries the anti-stopping contract, included by all three.

### 9.0 Shared preamble — the completion contract

```markdown
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
tell which absences are "not present in the codebase" and which are "not yet done."

### Context exhaustion is not completion

This task is expected to exceed your context window. That is normal and planned for.
Progress is stored on disk in `vulcan_mind/_build/worklist.json`, not in your context.

When context runs short:
  1. Finish the file you are on.
  2. Run `vulcan compile` to checkpoint.
  3. State plainly: "Checkpoint: N of M files mapped. Resuming from worklist."
  4. Continue. Do not summarise and stop.

Never report a partial map as a finished one.

### The batch loop

Work in batches of 5–10 source files:
  1. `vulcan worklist --next 8`      → the next files to map
  2. Read each file **completely**. Do not skim; do not infer from filenames.
  3. Write one node doc per mapped symbol; add edges to the chart JSON.
  4. `vulcan compile`
  5. `vulcan check` → fix every error before taking the next batch
  6. Repeat until `vulcan worklist --remaining` reports 0.
  7. `vulcan check --strict` → must exit 0.
```

### 9.1 Skill 1 — `vulcan-map` (master chart)

```markdown
---
name: vulcan-map
description: Build the complete Vulcan map of this repository — every in-scope file,
  function, and dataflow — as a master DAG plus per-node design/ICD documents. Use when
  the user asks to map, chart, or diagram a codebase, or asks "how does this repo work"
  at whole-system scale. Produces vulcan_mind/.
---

# vulcan-map — build the master map

You are producing a **complete, grounded map** of this repository: a master DAG of its
workflows, and one detailed design+ICD document per node.

{{include _shared/NOT-DONE.md}}

## Absolute grounding requirement

Every node and every edge must name **real, verbatim identifiers from this codebase**.

  REQUIRED:  node label `propagate_orbit`, source `src/simulation/propagator.jl:142`
  FORBIDDEN: "a helper function", "the main solver routine", "various utilities",
             "the orchestration layer"

If you have not opened the file and seen the symbol, you may not write it down.
Invented names are worse than omissions: `vulcan check` will fail on them (rule V6,
which opens the file and looks for the symbol), and you will have to redo the work.

Never describe what a function *probably* does. Read it and describe what it does.

## Procedure

### Step 1 — Establish scope

Run `vulcan init` if `vulcan_mind/` does not exist.

If the user gave a scope in natural language ("only map the sim code, ignore RL and
GNC"), you must **translate it into an explicit region** before mapping anything:

  1. Inspect the real directory structure — do not guess at paths.
  2. Draft a concrete region block with literal globs.
  3. Show it to the user and get confirmation:

         region "sim":
           include: src/simulation/**, src/dynamics/**, src/environment/**
           exclude: src/gnc/**, src/rl/**
         → 47 files in scope, 212 excluded. Proceed?

  4. Write it to `vulcan_mind/vulcan.config.yaml` under `regions:`.
  5. Run with `vulcan map --region sim`.

Never map from an unwritten interpretation of scope. The config file is the record of
what you were asked to do, and rule V11 enforces it.

Excluded regions are not deleted from the map — where in-scope code calls into excluded
code, create an `external` stub node so the boundary is visible.

### Step 2 — Build the worklist

    vulcan worklist --build --region <name>

This enumerates every in-scope file. It is your ledger. It outlives your context.

### Step 3 — Map, batch by batch

Follow the batch loop in the completion contract. For each file:

  - Read the whole file.
  - Identify every public symbol and every significant internal one.
  - Create a node doc per the template (`vulcan_mind/templates/node.md`), filling
    **every** section. Sections are not optional; `min_doc_words` is enforced.
  - Declare real inputs/outputs in frontmatter — actual argument names and types.
  - Add edges to `graph/master.graph.json` for every connection you can *point at*:
    a call site, an argument passed, a struct field written. Each edge needs
    `evidence` naming the file and lines where it is observable.

Granularity: the master chart is `module`/`file` level by default so it stays readable.
Where a module deserves function-level detail, do not cram it into the master — note it
as a subchart candidate and record it in `_build/subchart-candidates.json`.

### Step 4 — Converge

Repeat until `vulcan worklist --remaining` is 0 **and** `vulcan check --strict` exits 0.

Fix errors; do not suppress them. If a rule seems wrong, say so explicitly and ask —
do not edit the config to silence a check.

### Step 5 — Report

Report only after `--strict` passes. State: files mapped, nodes, edges, subchart
candidates, and anything you deliberately excluded and why.
```

### 9.2 Skill 2 — `vulcan-subchart`

```markdown
---
name: vulcan-subchart
description: Produce a focused sub-flowchart isolating one workflow from an existing
  Vulcan master map — e.g. "chart the plotting workflow" or "show me just the ADCS
  control loop". Requires an existing vulcan_mind/ master chart.
---

# vulcan-subchart — isolate one workflow

You are extracting a single workflow from the master map into its own readable chart,
at finer granularity than the master carries.

{{include _shared/NOT-DONE.md}}

## Prerequisite

A master chart must exist. If `vulcan_mind/graph/master.graph.json` is absent, stop and
tell the user to run the `vulcan-map` skill first. Do not invent a master.

## Key constraint — a subchart is a VIEW, not a fork

Subcharts reference master nodes by ID. You may add finer nodes, but each must declare
`expands: <master-node-id>`. You may **not** restate a master node under a new ID, and
you may not contradict the master. If the master is wrong, fix the master.

This is what keeps the maps consistent with each other.

## Procedure

1. **Trace the workflow.** Start from the entry point the user named. Follow real
   call sites and real dataflow through the code — not the master chart alone; the
   master is coarser than what you are producing. Record the member node IDs.

2. **Decide the decomposition.** For each master node in the workflow, judge whether
   function-level detail is warranted. If yes, create local nodes with `expands` set,
   each with its own doc and real source grounding.

3. **Write `graph/subcharts/<id>.graph.json`** per the subchart schema: `member_nodes`,
   `local_nodes`, `local_edges`.

4. **Edges.** Master edges between two members are inherited automatically — do not
   copy them. Add `local_edges` only for connections the master does not carry (which
   is most of them, since you are working at finer grain). Every one needs `evidence`.

5. `vulcan compile && vulcan check --strict`.

## Completeness for a subchart

"Complete" means the traced workflow is followed **end to end** — from its entry point
to its terminal effects (file written, state mutated, value returned to caller).

A subchart that stops at "and then it calls the renderer" is not finished. Follow it
into the renderer, or terminate deliberately at an `external` stub node and say so.
Every dangling thread is either followed or explicitly marked. There is no third option.
```

### 9.3 Skill 3 — `vulcan-augment`

```markdown
---
name: vulcan-augment
description: Add fidelity to an existing Vulcan chart — deepen one area of a master or
  sub chart on request, e.g. "augment the plotting subchart with more detail on
  animations". Additive by default; never silently removes existing map content.
---

# vulcan-augment — deepen an existing chart

You are increasing the resolution of a **bounded region** of an existing chart. You are
not rebuilding it.

{{include _shared/NOT-DONE.md}}

## Procedure

### Step 1 — Bound the augmentation, explicitly

From the request ("augment the plotting subchart with additional fidelity regarding
animations"), identify and state back:

  - target chart: `plotting`
  - target subgraph: nodes reachable from `viz.animate_sequence`
  - fidelity axis: animation frame lifecycle, timing, and state
  - out of scope: static plotting path (already mapped)

Get agreement before editing. Ambiguous augmentation requests produce sprawl.

### Step 2 — Augment

Fidelity is added in four ways. Use whichever the request calls for:

  a. **Decomposition** — expand a coarse node into finer nodes (`expands` set).
  b. **Socket refinement** — split an over-general socket into the real distinct
     inputs/outputs, with real parameter names and types.
  c. **Edge refinement** — replace one vague edge with the several specific dataflows
     it was standing in for; each needs its own `evidence`.
  d. **Doc deepening** — fill in the math, assumptions, and limitations sections with
     real detail: actual equations, actual numerical tolerances, actual failure modes.

### Step 3 — Additive discipline

Augmentation is **additive by default**.

  - Never delete a node or edge with `origin: "human"` — those are the user's own edits.
  - Never reposition existing nodes; the layout engine leaves `ui.pos` alone and so do you.
  - If existing content is genuinely *wrong*, do not silently overwrite it. State what is
    wrong, why, and what you propose — then change it only with `--allow-removal`.

### Step 4 — Converge

`vulcan compile && vulcan check --strict` must exit 0. Augmentation frequently breaks
socket parity (V10) and acyclicity (V5) — a finer decomposition can expose a real cycle
you must classify as `feedback` or restructure. Fix these; do not disable the rules.

## Completeness for an augmentation

Complete = the stated fidelity axis is at the requested depth **across the whole bounded
subgraph**, not just the first node you touched. If you deepened `animate_sequence` but
left its three children coarse, you are not done.
```

### 9.4 Installing skills into a target repo

Agents look in different places. `vulcan init` writes adapter-specific copies from one
source of truth in `src/vulcan_map/skills/`.

**Baseline adapter set (decided 2026-09-08):** Claude Code, Codex, Devin, and generic
`AGENTS.md`. Cursor is explicitly **not** in the baseline — it can be added later if
someone needs it, since adapters are additive and cost nothing already shipped.

| Agent | Destination | Format |
|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` | YAML frontmatter (`name`, `description`) |
| Codex (OpenAI) | `AGENTS.md` (appended, fenced section) | plain markdown |
| Devin (Cognition) | `AGENTS.md`, plus `.devin/` notes if the run confirms it is read | plain markdown |
| Generic | `AGENTS.md` (appended, fenced section) | plain markdown |

Three of the four baseline targets converge on `AGENTS.md`, so `agents_md.py` does the real
work and `codex.py`/`devin.py` are thin wrappers that add agent-specific framing. This is
deliberate: `AGENTS.md` is the emerging cross-agent convention, so the baseline is mostly
one well-tested code path rather than four parallel ones.

**Implementation-time verification required** (not an open decision — a fact to confirm
before shipping the adapter): the exact repo-level instruction file Devin reads, and
whether it honours `AGENTS.md` directly or needs its Knowledge feature populated. Confirm
against current vendor docs at build time, the same way conda-forge availability was
confirmed for §11.1. If Devin turns out to need a different location, the adapter changes;
the skill content does not.

The `{{include}}` directive is resolved at install time — emitted files are self-contained,
since no agent runtime resolves includes.

**No CI integration is installed.** `vulcan init` writes no workflow file and no pre-commit
hook; see §14.1 and the note under §8.

---

## 10. Node document template

`src/vulcan_map/templates/node.md.j2`, copied into `vulcan_mind/templates/node.md`.
Style: **LaTeX-heavy where there is math, terse everywhere else.** No filler prose — the
`min_doc_words` floor exists to catch stubs, not to invite padding.

````markdown
---
id: simulation.propagate_orbit
label: propagate_orbit
kind: function
source:
  file: src/simulation/propagator.jl
  symbol: propagate_orbit
  lines: [142, 219]
inputs:
  - id: state0
    type: StateVector
    units: "m, m s^-1 (ECI J2000)"
    required: true
    description: Cartesian state at epoch t0.
  - id: tspan
    type: Tuple{Float64,Float64}
    units: s
    required: true
    description: Integration interval (t0, tf).
outputs:
  - id: traj
    type: Trajectory
    units: "m, m s^-1 (ECI J2000)"
    description: Sampled state history at solver output points.
tags: [sim, dynamics]
charts: [master, orbit-propagation]
origin: agent
---

# propagate_orbit

## Purpose
One or two sentences. What this unit is responsible for, in the system's terms.

## Theory & Math
The governing equations, in LaTeX. Define every symbol.

$$
\ddot{\mathbf{r}} = -\frac{\mu}{\lVert \mathbf{r} \rVert^{3}}\mathbf{r}
                    + \mathbf{a}_{J_2} + \mathbf{a}_{\mathrm{drag}}
$$

with $\mu$ the gravitational parameter, $\mathbf{r}$ the ECI position vector, and
$\mathbf{a}_{J_2}$ the oblateness perturbation.

## Model & Assumptions
Bulleted. Every assumption that would change results if violated.

## Design & Implementation
How it actually works: algorithm, solver, data structures, control flow. Reference real
identifiers and real line ranges.

## Interface (ICD)
<!-- vulcan:icd:begin -->
GENERATED — do not edit. Table built from frontmatter inputs/outputs.
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
GENERATED — do not edit. Upstream/downstream wikilinks built from chart JSON edges.
<!-- vulcan:connections:end -->

## Limitations
Known failure modes, valid ranges, numerical caveats. Be specific: state the tolerance,
the divergence condition, the regime where the model stops holding.

## Provenance
Mapped from `src/simulation/propagator.jl` @ `<commit>`.
````

Two sections are machine-owned (inside marker fences); everything else is author-owned and
byte-preserved across recompiles.

---

## 11. UI

### 11.1 Stack, and why

Constraints: Python, desktop, **strict conda-only dependencies** (A6 — decided, no pip
fallback), node-graph editor with sockets and noodles.

**Verified while writing this plan:** `pyside6` **is** on conda-forge (6.11.2);
`nodegraphqt` **is not** (`conda search -c conda-forge nodegraphqt` → no match).

**This stack is locked** as of 2026-09-08. It is not a provisional recommendation.

| Layer | Choice | conda-forge | Why |
|---|---|---|---|
| GUI toolkit | **PySide6** (Qt 6) | ✔ 6.11.2 | Official Qt binding, LGPL, mature `QGraphicsView` framework — the right substrate for a node editor. `pyqtgraph`/matplotlib canvases are wrong for interactive node editing. |
| Node canvas | **Custom, on `QGraphicsScene`/`QGraphicsView`** | n/a (our code) | **Final.** Required by A6, since NodeGraphQt is not conda-installable. `QGraphicsView` gives pan/zoom, hit-testing, item transforms, and a scene graph for free; nodes/sockets/noodles are `QGraphicsItem` subclasses. Estimated ~1,200–1,800 LOC. |
| Noodles | `QPainterPath` cubic Bézier | n/a | Standard for this UI class: horizontal-tangent cubic between socket anchors. |
| Layout | **NetworkX** + custom layered pass | ✔ | Longest-path layering + barycentre crossing reduction. Deterministic (fixed seed) so positions don't churn in git. Graphviz is a heavier, non-Python-native dependency. |
| Markdown render | **markdown-it-py** → Qt rich text | ✔ | For the doc side panel. |
| LaTeX render | **matplotlib** mathtext → `QPixmap` | ✔ | The docs are LaTeX-heavy and Qt has no math renderer. mathtext needs no TeX install — important for portability. Full TeX quality is not needed for a side panel. |
| Config / schema | **PyYAML**, **jsonschema** | ✔ | |

**Rejected alternative — vendoring NodeGraphQt.** Copying its source into
`src/vulcan_map/ui/vendor/` would arguably satisfy the letter of the conda-only rule
(vendored source is not a package-manager dependency), but it was **rejected** on
2026-09-08: it imports an unmaintained-by-us dependency's full surface area, drags in its
own Qt-binding assumptions (it targets PySide2/Qt5 idioms), and would have to be patched
rather than upgraded. A purpose-built scene we control is smaller in practice than the
subset of NodeGraphQt we would end up maintaining.

**Consequences of the locked choice** — carried into the build order (§13):

- Milestones 6–7 (UI read-only, then UI editing) are the largest in the project; budget
  accordingly. The custom editor must implement, from scratch: node items with rounded-rect
  chrome and title bars, socket hit-targets with snap tolerance, cubic-Bézier noodles with
  live drag preview, rubber-band and click selection, pan/zoom with sensible zoom-to-cursor,
  a grid background, and z-ordering so noodles render behind nodes.
- No third-party node-editor API constrains the data model, so `QGraphicsItem` subclasses
  can bind directly to the schema in §6 — sockets map 1:1 onto frontmatter-declared
  inputs/outputs with no adapter layer.
- The P3 round-trip (§11.3) is simpler to guarantee, since there is no library-owned
  internal graph state that could diverge from `resolved.json`. This was a real risk with
  NodeGraphQt, which maintains its own node/port model.
- `environment.yml` stays fully solvable from conda-forge alone, so `vulcan doctor` can
  verify the environment without special-casing pip-installed packages.

### 11.2 Window layout

Per spec: sidebar lists charts, centre pane is the viewer/editor.

```
┌──────────────┬────────────────────────────────────────┬─────────────────┐
│ CHARTS       │                                        │ NODE DOC        │
│              │        node-graph canvas               │                 │
│ ▸ master     │        (pan / zoom / select)           │ propagate_orbit │
│ ▾ subcharts  │                                        │                 │
│   plotting   │   ┌────────────┐      ┌─────────────┐  │ Purpose …       │
│   adcs-ctl   │   │propagate_  │─traj─▶│write_       │  │ Theory (LaTeX)  │
│   orbit-prop │   │orbit    ○──┘      │telemetry ○  │  │ ICD table       │
│              │   └────────────┘      └─────────────┘  │ [open in editor]│
│ ── region ── │                                        │                 │
│ [sim      ▾] │                                        │                 │
├──────────────┴────────────────────────────────────────┴─────────────────┤
│ status: 47 nodes · 91 edges · check: PASS · region: sim                 │
└─────────────────────────────────────────────────────────────────────────┘
```

- Sidebar switching is immediate: charts are pre-resolved in `_build/`, so switching is a
  scene swap, not a recompute. `index.json` is loaded once at startup.
- Selecting a node loads its markdown into the right panel; "open in editor" hands off to
  `$EDITOR` / Obsidian.
- The status bar surfaces `vulcan check` state continuously — validation is visible, not
  buried in a CLI.
- Out-of-region nodes render greyed rather than hidden (§5.3).

### 11.3 Enforcing the invariant in the UI (P3)

The scene is never mutated directly, and the UI never writes a chart file. Dragging a
noodle from socket A to socket B does *not* create an edge item. It:

1. prompts for the evidence file and rejects a path that does not exist on disk;
2. appends an `add_edge` intent to `vulcan_mind/pending.json`;
3. triggers a recompile, which folds the queue into `master.graph.json` and clears it;
4. reloads the resolved graph — and the edge item appears because that graph now
   contains it.

If the result is invalid (e.g. the new edge closes a cycle, V5), the edge is still folded
in — it is what the person asked for — and the status bar reports the failure against the
persisted map rather than silently discarding the edit.

Edge **removal** takes the same route, for the same reason: if creation were queued but
deletion written directly, "the UI never writes canonical topology" would be false, and
the guarantee is only worth as much as its exceptions.

**Node positions are the deliberate exception** and are written directly. They are
presentation state the compiler preserves rather than derives (D6), they carry no
semantics for the validator to check, and a single drag would otherwise enqueue an intent
per mouse-move event. The queue is for topology; position is layout.

This makes "a connection in the UI that isn't in the JSON" unrepresentable rather than
merely invalid, and makes "a connection in the JSON that the compiler did not put there"
equally unrepresentable.

**Evidence is checked twice, on purpose.** `enqueue_add_edge` rejects a nonexistent file
so the person drawing gets the error immediately, in the dialog. V7 checks again at
validation time, because the queue is not the only way an edge can arrive. Neither check
is redundant: the first is for feedback latency, the second is the actual gate.

---

## 12. The `vulcan` CLI

### 12.1 Surface

| Command | Effect |
|---|---|
| `vulcan` | Open the UI, scoped to the current repo (§12.3) |
| `vulcan init` | Create `vulcan_mind/`, write config, install skill docs per adapter |
| `vulcan compile` | Run the pipeline; write `_build/` and regenerate md blocks |
| `vulcan check [--strict]` | Validate without writing; **the completion gate** |
| `vulcan worklist [--build\|--next N\|--remaining]` | Durable progress ledger |
| `vulcan region <list\|add\|show>` | Inspect/modify regions |
| `vulcan doctor` | Verify conda, env, PATH shims; report what's missing |
| `vulcan install-shim` | Install the cross-shell launcher (§12.2) |

### 12.2 Cross-shell installation (bash / zsh / PowerShell / cmd)

Two layers, because the requirement is `vulcan` works *without* first activating a conda env.

**Layer 1 — the console script.** `pyproject.toml` declares:

```toml
[project.scripts]
vulcan = "vulcan_map.cli.__main__:main"
```

Installing into the conda env produces `$CONDA_PREFIX/bin/vulcan` on POSIX and
`%CONDA_PREFIX%\Scripts\vulcan.exe` on Windows. The Windows artefact is a real `.exe`
launcher, which is why **cmd and PowerShell both work natively** with no per-shell
scripting. This layer works whenever the env is active.

**Layer 2 — the global shim**, so it works with the env *inactive*. `vulcan install-shim`
writes a launcher that runs the env's interpreter directly:

- **POSIX** → `~/.local/bin/vulcan` (0755):
  ```sh
  #!/usr/bin/env sh
  exec "$CONDA_ROOT/envs/vulcan/bin/python" -m vulcan_map.cli "$@"
  ```
  Covers bash, zsh, fish — anything honouring the shebang.

- **Windows** → `%LOCALAPPDATA%\Vulcan\bin\vulcan.cmd`:
  ```bat
  @echo off
  "%CONDA_ROOT%\envs\vulcan\python.exe" -m vulcan_map.cli %*
  ```
  A `.cmd` is the correct primary choice: **it is directly callable from both cmd and
  PowerShell**, whereas a `.ps1` is not callable from cmd. A sibling `vulcan.ps1` is also
  written for PowerShell users who want tab-completion, but it is not required for the
  command to work.

- **PATH** — the shim directory is appended to the *user* PATH: `setx PATH` (or the
  `HKCU\Environment` registry value, which avoids `setx`'s 1024-char truncation) on
  Windows; a line appended to the shell profile on POSIX. **PATH modification requires
  explicit consent** — `install-shim` prints the exact change and asks first (A7 rationale).

**Why not a conda `activate.d` hook:** it only fires on env activation, which is exactly
the case we need to work around.

### 12.3 cwd scoping

`vulcan` with no arguments resolves its target repo by walking up from `os.getcwd()`:

1. nearest ancestor containing `vulcan_mind/` → use it;
2. else nearest ancestor containing `.git/` → treat as repo root, offer `vulcan init`;
3. else error with a clear message.

So `cd ~/falcon/SpaceAGORA.jl && vulcan` maps SpaceAGORA.jl. `--repo PATH` overrides;
`--here` forces literal cwd without walking up.

Note for this machine: the walk stops at the *nearest* `vulcan_mind/`, so a nested repo
(as `vulcan_map/` currently is inside SpaceAGORA.jl) scopes to itself, not the parent.

---

## 13. Suggested build order

Not authorized yet — sequencing only, so dependencies are visible.

| # | Milestone | Contains | Why here |
|---|---|---|---|
| 1 | **Schema + model** | `schemas/`, `core/model.py`, fixtures | Everything else depends on the data shape |
| 2 | **Compile + validate** | `core/compile.py`, `core/validate.py`, V1–V16, round-trip test | The gate must exist before skills can reference it |
| 3 | **CLI skeleton** | `init`, `compile`, `check`, `worklist`, `doctor` | Makes milestone 2 usable by an agent |
| 4 | **Skills** | three SKILL.md + adapters | Now `vulcan check` is real, so the contract is enforceable |
| 5 | **Dogfood on SpaceAGORA.jl** | map the `sim` region only | Validates regions, grounding, and Julia symbol matching on a real repo |
| 6 | **UI read-only** | scene, items, sidebar, doc panel, layout | Renders what milestone 5 produced |
| 7 | **UI editing** | `QUndoCommand` write-back, live check status | The P3 round-trip |
| 8 | **Shims + packaging** | `environment.yml`, `install-shim`, cross-shell tests | Distribution last |

Milestone 5 before any UI work is deliberate: the map's *content* quality is the risky part
of this project, and it is testable without a GUI.

---

## 14. Decisions

**All design decisions are closed as of 2026-09-08. There are no open questions blocking
implementation.**

### 14.1 Decided — locked, do not revisit without an explicit change request

| # | Ref | Decision | Date |
|---|---|---|---|
| D1 | **A6** | **Strict conda-only; no pip fallback.** All dependencies resolve from conda channels. | 2026-09-08 |
| D2 | **A6 / §11.1** | **UI stack: PySide6 + a custom `QGraphicsView`/`QGraphicsScene` node editor.** NodeGraphQt ruled out (not conda-installable); vendoring considered and rejected. | 2026-09-08 |
| D3 | **A2 / A9 / §5.1** | **Granularity: module-level master chart + function-level subcharts.** No exhaustive function-level master. Coverage (V13) is therefore satisfied at module level for the master; function-level completeness is a per-subchart obligation. | 2026-09-08 |
| D4 | **A5 / §4** | **`vulcan_mind/` is committed to the target repo**, with `vulcan_mind/_build/` gitignored. The map is reviewable, diffable documentation, not a regenerable cache. | 2026-09-08 |
| D5 | **A1 / §6.2 / V5** | **Recursion and mutual recursion are mapped as `kind: "feedback"` edges**, exempt from the acyclicity check and rendered as dashed noodles. Cyclic call structures are never silently dropped. | 2026-09-08 |
| D6 | **A12 / §6.2** | **Human edits are sticky.** Agents must preserve `ui.pos` and may not delete `origin: "human"` nodes or edges without an explicit `--allow-removal` flag. | 2026-09-08 |
| D7 | **§9.4** | **Baseline agent adapters: Claude Code, Codex, Devin, generic `AGENTS.md`.** Cursor is deliberately excluded from the baseline; adapters are additive and can be added later. | 2026-09-08 |
| D8 | **§8.1** | **`vulcan check` never runs in CI and installs no pre-commit hook.** It runs during map creation and edits — inside the skill's own batch loop, at the completion gate, and on every UI mutation. Staleness is reported by V17, not enforced at merge. | 2026-09-08 |
| D9 | **A8 / §6.3** | **A subchart is a view over the master node set**, not an independent graph: it references master nodes by ID and may add finer nodes via `expands`, but cannot contradict the master. *Default retained — flagged for ratification (see note below).* | 2026-09-08 |

These are settled inputs to the build order in §13, not recommendations. Each is carried
into the section named in its `Ref` column; that section is authoritative for detail.

**Note on D9.** D1–D8 were explicitly ratified by the owner. D9 was not: A8 was marked as
needing an owner decision in §2 but was omitted from the open-questions list the owner
reviewed — an error in an earlier revision of this document. Its default (subchart-as-view)
therefore stands unopposed rather than affirmatively chosen. It is recorded here as decided
because the reasoning holds and nothing downstream conflicts with it, but it is the one row
that has not been through the same confirmation as the others. Raised explicitly so it is
not mistaken for a ratified decision.

### 14.2 Open decisions

**None.** This section is intentionally empty. Every ambiguity flagged in §2 has been
resolved and recorded in §14.1.

### 14.3 Facts to verify at implementation time

These are **not** open decisions — no design choice depends on them, and none can reopen a
§14.1 row. They are external facts to confirm rather than assume, in the same way
conda-forge availability was confirmed before locking D2.

| Ref | To verify | If it comes back different |
|---|---|---|
| §9.4 | The exact repo-level instruction file Devin reads, and whether it honours `AGENTS.md` directly | The `devin.py` adapter's output path changes; skill content is unaffected |
| §11.1 | conda-forge availability and current versions of `networkx`, `pyyaml`, `jsonschema`, `markdown-it-py`, `matplotlib` at env-creation time | Substitute a conda-installable equivalent; D1 forbids a pip fallback |
| §2 A11 | Whether any conda-installable Julia parser exists worth adopting | Julia grounder stays regex-based, which V6 already only requires |

### 14.4 What would reopen a decision

For the record, so this does not get relitigated informally: a §14.1 row changes only on an
explicit written change request from the owner, or on discovery that the decision is
technically impossible (e.g. a required package proving unavailable under D1). Neither
inconvenience during implementation nor an agent's preference is sufficient.
