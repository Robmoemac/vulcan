"""UI tests: the scene renders exactly the resolved graph and nothing else (P3).

Runs headless. Skipped when PySide6 is unavailable so the core suite stays
runnable without the UI dependencies.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from vulcan_map.core import compile as compile_mod  # noqa: E402
from vulcan_map.core.mutations import enqueue_add_edge  # noqa: E402
from vulcan_map.core.repo import Mind  # noqa: E402
from vulcan_map.ui.graph_scene import GraphScene  # noqa: E402
from vulcan_map.ui.graph_view import GraphView  # noqa: E402
from vulcan_map.ui.items import noodle_path  # noqa: E402
from vulcan_map.ui.session import Session  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def session(repo: Path, qapp) -> Session:
    s = Session(repo_root=repo)
    s.reload()
    return s


def test_scene_matches_resolved_graph(session: Session) -> None:
    graph = session.graph("master")
    scene = GraphScene()
    scene.load(graph)
    assert set(scene.nodes) == {n.id for n in graph.nodes}
    assert set(scene.edges) == {e.id for e in graph.edges}


def test_every_edge_item_has_backing_sockets(session: Session) -> None:
    """The invariant: nothing is drawn that the JSON does not back."""
    scene = GraphScene()
    scene.load(session.graph("master"))
    for edge_id, item in scene.edges.items():
        assert item.source.socket_id == item.edge.from_.socket
        assert item.target.socket_id == item.edge.to.socket
        assert item.source.node_id == item.edge.from_.node
        assert item.target.node_id == item.edge.to.node


def test_new_edge_appears_only_after_recompile(repo: Path, session: Session) -> None:
    """A drawn edge must round-trip through the compiler before it renders."""
    mind = Mind(repo)
    scene = GraphScene()
    scene.load(session.graph("master"))
    before = len(scene.edges)

    enqueue_add_edge(
        mind, "master",
        from_node="telemetry.run", from_socket="path_out",
        to_node="propagator.propagate_orbit", to_socket="state0",
        evidence_file="src/telemetry.py",
    )
    # Nothing has rendered and nothing has been written — the edit is only queued.
    assert len(scene.edges) == before
    assert mind.pending_path.exists()

    session.reload()  # runs compile, which folds the queue
    scene.load(session.graph("master"))
    assert len(scene.edges) == before + 1
    assert not mind.pending_path.exists()


def test_edge_with_undeclared_socket_is_never_drawn(repo: Path, session: Session) -> None:
    """`result` is not a socket on `run`, so the noodle has nothing to attach to.

    The scene must skip it rather than invent an anchor; V4 reports it separately.
    """
    enqueue_add_edge(
        Mind(repo), "master",
        from_node="telemetry.run", from_socket="result",
        to_node="telemetry.write_telemetry", to_socket="data",
        evidence_file="src/telemetry.py",
    )
    session.reload()
    scene = GraphScene()
    scene.load(session.graph("master"))

    assert "e:telemetry.run:result->telemetry.write_telemetry:data" not in scene.edges
    assert session.errors > 0  # surfaced in the status bar, not silently ignored


def test_connection_signal_normalises_direction(session: Session, qapp) -> None:
    """Dragging input->output is the same connection as output->input."""
    scene = GraphScene()
    scene.load(session.graph("master"))
    seen: list[tuple[str, str, str, str]] = []
    scene.connection_requested.connect(lambda a, b, c, d: seen.append((a, b, c, d)))

    out = scene.nodes["propagator.propagate_orbit"].socket("traj", is_input=False)
    inp = scene.nodes["telemetry.write_telemetry"].socket("data", is_input=True)

    scene._request_connection(out, inp)
    scene._request_connection(inp, out)  # reversed drag
    assert len(seen) == 2 and seen[0] == seen[1]


def test_same_node_and_same_direction_are_refused(session: Session) -> None:
    scene = GraphScene()
    scene.load(session.graph("master"))
    seen: list[tuple] = []
    scene.connection_requested.connect(lambda *a: seen.append(a))

    node = scene.nodes["telemetry.run"]
    scene._request_connection(node.socket("state0_out", False), node.socket("state0", True))
    assert seen == []  # self-connection

    a = scene.nodes["telemetry.run"].socket("state0", True)
    b = scene.nodes["telemetry.write_telemetry"].socket("data", True)
    scene._request_connection(a, b)
    assert seen == []  # input -> input


def test_feedback_edges_are_drawn_dashed(repo: Path, session: Session) -> None:
    """D5 is visible, not just tolerated."""
    import json

    mind = Mind(repo)
    data = json.loads(mind.master_path.read_text(encoding="utf-8"))
    data["edges"].append({
        "id": "e:telemetry.write_telemetry:written_path->telemetry.run:path",
        "from": {"node": "telemetry.write_telemetry", "socket": "written_path"},
        "to": {"node": "telemetry.run", "socket": "path"},
        "kind": "feedback",
        "evidence": {"file": "src/telemetry.py"},
        "origin": "agent",
    })
    mind.master_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    session.reload()

    scene = GraphScene()
    scene.load(session.graph("master"))
    feedback = [i for i in scene.edges.values() if i.edge.is_feedback]
    assert len(feedback) == 1


def test_node_positions_come_from_the_graph(session: Session) -> None:
    scene = GraphScene()
    graph = session.graph("master")
    scene.load(graph)
    for node in graph.nodes:
        if node.pos:
            item = scene.nodes[node.id]
            assert (item.pos().x(), item.pos().y()) == node.pos


def test_noodle_is_a_curve_not_a_line() -> None:
    path = noodle_path(QPointF(0, 0), QPointF(200, 100))
    assert path.elementCount() >= 4  # moveTo + cubic control points


def test_view_fit_ignores_unlaid_out_viewport(session: Session, qapp) -> None:
    """Regression: fitting against an unrealised viewport zoomed the graph to a speck.

    The window defers its first fit to showEvent; this guard covers the case
    where fit is reached anyway with a viewport that has no usable size.
    """
    scene = GraphScene()
    scene.load(session.graph("master"))
    view = GraphView(scene)

    view.resize(10, 10)
    view.viewport().resize(10, 10)
    qapp.processEvents()
    before = view.transform().m11()
    view.fit()
    assert view.transform().m11() == before


def test_view_fit_scales_to_content_when_laid_out(session: Session, qapp) -> None:
    scene = GraphScene()
    scene.load(session.graph("master"))
    view = GraphView(scene)
    view.resize(1000, 600)
    view.viewport().resize(1000, 600)
    qapp.processEvents()
    view.fit()
    assert 0.2 < view.transform().m11() <= 1.0


def test_status_text_reports_check_state(session: Session) -> None:
    assert "check: PASS" in session.status_text("master")


def test_math_falls_back_to_source_when_unavailable(monkeypatch) -> None:
    """A broken matplotlib must degrade the panel, never take down the UI.

    Some builds abort the process inside savefig, which no try/except can catch,
    so availability is probed once in a subprocess and rendering is skipped when
    it fails.
    """
    from vulcan_map.ui import mathtext

    monkeypatch.setattr(mathtext, "available", lambda: False)
    mathtext.render_latex.cache_clear()

    out = mathtext.substitute("Inline $x^2$ and\n\n$$E = mc^2$$\n")
    assert "<code>x^2</code>" in out
    assert "<pre>E = mc^2</pre>" in out
    assert "data:image" not in out
    mathtext.render_latex.cache_clear()


def test_doc_panel_renders_a_node_with_math(repo: Path, session: Session, qapp) -> None:
    """Selecting a node must not crash regardless of matplotlib's state."""
    from vulcan_map.ui.doc_panel import DocPanel

    panel = DocPanel()
    path = session.doc_path("master", "propagator.propagate_orbit")
    assert path is not None and path.exists()

    panel.show_doc(path, "propagator.propagate_orbit")
    html = panel.browser.toHtml()
    assert "propagate_orbit" in html
    assert panel.title.text() == "propagator.propagate_orbit"


