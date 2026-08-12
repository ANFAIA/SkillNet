"""Compiled LangGraph for one node render (§4.2).

```
load_context ─► probe_gate ──(mastered)──────────────────────────► skip_node ──► END
                    │ needs_content
                    ▼
              decide_formato ─► author_activity ─► genera_ui ─► validate_ui ──(ok)──► persist_render ─► END
                                    ▲             │
                                    └─(invalid, retry<MAX)
                                                  │
                                                  └─(fail)───────► fallback_seed ──► END
```

Checkpointer: ``MemorySaver``, like v1 and the schema graph. The real state of a render is
``node_renders`` plus ``learner_node_states``, both in Postgres, so
``langgraph-checkpoint-postgres`` would be a new dependency buying nothing (and the human
gate of this feature is a database state, not an ``interrupt``).

Two routing decisions are worth reading twice:

* **``route_after_validate`` is the repair loop.** Invalid output with
  ``retry_count <= MAX_UI_RETRIES`` goes back to ``genera_ui`` — which sees a non-zero
  ``retry_count`` and switches to the repair prompt carrying the validator's own messages.
  Beyond that it goes to ``fallback_seed``: a model that has failed the same instructions
  twice will not succeed on the third try, and the learner is owed a screen.
* **An ``error`` short-circuits to ``fallback_seed``, not to a terminal handler.** This is
  the opposite choice from the schema graph, and deliberately so: there, continuing after a
  failure would overwrite a real schema with an empty one, so failing was the safe act.
  Here the failure is in *generating* content nobody has yet, and §9.3 level 4 says the seed
  lesson is the answer — the course keeps working in degraded v1 mode instead of breaking.
  ``fallback_seed`` failing in turn is caught by its own wrapper and ends the graph.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.runtime.nodes import (
    author_activity,
    decide_formato,
    fallback_seed,
    genera_ui,
    load_context,
    persist_render,
    probe_gate,
    skip_node,
    validate_ui,
)
from src.agents.runtime.state import NodeRuntimeState
from src.config import settings
from src.llm.prompts.runtime import MAX_UI_RETRIES


def route_after_load(state: NodeRuntimeState) -> str:
    """``"error"`` if loading failed, else straight on to the gate."""
    return "error" if state.get("error") else "ok"


def route_after_gate(state: NodeRuntimeState) -> str:
    """``"skip"`` when the learner already mastered the node (0 tokens, §2)."""
    if state.get("error"):
        return "error"
    return "skip" if state.get("mastered") else "generate"


def route_after_decide(state: NodeRuntimeState) -> str:
    return "error" if state.get("error") else "ok"


def route_after_generate(state: NodeRuntimeState) -> str:
    return "error" if state.get("error") else "ok"


def route_after_validate(state: NodeRuntimeState) -> str:
    """``"ok"`` | ``"retry"`` | ``"fallback"`` — the repair loop of §4.2."""
    if state.get("error"):
        return "fallback"
    if state.get("ui_spec"):
        return "ok"
    if int(state.get("retry_count") or 0) <= MAX_UI_RETRIES:
        return "retry"
    return "fallback"


def route_after_persist(state: NodeRuntimeState) -> str:
    """A failed persist still owes the learner a screen, so it falls back too."""
    return "fallback" if state.get("error") else "ok"


def build_node_graph():
    """Build and compile the runtime render graph."""
    graph = StateGraph(NodeRuntimeState)

    graph.add_node("load_context", load_context)
    graph.add_node("probe_gate", probe_gate)
    graph.add_node("decide_formato", decide_formato)
    graph.add_node("author_activity", author_activity)
    # The existing blueprint agent has a fixed legacy vocabulary. Until it consumes the
    # same closed scope, shortlist mode must use the monolithic generator; otherwise a
    # second prompt path could bypass the renderer-safe boundary.
    if settings.MULTI_AGENT_RENDER and not settings.RUNTIME_COMPONENT_SHORTLIST:
        from src.agents.runtime.nodes import genera_ui_multi
        graph.add_node("genera_ui", genera_ui_multi)
    else:
        graph.add_node("genera_ui", genera_ui)
    graph.add_node("validate_ui", validate_ui)
    graph.add_node("persist_render", persist_render)
    graph.add_node("fallback_seed", fallback_seed)
    graph.add_node("skip_node", skip_node)

    graph.set_entry_point("load_context")
    graph.add_conditional_edges(
        "load_context",
        route_after_load,
        {"ok": "probe_gate", "error": "fallback_seed"},
    )
    graph.add_conditional_edges(
        "probe_gate",
        route_after_gate,
        {"generate": "decide_formato", "skip": "skip_node", "error": "fallback_seed"},
    )
    graph.add_conditional_edges(
        "decide_formato",
        route_after_decide,
        {"ok": "author_activity", "error": "fallback_seed"},
    )
    graph.add_edge("author_activity", "genera_ui")
    graph.add_conditional_edges(
        "genera_ui",
        route_after_generate,
        {"ok": "validate_ui", "error": "fallback_seed"},
    )
    graph.add_conditional_edges(
        "validate_ui",
        route_after_validate,
        {
            "ok": "persist_render",
            "retry": "genera_ui",
            "fallback": "fallback_seed",
        },
    )
    graph.add_conditional_edges(
        "persist_render",
        route_after_persist,
        {"ok": END, "fallback": "fallback_seed"},
    )
    graph.add_edge("fallback_seed", END)
    graph.add_edge("skip_node", END)

    return graph.compile(checkpointer=MemorySaver())


__all__ = [
    "build_node_graph",
    "route_after_decide",
    "route_after_gate",
    "route_after_generate",
    "route_after_load",
    "route_after_persist",
    "route_after_validate",
]
