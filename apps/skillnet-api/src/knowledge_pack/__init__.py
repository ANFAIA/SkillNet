"""Pure, reviewable knowledge packs used to prepare dynamic-course content.

The package deliberately has no database, LLM, runtime, or rendering dependencies.
It is a contract and a deterministic selector that can be exercised in shadow before a
pack is ever made part of course delivery.
"""

from src.knowledge_pack.contracts import (
    PACK_FORMAT,
    EvidenceSpec,
    GenerableSlot,
    MissingData,
    MissingDataArea,
    MustPreserveAtom,
    MustPreserveKind,
    NodeKnowledgePack,
    PackProvenance,
    PackStatus,
    SelectableAtom,
    SelectableKind,
    SourceRef,
)
from src.knowledge_pack.markdown import render_markdown
from src.knowledge_pack.selector import (
    SelectionDeclineReason,
    SelectionDeclined,
    SelectionRequest,
    SelectionResult,
    select_knowledge,
)

__all__ = [
    "PACK_FORMAT",
    "EvidenceSpec",
    "GenerableSlot",
    "MissingData",
    "MissingDataArea",
    "MustPreserveAtom",
    "MustPreserveKind",
    "NodeKnowledgePack",
    "PackProvenance",
    "PackStatus",
    "SelectableAtom",
    "SelectableKind",
    "SourceRef",
    "SelectionDeclineReason",
    "SelectionDeclined",
    "SelectionRequest",
    "SelectionResult",
    "render_markdown",
    "select_knowledge",
]
