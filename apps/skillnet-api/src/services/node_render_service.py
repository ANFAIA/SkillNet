"""Serving, caching, pinning and cancelling node renders (§3.4, §5.5, §9.1, §9.3).

Four cache levels, and this module owns three of them:

1. **``node_renders`` by ``cache_key``** — the shared row. Looked up by ``cache_key``
   **alone**, never with ``user_id`` in the ``WHERE`` (§9.3): that is what makes the second
   employee of the same bucket pay nothing.
2. **``active_render_id`` per ``(user, node)``** — the pinned render. While
   ``render_pinned`` is true, ``GET /nodes/{id}/render`` does not even consult the cache and
   **never recomputes the key**, so answering an item or a TanStack refetch on window focus
   cannot change the screen mid-node (the "Estable" row of §5.5). Only
   ``POST /render {"force": true}`` recomputes and repins.
3. (probes and term explanations are levels 3 and 4, owned elsewhere.)

Two invariants worth stating because they are easy to break by accident:

* **``answer_key`` never leaves this module.** :class:`ServedRender` has no such field, so
  a route cannot serialize it even by mistake; :meth:`NodeRenderService.answer_key_for` is
  the one accessor and it is used by the grading path, not by a response model.
* **Preview renders get a salted key.** ``cache_key`` is ``UNIQUE`` globally, so a preview
  computed from the same profile as a real render would collide with it on insert; and a
  preview *must* stay out of the cache (§11.3), so it cannot simply reuse the row. The salt
  makes every preview its own row, un-hittable by construction.
* **A forced refresh gets a salted key too, and for the same reason.** Nothing that moves
  with a click is *in* the key — ``mastery`` is excluded by design and ``scaffold_band`` is
  frozen when the probe closes — so "Actualizar esta leccion" (§5.5) recomputes the exact
  same key. Reading the cache with it would hand back the very render the learner asked to
  replace, and writing over the row would rewrite the screen of everybody else in the
  bucket. The salt is what makes the refresh a *new* row, leaving the shared one (and this
  learner's ``GET /renders`` history) intact.
"""

from __future__ import annotations

import asyncio
import enum
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.exceptions import ConflictError
from src.core.logging import get_logger
from src.llm.prompts.runtime import EPISODE_PROMPT_VERSION, PROMPT_VERSION
from src.models import (
    Course,
    CourseNode,
    LearnerNodeState,
    LearnerProfile,
    NodeRender,
    NodeRenderStatus,
    Organization,
)
from src.personalization.preferences import preference_bucket
from src.personalization.modality import tts_is_available
from src.personalization.projection import (
    LongitudinalHistoryProjection,
    project_longitudinal_history,
)
from src.personalization.selection_policy import SelectionExecution, live_cache_fragment
from src.render.prompt import catalog_version
from src.render.prompt_slice import RUNTIME_SCOPE_POLICY_VERSION
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.repositories.node_render_repo import SERVABLE_STATUSES, NodeRenderRepository
from src.repositories.node_render_view_repo import NodeRenderViewRepository
from src.services.cache_key import (
    accessibility_bucket,
    build_cache_key,
    effective_density,
    role_bucket,
)
from src.services.learner_profile_service import CALIBRATION_NODES, vector_bucket

logger = get_logger(__name__)


def current_prompt_version() -> str:
    """Exact instruction and catalogue version used by the shared render cache."""

    prompt_version = (
        f"{EPISODE_PROMPT_VERSION}+{PROMPT_VERSION}"
        if settings.ADAPTIVE_EPISODES
        else PROMPT_VERSION
    )
    if settings.RUNTIME_COMPONENT_SHORTLIST:
        return f"{prompt_version}+{catalog_version()}+{RUNTIME_SCOPE_POLICY_VERSION}"
    return f"{prompt_version}+{catalog_version()}"


SCREEN_SCHEME_POLICY_VERSION = "v1"
ADAPTIVE_EPISODES_POLICY_VERSION = "v1"


def generation_policy_key(adaptive_episodes: bool | None = None) -> str:
    """Versioned cache partition for the policy that constructs a learning episode."""

    enabled = settings.ADAPTIVE_EPISODES if adaptive_episodes is None else adaptive_episodes
    if enabled:
        return f"adaptive-episodes/{ADAPTIVE_EPISODES_POLICY_VERSION}"
    return f"screen-scheme/{SCREEN_SCHEME_POLICY_VERSION}"


