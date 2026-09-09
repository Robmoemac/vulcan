---
id: grounding.base.check
label: check
kind: function
source:
  file: src/vulcan_map/core/grounding/base.py
  symbol: check
  lines:
  - 29
  - 34
inputs:
- id: impl
  type: Callable
  units: n/a
  required: true
  description: The concrete contains_symbol supplied by the subclass.
- id: path
  type: Path
  units: n/a
  required: true
  description: Absolute path to the source file being checked.
outputs:
- id: verdict
  type: bool
  units: n/a
  description: True when the symbol occurs in the file; False on any read error.
tags:
- grounding
charts:
- master
origin: agent
---

# check

## Purpose
The single entry point the validator calls for rule V6. Reads a source file and
reports whether a named symbol occurs in it.

## Model & Assumptions
- The caller has already established that `path` exists; a missing file is
  reported by V6 before `check` is reached.
- Read errors are not exceptional conditions to propagate. A file that cannot be
  read cannot ground a symbol, so `False` is the correct answer rather than a
  raised exception that would abort the whole validation pass.

## Design & Implementation
The body reads the file with `encoding="utf-8", errors="replace"` inside a
`try`, returning `False` on `OSError`, then delegates to `self.contains_symbol`.
Decoding with replacement rather than strict mode means a file containing
invalid byte sequences still yields a searchable string, so one malformed file
cannot mask grounding failures across an entire map.

Dispatch to the concrete implementation is ordinary Python method resolution,
which is why the `impl` input on this node is drawn from the abstract interface
rather than from any one subclass.

## Interface (ICD)
<!-- vulcan:icd:begin -->
| Direction | Socket | Type | Units | Required | Description |
|---|---|---|---|---|---|
| in | `impl` | Callable | n/a | yes | The concrete contains_symbol supplied by the subclass. |
| in | `path` | Path | n/a | yes | Absolute path to the source file being checked. |
| out | `verdict` | bool | n/a | — | True when the symbol occurs in the file; False on any read error. |
<!-- vulcan:icd:end -->

## Connections
<!-- vulcan:connections:begin -->
**Upstream**

- [[grounding.base.grounder|Grounder]] · `interface` → `impl` · call · `src/vulcan_map/core/grounding/base.py:33-34`

**Downstream**

- *none*
<!-- vulcan:connections:end -->

## Limitations
Every call re-reads the file from disk with no caching, so validating a map whose
nodes cluster in a few large files reads those files once per node. For map sizes
seen so far this is well under the cost of the surrounding validation pass, but
it is the obvious place to memoise if grounding ever dominates runtime.

## Provenance
Mapped from `src/vulcan_map/core/grounding/base.py`.
