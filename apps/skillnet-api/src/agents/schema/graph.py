"""Compiled LangGraph for the design-time schema proposal (§4.1).

```
load_source ──► extract_themes_schema ──► design_schema ──► persist_schema ──► END
      └──────────────── on error ────────────────► handle_error ──► END
```

Checkpointer: ``MemorySaver``, same as v1. The job is short and its real state lives
in ``generation_jobs`` + ``course_nodes``; ``langgraph-checkpoint-postgres`` is
deliberately **not** introduced (a new dependency, and the human gate is a database
state, not an ``interrupt``).

Unlike v1, a failing node short-circuits to ``handle_error`` instead of letting the
next node run on an empty state: a schema pipeline that keeps going after
``load_source`` failed would persist an empty schema over a real one.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.schema.nodes import (
    design_schema,
    extract_themes_schema,
    handle_error,
    load_source,
    persist_schema,
)
from src.agents.schema.state import SchemaState

_STEPS = (
    ("load_source", load_source, "extract_themes_schema"),
    ("extract_themes_schema", extract_themes_schema, "design_schema"),
    ("design_schema", design_schema, "persist_schema"),
    ("persist_schema", persist_schema, END),
)


def route_on_error(state: SchemaState) -> str:
    """``"error"`` as soon as any node has recorded one, else ``"ok"``."""
    return "error" if state.get("error") else "ok"


def build_schema_graph():
    """Build and compile the schema proposal graph."""
    graph = StateGraph(SchemaState)

    for name, fn, _ in _STEPS:
        graph.add_node(name, fn)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("load_source")
    for name, _, nxt in _STEPS:
        graph.add_conditional_edges(
            name, route_on_error, {"ok": nxt, "error": "handle_error"}
        )
    graph.add_edge("handle_error", END)

    return graph.compile(checkpointer=MemorySaver())