SCREEN_SAFETY_EPOCH = "bounded-screen/1"


def current_render_safety_prefix() -> str:
    """Readable compatibility marker for the viewport and generation contracts.

    The generation policy also lives inside the hashed cache material, while keeping it in
    this prefix lets ``pinned_render`` reject a pin created by another rollout policy.
    Ordinary prompt/catalog updates still preserve the learner stability promised by
    Vision A.
    """

    return f"safety:{SCREEN_SAFETY_EPOCH}:generation:{generation_policy_key()}:"


def cache_key_uses_current_screen_contract(cache_key: str) -> bool:
    prefix = current_render_safety_prefix()
    return cache_key.startswith(prefix) or f":{prefix}" in cache_key

#: ``409`` code returned when the node has no ``reviewed_at`` (§3.2). Structural, not
#: advisory: the validation gate proves the graph is well formed, not that a human read the
#: pedagogy, so an unreviewed node cannot be served even in a validated course.
NODE_NOT_REVIEWED = "node_not_reviewed"

#: Prefix of a preview ``cache_key``. Also makes previews trivially greppable in the table.
PREVIEW_KEY_PREFIX = "preview"

#: Prefix of the ``cache_key`` of a forced refresh (§5.5). Same device as the preview salt,
#: different meaning: a refresh row **is** servable and **is** pinned, it simply belongs to
#: the one learner who asked for it, because nothing shared can be regenerated in place
#: without rewriting somebody else's open lesson.
REFRESH_KEY_PREFIX = "refresh"


def _plain(value: object) -> str:
    return value.value if isinstance(value, enum.Enum) else str(value)


# --------------------------------------------------------------------------------------
# The key. A pure function, called from exactly two places: the pre-graph cache check in
# this service, and ``load_context`` inside the graph (§4.2). One function, two call sites,
# deterministic output — the alternative is two authorities that drift.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderKey:
    """The ``cache_key`` plus every derived value the graph and the prompts also need."""

    cache_key: str
    effective_density: int
    vector_bucket: str
    preference_bucket: str
    accessibility_bucket: str
    knowledge_pack_key: str
    scaffold_band: str
    role_bucket: str
    model_key: str
    calibrating: bool
    is_preview: bool
    personalization_revision: int
    selection_policy_key: str
    generation_policy_key: str
    selection_strategy: str
    selection_execution: str
    longitudinal_decision_digest: str
    longitudinal_history: LongitudinalHistoryProjection


