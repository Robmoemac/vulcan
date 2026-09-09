"""PySide6 node-graph UI.

Custom QGraphicsView implementation rather than NodeGraphQt, which is not
available from conda-forge (PLAN.md D1/D2). Importing this package requires
PySide6; the CLI imports it lazily so core commands work without it.
"""
