"""Compiled LangGraph for the autonomous content generation pipeline.

No human-in-the-loop, no interrupts. In-memory ``MemorySaver`` checkpointer
(jobs are short-lived and tracked in ``generation_jobs``).
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.content.nodes import (
    design_structure,
    extract_themes,
    generate_modules,
    handle_error,
    prepare_context,
    publish,
    refine_content,
    review_quality,
)
from src.agents.content.routing import route_after_quality_review
from src.agents.content.state import GenerationState


def build_content_graph():
    """Build and compile the content generation graph."""
    graph = StateGraph(GenerationState)

    graph.add_node("prepare_context", prepare_context)
    graph.add_node("extract_themes", extract_themes)
    graph.add_node("design_structure", design_structure)
    graph.add_node("generate_modules", generate_modules)
    graph.add_node("review_quality", review_quality)
    graph.add_node("refine_content", refine_content)
    graph.add_node("publish", publish)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("prepare_context")
    graph.add_edge("prepare_context", "extract_themes")
    graph.add_edge("extract_themes", "design_structure")
    graph.add_edge("design_structure", "generate_modules")
    graph.add_edge("generate_modules", "review_quality")

    graph.add_conditional_edges(
        "review_quality",
        route_after_quality_review,
        {
            "pass": "publish",
            "refine": "refine_content",
            "fail": "handle_error",
        },
    )

    graph.add_edge("refine_content", "review_quality")
    graph.add_edge("publish", END)
    graph.add_edge("handle_error", END)

    return graph.compile(checkpointer=MemorySaver())