def build_render_key(
    *,
    node: Any,
    course: Any,
    profile: Any | None,
    node_state: Any | None,
    accessibility: dict | None = None,
    model_key: str,
    backend: str | None = None,
    is_preview: bool = False,
    preview_salt: str | None = None,
    refresh_salt: str | None = None,
    knowledge_pack_key: str = "",
    longitudinal_history: LongitudinalHistoryProjection | None = None,
) -> RenderKey:
    """Compose the ``cache_key`` of §3.4 from a loaded context.

    Three subtleties, all of them load-bearing:

    * ``role_bucket`` is in the key because ``role_title`` is the one learner string that
      travels *literally* into ``genera_ui`` (§6.2). Without it a shop assistant and a shift
      manager with the same preset shared a row and the second one silently got examples
      framed for the first one's job.
    * ``scaffold_band`` is in the key and ``mastery`` is **not**. ``mastery`` moves with every
      answer (0 -> 0.40 -> 0.64 -> 0.784 …), which inside one ``critical`` node would be four
      different keys; ``scaffold_band`` is frozen when the probe closes.
    * ``vector_bucket`` is ``""`` during the calibration period, so the first three nodes of
      a new learner share a key with everybody else in the same declared bucket (§6.4).
    """
    nodes_completed = int(getattr(profile, "nodes_completed", 0) or 0)
    bucket = vector_bucket(getattr(profile, "format_vector", None), nodes_completed)
    band = _plain(getattr(node_state, "scaffold_band", None) or "neutral")
    density = effective_density(
        int(getattr(course, "intent_density", 3) or 3), accessibility
    )
    role = getattr(profile, "role_title", None)
    sector = getattr(profile, "sector", None)
    preferences = preference_bucket(
        getattr(profile, "learning_preferences", None),
        tts_available=tts_is_available(settings.TTS_PROVIDER),
    )
    accessibility_key = accessibility_bucket(accessibility)
    selection_execution = (
        settings.RUNTIME_SELECTION_EXECUTION
        if settings.RUNTIME_COMPONENT_SHORTLIST
        else SelectionExecution.OFF
    )
    selection_strategy = settings.RUNTIME_SELECTION_STRATEGY
    selection_policy_key = live_cache_fragment(
        selection_execution,
        selection_strategy,
    )
    generation_key = generation_policy_key()
    history = longitudinal_history or project_longitudinal_history(
        [], nodes_completed=nodes_completed
    )

    key = build_cache_key(
        node_id=node.id,
        schema_version=int(getattr(course, "schema_version", 1) or 1),
        preset=getattr(profile, "preset", "standard"),
        experience_level=getattr(profile, "experience_level", "unknown"),
        scaffold_band=band,
        effective_density=density,
        backend=backend or settings.RENDER_BACKEND,
        model=model_key,
        # Both halves of "which instructions produced this": the prompt module's own
        # version and the generated catalogue the model was taught. Either one changing
        # must invalidate the render, and the two are owned by different files.
        prompt_version=current_prompt_version(),
        role_title=role,
        sector=sector,
        vector_bucket=bucket,
        preference_bucket=preferences,
        accessibility_bucket=accessibility_key,
        knowledge_pack_key=knowledge_pack_key,
        selection_policy_key=selection_policy_key,
        generation_policy_key=generation_key,
        longitudinal_decision_digest=history.decision_digest,
    )
    key = f"{current_render_safety_prefix()}{key}"
    if is_preview:
        salt = preview_salt or uuid.uuid4().hex[:12]
        key = f"{PREVIEW_KEY_PREFIX}:{salt}:{key}"
    elif refresh_salt:
        key = f"{REFRESH_KEY_PREFIX}:{refresh_salt}:{key}"

    return RenderKey(
        cache_key=key,
        effective_density=density,
        vector_bucket=bucket,
        preference_bucket=preferences,
        accessibility_bucket=accessibility_key,
        knowledge_pack_key=knowledge_pack_key,
        scaffold_band=band,
        role_bucket=role_bucket(role, sector),
        model_key=model_key,
        calibrating=nodes_completed < CALIBRATION_NODES,
        is_preview=is_preview,
        personalization_revision=int(
            getattr(profile, "personalization_revision", 0) or 0
        ),
        selection_policy_key=selection_policy_key,
        generation_policy_key=generation_key,
        selection_strategy=_plain(selection_strategy),
        selection_execution=_plain(selection_execution),
        longitudinal_decision_digest=history.decision_digest,
        longitudinal_history=history,
    )


# --------------------------------------------------------------------------------------
# In-flight registry: what makes cancellation (§9.1) and "is it still generating?" possible
# --------------------------------------------------------------------------------------


@dataclass
class InFlight:
    """One running generation. Process-local, like ``src/core/sse.py`` — same single-worker
    assumption, documented in §9.2, and the same migration path (LISTEN/NOTIFY) when that
    changes."""

    request_id: str
    user_id: uuid.UUID
    node_id: uuid.UUID
    task: asyncio.Task | None = None


_INFLIGHT: dict[tuple[uuid.UUID, uuid.UUID], InFlight] = {}


def in_flight_for(user_id: uuid.UUID, node_id: uuid.UUID) -> InFlight | None:
    """The generation currently running for this ``(user, node)``, if any."""
    entry = _INFLIGHT.get((user_id, node_id))
    if entry is None:
        return None
    if entry.task is not None and entry.task.done():
        _INFLIGHT.pop((user_id, node_id), None)
        return None
    return entry


def owner_of_request(request_id: str) -> uuid.UUID | None:
    """Which learner a ``request_id`` belongs to, while its render is still running.

    Used by the SSE route so a caller cannot attach to somebody else's stream. It is a
    *narrowing*, not the whole guarantee: once the render finishes the entry is gone and the
    channel is silent, and ``request_id`` is 128 bits of ``uuid4`` to begin with.
    """
    for entry in _INFLIGHT.values():
        if entry.request_id == request_id:
            return entry.user_id
    return None