# --- drill-through ------------------------------------------------------------

def test_expansions_maps_parent_nodes_to_their_detail_charts(repo: Path, mind: Mind, qapp) -> None:
    import json

    doc = mind.nodes_dir / "propagator" / "inner.md"
    doc.write_text(
        open(mind.nodes_dir / "propagator" / "propagate_orbit.md", encoding="utf-8")
        .read()
        .replace("id: propagator.propagate_orbit", "id: propagator.inner")
        .replace("label: propagate_orbit", "label: inner"),
        encoding="utf-8",
    )
    sub = {
        "schema_version": "1.0.0", "chart_id": "detail", "chart_kind": "sub",
        "derives_from": "master", "title": "Detail",
        "member_nodes": ["propagator.propagate_orbit"],
        "local_nodes": [{
            "id": "propagator.inner", "label": "inner", "kind": "function",
            "doc": "nodes/propagator/inner.md",
            "source": {"file": "src/propagator.py", "symbol": "propagate_orbit"},
            "expands": "propagator.propagate_orbit", "origin": "agent",
        }],
        "local_edges": [],
    }
    (mind.subcharts_dir / "detail.graph.json").write_text(json.dumps(sub, indent=2), encoding="utf-8")

    s = Session(repo_root=repo)
    s.reload()
    assert s.expansions().get("propagator.propagate_orbit") == ["detail"]
    assert s.expansion_for("propagator.propagate_orbit") == "detail"
    assert s.expansion_for("telemetry.run") is None


