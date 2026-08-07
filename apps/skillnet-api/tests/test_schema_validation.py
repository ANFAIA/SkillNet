"""Unit tests for the pure schema-graph algorithms (§12.2). No DB, no network.

Covers cycle detection (self-edge, 2-cycle, 5-cycle, a large valid DAG), orphan
prerequisites, ``no_critical_node``, the remaining blocking rules of §11.1, and the
cycle pruning ``persist_schema`` applies to an LLM proposal.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from src.services.course_schema_service import (
    default_threshold_for,
    find_cycle,
    prune_cyclic_prerequisites,
    topological_order,
    validate_schema_graph,
)


# --------------------------------------------------------------------------- #
# find_cycle
# --------------------------------------------------------------------------- #
def test_find_cycle_empty_graph() -> None:
    assert find_cycle([], {}) == []


def test_find_cycle_linear_chain_is_a_dag() -> None:
    # c requires b, b requires a.
    assert find_cycle(["a", "b", "c"], {"b": ["a"], "c": ["b"]}) == []


def test_find_cycle_self_edge() -> None:
    assert find_cycle(["a", "b"], {"a": ["a"]}) == ["a"]


def test_find_cycle_two_cycle_reports_both_ids() -> None:
    cycle = find_cycle(["a", "b"], {"a": ["b"], "b": ["a"]})
    assert sorted(cycle) == ["a", "b"]
    # §11.1's example carries exactly the two members, not a closed loop.
    assert len(cycle) == 2


def test_find_cycle_five_cycle() -> None:
    ids = ["a", "b", "c", "d", "e"]
    edges = {"a": ["b"], "b": ["c"], "c": ["d"], "d": ["e"], "e": ["a"]}
    cycle = find_cycle(ids, edges)
    assert sorted(cycle) == ids


def test_find_cycle_ignores_a_cycle_outside_the_known_ids() -> None:
    # An edge to an unknown node is an orphan, reported by validate_schema_graph,
    # and must not be mistaken for a cycle.
    assert find_cycle(["a"], {"a": ["ghost"]}) == []


def test_find_cycle_large_valid_dag() -> None:
    # 40 nodes, every node depending on all its predecessors: dense but acyclic.
    ids = [f"n{i}" for i in range(40)]
    edges = {ids[i]: ids[:i] for i in range(40)}
    assert find_cycle(ids, edges) == []


def test_find_cycle_finds_a_cycle_hidden_in_a_large_dag() -> None:
    ids = [f"n{i}" for i in range(40)]
    edges: dict[str, list[str]] = {ids[i]: [ids[i - 1]] for i in range(1, 40)}
    edges[ids[0]] = [ids[39]]
    assert len(find_cycle(ids, edges)) == 40


def test_find_cycle_disconnected_components() -> None:
    ids = ["a", "b", "x", "y"]
    edges = {"b": ["a"], "x": ["y"], "y": ["x"]}
    assert sorted(find_cycle(ids, edges)) == ["x", "y"]


# --------------------------------------------------------------------------- #
# topological_order
# --------------------------------------------------------------------------- #
def test_topological_order_puts_prerequisites_first() -> None:
    order = topological_order(["c", "b", "a"], {"c": ["b"], "b": ["a"]})
    assert order == ["a", "b", "c"]


def test_topological_order_is_none_on_a_cycle() -> None:
    assert topological_order(["a", "b"], {"a": ["b"], "b": ["a"]}) is None


def test_topological_order_ignores_self_and_unknown_edges() -> None:
    assert topological_order(["a"], {"a": ["a", "ghost"]}) == ["a"]


def test_topological_order_is_deterministic() -> None:
    ids = ["a", "b", "c", "d"]
    edges = {"d": ["a"], "c": ["a"]}
    assert topological_order(ids, edges) == ["a", "b", "c", "d"]


# --------------------------------------------------------------------------- #
# prune_cyclic_prerequisites — what persist_schema applies to a proposal
# --------------------------------------------------------------------------- #
def _proposal(*prereqs: list) -> list[dict]:
    return [
        {"title": f"Nodo {i}", "summary": "s", "prerequisites": p}
        for i, p in enumerate(prereqs)
    ]


def test_prune_keeps_an_acyclic_proposal_untouched() -> None:
    pruned, warnings = prune_cyclic_prerequisites(_proposal([], [0], [0, 1]))
    assert [node["prerequisites"] for node in pruned] == [[], [0], [0, 1]]
    assert warnings == []


def test_prune_drops_the_edge_that_closes_a_cycle_and_warns() -> None:
    pruned, warnings = prune_cyclic_prerequisites(_proposal([1], [0]))
    # The first edge survives, the one that closes the loop does not.
    assert pruned[0]["prerequisites"] == [1]
    assert pruned[1]["prerequisites"] == []
    assert len(warnings) == 1
    assert "ciclico" in warnings[0]
    assert "Nodo 1" in warnings[0] and "Nodo 0" in warnings[0]
    assert find_cycle(
        list(range(2)), {i: node["prerequisites"] for i, node in enumerate(pruned)}
    ) == []


def test_prune_drops_a_self_edge() -> None:
    pruned, warnings = prune_cyclic_prerequisites(_proposal([0]))
    assert pruned[0]["prerequisites"] == []
    assert "si mismo" in warnings[0]


def test_prune_drops_out_of_range_and_non_numeric_indices() -> None:
    pruned, warnings = prune_cyclic_prerequisites(_proposal([], [7, "x", -1]))
    assert pruned[1]["prerequisites"] == []
    assert len(warnings) == 3


def test_prune_deduplicates_repeated_edges_without_warning() -> None:
    pruned, warnings = prune_cyclic_prerequisites(_proposal([], [0, 0]))
    assert pruned[1]["prerequisites"] == [0]
    assert warnings == []


def test_prune_breaks_a_five_cycle_with_a_single_drop() -> None:
    pruned, warnings = prune_cyclic_prerequisites(
        _proposal([4], [0], [1], [2], [3])
    )
    edges = {i: node["prerequisites"] for i, node in enumerate(pruned)}
    assert find_cycle(list(range(5)), edges) == []
    assert len(warnings) == 1


def test_prune_preserves_every_other_field() -> None:
    proposal = [{"title": "T", "summary": "S", "criticality": "critical",
                 "prerequisites": []}]
    pruned, _ = prune_cyclic_prerequisites(proposal)
    assert pruned[0]["criticality"] == "critical"
    assert pruned[0]["title"] == "T"


# --------------------------------------------------------------------------- #
# validate_schema_graph — the blocking rules of §11.1
# --------------------------------------------------------------------------- #
def _node(
    *,
    position: int,
    criticality: str = "recommended",
    summary: str = "un resumen",
    reviewed: bool = True,
    source: bool = True,
    archived: bool = False,
    node_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=node_id or uuid.uuid4(),
        title=f"Nodo {position}",
        summary=summary,
        criticality=criticality,
        position=position,
        source_document_id=uuid.uuid4() if source else None,
        seed_lesson_id=None,
        reviewed_at="2026-07-25T00:00:00Z" if reviewed else None,
        archived=archived,
    )


def _codes(errors: list[dict]) -> list[str]:
    return [error["code"] for error in errors]


def test_validate_accepts_a_well_formed_schema() -> None:
    a = _node(position=1, criticality="critical")
    b = _node(position=2)
    assert validate_schema_graph([a, b], {b.id: [a.id]}) == []


def test_validate_rejects_an_empty_schema() -> None:
    assert _codes(validate_schema_graph([], {})) == ["empty_schema"]


def test_validate_rejects_a_schema_whose_only_nodes_are_archived() -> None:
    assert _codes(
        validate_schema_graph([_node(position=1, archived=True)], {})
    ) == ["empty_schema"]


def test_validate_requires_a_critical_node() -> None:
    errors = validate_schema_graph([_node(position=1)], {})
    assert "no_critical_node" in _codes(errors)


def test_validate_requires_a_non_empty_summary() -> None:
    node = _node(position=1, criticality="critical", summary="   ")
    errors = validate_schema_graph([node], {})
    assert "missing_summary" in _codes(errors)
    reported = next(e for e in errors if e["code"] == "missing_summary")
    assert reported["node_ids"] == [str(node.id)]


def test_validate_reports_orphan_prerequisites() -> None:
    node = _node(position=1, criticality="critical")
    ghost = uuid.uuid4()
    errors = validate_schema_graph([node], {node.id: [ghost]})
    orphan = next(e for e in errors if e["code"] == "orphan_prerequisite")
    assert orphan["node_ids"] == [str(ghost)]


def test_validate_reports_a_cycle() -> None:
    a = _node(position=1, criticality="critical")
    b = _node(position=2)
    errors = validate_schema_graph([a, b], {a.id: [b.id], b.id: [a.id]})
    cycle = next(e for e in errors if e["code"] == "cycle")
    assert sorted(cycle["node_ids"]) == sorted([str(a.id), str(b.id)])


def test_validate_requires_contiguous_positions_from_one() -> None:
    a = _node(position=1, criticality="critical")
    b = _node(position=3)
    assert "position_not_contiguous" in _codes(validate_schema_graph([a, b], {}))


def test_validate_ignores_archived_nodes_when_checking_positions() -> None:
    a = _node(position=1, criticality="critical")
    b = _node(position=2)
    gone = _node(position=9, archived=True)
    assert validate_schema_graph([a, b, gone], {}) == []


def test_validate_requires_every_node_to_be_reviewed() -> None:
    a = _node(position=1, criticality="critical", reviewed=False)
    errors = validate_schema_graph([a], {})
    unreviewed = next(e for e in errors if e["code"] == "node_not_reviewed")
    assert unreviewed["node_ids"] == [str(a.id)]


def test_validate_reports_every_violation_at_once() -> None:
    # A creator fixing a schema wants the whole list, not one error per round trip.
    a = _node(position=2, summary="", reviewed=False, source=False)
    codes = set(_codes(validate_schema_graph([a], {})))
    assert {
        "missing_summary",
        "no_critical_node",
        "position_not_contiguous",
        "node_not_reviewed",
    } <= codes


# --------------------------------------------------------------------------- #
# threshold defaults (§3.2)
# --------------------------------------------------------------------------- #
def test_default_threshold_per_criticality() -> None:
    assert default_threshold_for("critical") == 0.90
    assert default_threshold_for("recommended") == 0.80
    assert default_threshold_for("contextual") == 0.70


def test_default_threshold_falls_back_for_garbage() -> None:
    assert default_threshold_for("nonsense") == 0.80