def register_in_flight(entry: InFlight) -> None:
    _INFLIGHT[(entry.user_id, entry.node_id)] = entry


def forget_in_flight(user_id: uuid.UUID, node_id: uuid.UUID) -> None:
    _INFLIGHT.pop((user_id, node_id), None)


def cancel_in_flight(user_id: uuid.UUID, node_id: uuid.UUID) -> bool:
    """Cancel the render in flight for this ``(user, node)``. ``True`` if there was one.

    §9.1: when the probe verdict finally comes out ``mastered``, the render fired in the
    background after item A is thrown away. The cost of the wasted tokens is accepted in
    exchange for zero latency in the frequent case; what must not happen is the learner
    being pinned to a screen for a node they just skipped.
    """
    entry = in_flight_for(user_id, node_id)
    if entry is None:
        return False
    if entry.task is not None and not entry.task.done():
        entry.task.cancel()
    forget_in_flight(user_id, node_id)
    return True


# --------------------------------------------------------------------------------------
# What a route may serialize
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ServedRender:
    """The render as the client may see it. **No ``answer_key`` field exists here.**

    ``program`` is the canonical dialect re-serialized from the validated ``UISpec``
    (``node_renders.dialect``), never the model's own bytes: that text is derived from a
    customer document and handing it to a reactive runtime would walk past every barrier at
    once. ``ui_spec`` stays server-side as the audit evidence it is (§3.4).
    """

    render_id: uuid.UUID
    node_id: uuid.UUID
    ui_format: str
    status: str
    backend: str
    cached: bool
    program: str

    @classmethod
    def of(cls, render: NodeRender, *, cached: bool) -> ServedRender:
        return cls(
            render_id=render.id,
            node_id=render.node_id,
            ui_format=_plain(render.ui_format),
            status=_plain(render.status),
            backend=render.backend,
            cached=cached,
            program=render.dialect or "",
        )


@dataclass(frozen=True)
class RenderRequest:
    """Result of ``POST /nodes/{id}/render``: ``202 {request_id, cached}``."""

    request_id: str
    cached: bool
    render_id: uuid.UUID | None = None