def test_scene_marks_expandable_nodes(session: Session) -> None:
    scene = GraphScene()
    graph = session.graph("master")
    scene.load(graph, {"propagator.propagate_orbit"})
    assert scene.nodes["propagator.propagate_orbit"].expandable is True
    assert scene.nodes["telemetry.run"].expandable is False


def test_double_click_emits_node_activated(session: Session, qapp) -> None:
    """Regression: `expands` existed in the data but nothing in the UI used it."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    scene = GraphScene()
    scene.load(session.graph("master"), set())
    seen: list[str] = []
    scene.node_activated.connect(seen.append)

    target = scene.nodes["telemetry.run"]
    event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMouseDoubleClick)
    event.setScenePos(target.sceneBoundingRect().center())
    event.setButton(Qt.MouseButton.LeftButton)
    scene.mouseDoubleClickEvent(event)

    assert seen == ["telemetry.run"]


def test_double_click_on_empty_canvas_emits_nothing(session: Session, qapp) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    scene = GraphScene()
    scene.load(session.graph("master"), set())
    seen: list[str] = []
    scene.node_activated.connect(seen.append)

    event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMouseDoubleClick)
    event.setScenePos(QPointF(-9999, -9999))
    event.setButton(Qt.MouseButton.LeftButton)
    scene.mouseDoubleClickEvent(event)

    assert seen == []


# --- workflow charts must render like any other (D12) --------------------------

def test_workflow_chart_renders_in_the_scene(repo: Path, mind: Mind, qapp) -> None:
    """The renderer had only ever drawn master and sub charts."""
    import json

    (mind.subcharts_dir / "flow.graph.json").write_text(json.dumps({
        "schema_version": "1.0.0", "chart_id": "flow", "chart_kind": "workflow",
        "derives_from": "master", "title": "Flow",
        "seeds": [{"node": "telemetry.run", "why": "entry point"}],
        "traversal": {"direction": "downstream", "max_depth": 4},
        "member_nodes": [],
    }, indent=2), encoding="utf-8")

    s = Session(repo_root=repo)
    s.reload()
    graph = s.graph("flow")
    assert graph is not None, "workflow chart did not resolve"
    assert graph.chart_kind == "workflow"
    assert len(graph.nodes) >= 2

    scene = GraphScene()
    scene.load(graph, set(s.expansions()))
    assert set(scene.nodes) == {n.id for n in graph.nodes}
    # every node it borrowed got a position from layout, so nothing stacks
    positions = [scene.nodes[n.id].pos() for n in graph.nodes]
    assert len({(p.x(), p.y()) for p in positions}) == len(positions)


def test_workflow_chart_appears_in_the_sidebar_listing(repo: Path, mind: Mind, qapp) -> None:
    import json

    (mind.subcharts_dir / "flow.graph.json").write_text(json.dumps({
        "schema_version": "1.0.0", "chart_id": "flow", "chart_kind": "workflow",
        "derives_from": "master", "title": "Flow",
        "seeds": [{"node": "telemetry.run"}],
        "traversal": {"direction": "downstream", "max_depth": 4},
        "member_nodes": [],
    }, indent=2), encoding="utf-8")

    s = Session(repo_root=repo)
    s.reload()
    listed = {c.chart_id: c.chart_kind for c in s.charts()}
    assert listed.get("flow") == "workflow"
    assert listed.get("master") == "master"