class NodeRenderService:
    """Everything around the graph: the cache, the pin, the view log, cancellation.

    The graph itself is driven by ``src/agents/runtime/runner.py``, imported lazily inside
    :meth:`request_render` so this module stays importable (and unit-testable) without
    LangGraph in the picture.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.renders = NodeRenderRepository(db)
        self.views = NodeRenderViewRepository(db)
        self.states = LearnerNodeStateRepository(db)

    # -- guards -----------------------------------------------------------------

    @staticmethod
    def assert_reviewed(node: CourseNode) -> None:
        """``409 node_not_reviewed`` for a node no human has signed off (§3.2, §11.3)."""
        if node.reviewed_at is None:
            raise ConflictError(
                "This node has not been reviewed by a person yet, so it cannot be served.",
                field=NODE_NOT_REVIEWED,
            )

    # -- context ----------------------------------------------------------------

    async def org_settings(self, org_id: uuid.UUID) -> dict[str, Any]:
        """Provider overrides carried by the organization row."""
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = result.scalar_one_or_none()
        if org is None:
            org = (
                await self.db.execute(select(Organization).limit(1))
            ).scalar_one_or_none()
        return dict(org.settings) if org and org.settings else {}

    # -- level 2: the pinned render --------------------------------------------

    async def pinned_render(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID
    ) -> NodeRender | None:
        """The render fixed for this ``(user, node)``, without recomputing anything.

        This is what ``GET /nodes/{id}/render`` answers with. It is also what makes a
        revisit to an already-seen node serve the last render rather than a new one (§5.5).
        """
        state = await self.states.get_by_user_and_node(user_id, node_id)
        if state is None or not state.render_pinned or state.active_render_id is None:
            return None
        render = await self.renders.get_by_id(state.active_render_id)
        if render is None or render.status not in (
            NodeRenderStatus.READY,
            NodeRenderStatus.FALLBACK,
        ):
            return None
        if not cache_key_uses_current_screen_contract(render.cache_key):
            return None
        return render

    async def pin(
        self,
        *,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        render: NodeRender,
        personalization_revision: int = 0,
    ) -> LearnerNodeState | None:
        """Fix ``active_render_id`` and ``render_pinned`` (§3.3 "Vision A")."""
        current_revision = (
            await self.db.execute(
                select(LearnerProfile.personalization_revision).where(
                    LearnerProfile.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        # Real SQL returns the selected scalar. Lightweight repository/session fakes may
        # return the profile object itself; normalising both shapes keeps this race guard
        # at the service boundary instead of coupling every test double to SQLAlchemy's
        # scalar projection internals.
        current_revision = getattr(
            current_revision, "personalization_revision", current_revision
        )
        if int(current_revision or 0) != int(personalization_revision):
            return None
        state = await self.states.get_or_create(user_id=user_id, node_id=node_id)
        state.active_render_id = render.id
        state.render_pinned = True
        state.pinned_personalization_revision = int(personalization_revision)
        await self.db.flush()
        return state

    async def serve(
        self, *, user_id: uuid.UUID, render: NodeRender, cached: bool
    ) -> ServedRender:
        """Project the render for the wire **and** record the first view (§2.1).

        The view row is the only place that can answer "who saw this", because the render
        row is shared by everybody in the bucket.
        """
        await self.views.record_first_view(
            user_id=user_id, render_id=render.id, node_id=render.node_id
        )
        return ServedRender.of(render, cached=cached)

    async def history(
        self, *, user_id: uuid.UUID, node_id: uuid.UUID, limit: int = 20
    ) -> list[NodeRender]:
        """"Ver la version anterior" (§5.5): the renders **this** learner was served."""
        render_ids = await self.views.render_ids_for_node(
            user_id=user_id, node_id=node_id, limit=limit
        )
        rows = await self.renders.history_for_node(
            node_id=node_id, render_ids=render_ids
        )
        return list(rows)

    async def answer_key_for(self, render: NodeRender) -> dict:
        """The one accessor. Used by grading, never by a response model (§5.2 rule 5)."""
        return dict(render.answer_key or {})

    # -- level 1: the shared cache, and starting the graph ----------------------

    async def request_render(
        self,
        *,
        user: Any,
        node: CourseNode,
        course: Course,
        force: bool = False,
        preview: bool = False,
    ) -> RenderRequest:
        """``POST /nodes/{node_id}/render``.

        Order of decisions, and why:

        1. **Already pinned and not forced** -> return it. Cheapest level, and the one that
           guarantees spatial stability.
        2. **Already generating** -> return the same ``request_id``. Two tabs must not start
           two generations of the same screen.
        3. **Cache hit on ``cache_key``, and not forced** -> pin it and answer
           ``cached=True``. Zero tokens.
        4. Otherwise spawn the graph and answer ``202`` with a fresh ``request_id``.

        A preview never pins and never hits the cache (§11.3).

        ``force`` skips step 3 *entirely*, not just the pin: the key is a pure function of
        the node and the learner's profile, and neither moves when the learner presses
        "Actualizar esta leccion", so reading the cache with it would return the render they
        asked to replace and the button would be decoration. When the base key is already
        occupied by something servable, the forced run gets a salted key of its own so it
        writes a new row instead of overwriting the one the rest of the bucket is reading.
        """
        from src.agents.runtime.runner import spawn_node_render  # local: avoids a cycle

        self.assert_reviewed(node)

        if not preview and not force:
            pinned = await self.pinned_render(user_id=user.id, node_id=node.id)
            if pinned is not None:
                return RenderRequest(
                    request_id="", cached=True, render_id=pinned.id
                )

        if not preview:
            running = in_flight_for(user.id, node.id)
            if running is not None and not force:
                return RenderRequest(request_id=running.request_id, cached=False)
            if running is not None and force:
                cancel_in_flight(user.id, node.id)

        key = await self.render_key_for(
            user=user, node=node, course=course, is_preview=preview
        )

        if not preview and not force:
            hit = await self.renders.find_cached(key.cache_key)
            if hit is not None:
                await self.pin(
                    user_id=user.id,
                    node_id=node.id,
                    render=hit,
                    personalization_revision=key.personalization_revision,
                )
                await self.db.commit()
                return RenderRequest(request_id="", cached=True, render_id=hit.id)

        if not preview and force:
            # The row under the base key is not read as a cache hit here — it is only
            # checked for *existence*. ``cache_key`` is UNIQUE, so reusing it would make
            # ``claim`` either return the served row untouched (and the graph would rewrite
            # what other learners have open) or resurrect a failed one. A salt keeps the
            # shared row, and this learner's "version anterior", exactly as they are.
            occupied = await self.renders.get_by_cache_key(key.cache_key)
            if occupied is not None and occupied.status in SERVABLE_STATUSES:
                key = await self.render_key_for(
                    user=user, node=node, course=course, refresh=True
                )

        request_id = uuid.uuid4().hex
        state: dict[str, Any] = {
            "request_id": request_id,
            "org_id": str(node.org_id),
            "user_id": str(user.id),
            "course_id": str(node.course_id),
            "node_id": str(node.id),
            "cache_key": key.cache_key,
            "backend": settings.RENDER_BACKEND,
            "is_preview": preview,
            "schema_version": int(course.schema_version or 1),
            "effective_density": key.effective_density,
            "scaffold_band": key.scaffold_band,
            "knowledge_pack_key": key.knowledge_pack_key,
            "selection_strategy": key.selection_strategy,
            "selection_execution": key.selection_execution,
            "longitudinal_decision_digest": key.longitudinal_decision_digest,
            "longitudinal_history": {
                **asdict(key.longitudinal_history),
                "support_level": key.longitudinal_history.support_level.value,
            },
            "retry_count": 0,
            "validation_errors": [],
            "answer_key": {},
            "error": None,
            "current_step": "pending",
        }
        task = spawn_node_render(state)
        if not preview:
            register_in_flight(
                InFlight(
                    request_id=request_id,
                    user_id=user.id,
                    node_id=node.id,
                    task=task,
                )
            )
        return RenderRequest(request_id=request_id, cached=False)

    async def render_key_for(
        self,
        *,
        user: Any,
        node: CourseNode,
        course: Course,
        is_preview: bool = False,
        refresh: bool = False,
    ) -> RenderKey:
        """The pre-graph key: same pure function ``load_context`` uses (§4.2)."""
        from src.agents.runtime.router import runtime_model_key
        from src.repositories.learner_profile_repo import LearnerProfileRepository

        profile = await LearnerProfileRepository(self.db).get_by_user(user.id)
        node_state = await self.states.get_by_user_and_node(user.id, node.id)
        org_settings = await self.org_settings(node.org_id)
        from src.knowledge_pack.runtime_selection import load_runtime_knowledge

        pack = await load_runtime_knowledge(
            self.db,
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=dict(user.accessibility or {}),
        )
        events = await LearningEventRepository(
            self.db
        ).recent_longitudinal_didact_events(
            user_id=user.id,
            exclude_node_id=node.id,
        )
        history = project_longitudinal_history(
            events,
            nodes_completed=int(getattr(profile, "nodes_completed", 0) or 0),
        )
        return build_render_key(
            node=node,
            course=course,
            profile=profile,
            node_state=node_state,
            accessibility=dict(user.accessibility or {}),
            model_key=runtime_model_key(org_settings),
            is_preview=is_preview,
            refresh_salt=uuid.uuid4().hex[:12] if refresh and not is_preview else None,
            knowledge_pack_key=pack.cache_fragment if pack else "",
            longitudinal_history=history,
        )

    # -- cancellation (§9.1) ----------------------------------------------------

    @staticmethod
    def cancel(user_id: uuid.UUID, node_id: uuid.UUID) -> bool:
        return cancel_in_flight(user_id, node_id)


__all__ = [
    "NODE_NOT_REVIEWED",
    "PREVIEW_KEY_PREFIX",
    "REFRESH_KEY_PREFIX",
    "InFlight",
    "NodeRenderService",
    "RenderKey",
    "RenderRequest",
    "ServedRender",
    "build_render_key",
    "cancel_in_flight",
    "forget_in_flight",
    "generation_policy_key",
    "in_flight_for",
    "owner_of_request",
    "register_in_flight",
]
