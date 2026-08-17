"""The runtime employee surface (§11.3): node list, probe, render, answer, hint, feedback.

A course that is not dynamic 404s: it has no nodes, and saying so with a 403 would leak
the existence of a surface that does not apply.

Where the wiring left dangling by other batches gets connected:

* ``LearnerProfileService.record_events`` -> ``POST /nodes/{id}/events``.
* ``LearnerProfileService.apply_signals`` -> ``/answer`` and ``/feedback``, with
  ``NodeSignalContext.unmastered_prerequisites`` filled from
  ``LearnerNodeStateRepository.unmastered_prerequisites`` (the LEFT-join query B4 shipped
  without a caller).
* ``LearnerProfileService.increment_nodes_completed`` -> only on the ``learning -> mastered``
  transition (rule 6 of §7.3), never on a probe skip.
* ``LearnerProfileService.refresh_format_vector`` -> **only when a node closes**, not per
  event batch. That is a decision, and the reason is arithmetic: recomputing is
  ``O(events in the 30-day window)`` and the vector is *read* in exactly one place —
  ``decide_formato``, which runs when a node opens. Refreshing on every batch would repeat
  the same scan dozens of times per node to produce a value nobody reads in between. A node
  closing is both the moment the vector has new information and the moment before the next
  node will consult it.
"""

from __future__ import annotations

import uuid
import hashlib
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select

from src.agents.runtime.errors import node_channel
from src.agents.runtime.nodes import load_source_context
from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from src.core.sse import format_sse, subscribe
from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.deps.llm import get_optional_llm_service
from src.llm.client import LLMService, resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm
from src.models import (
    Course,
    CourseNode,
    LearnerNodeState,
    NodeFeedback,
    NodeRender,
    Organization,
    UserRole,
)
from src.render.prompt import load_artifact
from src.render.spec import UI_SPEC_VERSION
from src.repositories.audit_log_repo import AuditLogRepository, node_subject
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.enrollment_repo import EnrollmentRepository
from src.repositories.exercise_repo import ExerciseRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.learning_event_repo import EventInput, LearningEventRepository
from src.repositories.node_attempt_repo import NodeAttemptRepository
from src.repositories.node_probe_repo import NodeProbeRepository
from src.repositories.node_render_repo import SERVABLE_STATUSES, NodeRenderRepository
from src.repositories.node_render_view_repo import NodeRenderViewRepository
from src.repositories.skill_repo import SkillRepository
from src.schemas.media import MediaArtifactAccepted
from src.schemas.node import (
    DEFAULT_ESTIMATED_MINUTES,
    NodeAnswerRequest,
    NodeAttemptResult,
    NodeEventsRequest,
    NodeFeedbackRequest,
    NodeHintRequest,
    NodeHintResult,
    NodeListRead,
    NodeModalityRequest,
    NodeRenderAccepted,
    NodeRenderHistoryItem,
    NodeRenderHistoryRead,
    NodeRenderRead,
    NodeRenderRequest,
    NodeStateRead,
    NodeSummaryRead,
    NodeWaiveRequest,
    ProbeAnswerRequest,
    ProbeAnswerResult,
    UIKitComponentRead,
    UIKitRead,
)
from src.schemas.probe import ProbeSessionRead
from src.services.course_delivery import resolve_delivery
from src.services.enrollment_service import EnrollmentService
from src.services.learner_profile_service import (
    LearnerProfileService,
    NodeSignalContext,
)
from src.services.mastery_service import (
    HINT_LIMIT,
    MASTERED,
    NEEDS_REVIEW,
    evaluate_course_completion,
    may_offer_hint,
)
from src.services.mastery_evidence_service import MasteryEvidenceService
from src.services.node_grading import (
    classify_error,
    content_for,
    grade_item,
    item_type_of,
)
from src.services.node_render_service import (
    NodeRenderService,
    ServedRender,
    in_flight_for,
    owner_of_request,
)
from src.services.probe_service import ProbeService
from src.services.runtime_modalities import RuntimeModality, request_runtime_modality
from src.services.skill_service import SkillService

router = APIRouter(
    prefix="/nodes",
    tags=["Nodes"],
)

#: ``GET /courses/{course_id}/nodes`` lives on its own router because its prefix belongs to
#: the v1 ``courses`` surface. Registered after ``courses`` in ``main.py``; no path collides.
course_nodes_router = APIRouter(
    prefix="/courses",
    tags=["Nodes"],
)

#: ``GET /render-kit`` (§11.3). Its own router because the path has no ``/nodes`` prefix
#: and it is the one route here that reads no per-learner data at all.
render_kit_router = APIRouter(
    prefix="/render-kit",
    tags=["Nodes"],
)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

#: Events after which the render stream has nothing left to say.
_TERMINAL_EVENTS = {"ui_done", "node_skipped", "error"}


def _node_answer_digest(body: NodeAnswerRequest) -> str:
    canonical = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Small shared reads.
#
# Two of these touch ``node_feedback`` and ``user_skills`` with a plain ``select``. Neither
# table was allocated a repository in this batch's file list (§13 B5) and inventing one
# outside the plan is a bigger deviation than two three-line queries next to their only
# caller; both are pure reads with no business logic.
# --------------------------------------------------------------------------------------


async def _org_settings(db: DBSession) -> dict[str, Any]:
    result = await db.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    return dict(org.settings) if org and org.settings else {}


async def get_runtime_fast_llm(db: DBSession) -> LLMService | None:
    """The ``runtime_fast`` tier, used only as the probe's last-resort generator (§7.1).

    ``None`` when nothing is configured: the probe then refuses to generate rather than
    attempting a network call. Goes through ``maybe_fixture_llm`` like every other
    construction site, so the whole flow runs with ``LLM_MODEL=fixture/local``.
    """
    try:
        return maybe_fixture_llm(
            resolve_llm_config(await _org_settings(db), purpose="runtime_fast")
        )
    except Exception:  # noqa: BLE001 - a missing model must degrade, not 500
        return None


RuntimeFastLLMDep = Annotated[LLMService | None, Depends(get_runtime_fast_llm)]
OptionalEvalLLMDep = Annotated[
    LLMService | None, Depends(get_optional_llm_service)
]


async def _user_skill_level(
    db: DBSession, user_id: uuid.UUID, skill_id: uuid.UUID | None
) -> Any:
    """``user_skills.level`` for the node's skill — the mastery prior of §7.1.

    Delegates to ``SkillService.level_for_skill`` (B11), which owns both halves of the
    ``mastery <-> user_skills`` bridge. It used to be a local ``select`` here because
    B5 had no owner for it; now that the write half exists in ``skill_service.py``, the
    read living anywhere else would guarantee the two drift.
    """
    return await SkillService(SkillRepository(db)).level_for_skill(
        user_id=user_id, skill_id=skill_id
    )


async def _feedback_difficulty(
    db: DBSession, user_id: uuid.UUID, node_id: uuid.UUID
) -> str | None:
    """The difficulty this learner reported for this node, if any (§3.3 signals)."""
    query = select(NodeFeedback.difficulty).where(
        NodeFeedback.user_id == user_id, NodeFeedback.node_id == node_id
    )
    return (await db.execute(query)).scalars().first()


async def _assert_enrolled(db: DBSession, user: Any, course_id: uuid.UUID) -> None:
    """The v1 rule of ``GET /courses/{id}`` (``routes/courses.py``), applied to v2.

    Org scoping is **not** an access rule. ``CourseNodeRepository.get_scoped`` and
    ``CourseRepository.get_scoped`` only prove the row belongs to the caller's
    organisation, which every colleague shares; without this check any authenticated
    employee could enumerate the node graph of a course nobody assigned them, open its
    probes, and make ``POST /nodes/{id}/render`` spend real tokens on a node they were
    never meant to see. v1 forbids exactly that over the same data.

    Admins are exempt for the same reason they are in v1: the preview of §11.3 and the
    waiver of §7.4 are creator tools, and nobody enrolls a creator in the course they are
    reviewing.
    """
    if _is_admin(user):
        return
    enrollment = await EnrollmentRepository(db).get_by_user_and_course(user.id, course_id)
    if enrollment is None:
        raise ForbiddenError("You are not enrolled in this course")


async def _load_dynamic_node(
    db: DBSession, user: Any, node_id: uuid.UUID
) -> tuple[CourseNode, Course]:
    """Fetch a node of a **dynamic** course in the caller's org, or 404.

    ``resolve_delivery`` is the single decision point (course opted in + schema
    validated). A node of a static course is not "forbidden", it does not exist as
    far as this surface is concerned.

    Enrollment is checked here rather than in each route because *every* node route goes
    through this function: a route added later inherits the gate instead of forgetting it.
    """
    node = await CourseNodeRepository(db).get_scoped(node_id, user.org_id)
    if node is None or node.archived:
        raise NotFoundError("course_nodes", str(node_id))
    course = await CourseRepository(db).get_by_id(node.course_id)
    if course is None or resolve_delivery(course) != "dynamic":
        raise NotFoundError("course_nodes", str(node_id))
    await _assert_enrolled(db, user, course.id)
    return node, course


def _profile_service(db: DBSession) -> LearnerProfileService:
    return LearnerProfileService(
        LearnerProfileRepository(db), LearningEventRepository(db)
    )


def _probe_service(
    db: DBSession, llm: LLMService | None, open_llm: LLMService | None
) -> ProbeService:
    return ProbeService(
        probe_repo=NodeProbeRepository(db),
        attempt_repo=NodeAttemptRepository(db),
        state_repo=LearnerNodeStateRepository(db),
        exercise_repo=ExerciseRepository(db),
        llm=llm,
        open_llm=open_llm,
    )


def _enrollment_service(db: DBSession) -> EnrollmentService:
    """The §7.5 closer (B11).

    Built here rather than injected because it is used by three routes and its only
    v2 entry point is ``close_dynamic_if_mastered``, which is gated on
    ``resolve_delivery`` internally — so wiring it in cannot reach a static course.
    """
    return EnrollmentService(
        EnrollmentRepository(db), CourseRepository(db), ExerciseRepository(db)
    )


def _is_admin(user: Any) -> bool:
    role = getattr(user.role, "value", user.role)
    return str(role) == UserRole.ADMIN.value


# --------------------------------------------------------------------------------------
# GET /courses/{course_id}/nodes
# --------------------------------------------------------------------------------------
@course_nodes_router.get("/{course_id}/nodes", response_model=NodeListRead)
async def list_course_nodes(
    user: CurrentUser, db: DBSession, course_id: uuid.UUID
) -> NodeListRead:
    """The node list with per-learner state, locks and the completion rule of §7.5."""
    course = await CourseRepository(db).get_scoped(course_id, user.org_id)
    if course is None or resolve_delivery(course) != "dynamic":
        raise NotFoundError("courses", str(course_id))
    await _assert_enrolled(db, user, course.id)

    node_repo = CourseNodeRepository(db)
    nodes = list(await node_repo.list_for_course(course_id, include_archived=False))
    node_ids = [node.id for node in nodes]
    prerequisites = await node_repo.prerequisites_for(node_ids)
    states = await LearnerNodeStateRepository(db).states_for_nodes(
        user_id=user.id, node_ids=node_ids
    )

    def state_value(node_id: uuid.UUID) -> str:
        row = states.get(node_id)
        if row is None:
            return "not_started"
        return str(getattr(row.state, "value", row.state))

    rows: list[NodeSummaryRead] = []
    for node in nodes:
        row = states.get(node.id)
        unmet = [
            prerequisite_id
            for prerequisite_id in prerequisites.get(node.id) or []
            # A prerequisite that is not in this course's active set (archived, or moved)
            # cannot keep anybody locked: there would be no way to ever clear it.
            if prerequisite_id in states or prerequisite_id in node_ids
            if state_value(prerequisite_id) != MASTERED
        ]
        current = state_value(node.id)
        rows.append(
            NodeSummaryRead(
                id=node.id,
                title=node.title,
                summary=node.summary,
                criticality=str(getattr(node.criticality, "value", node.criticality)),
                position=node.position,
                state=current,
                mastery=float(getattr(row, "mastery", 0.0) or 0.0),
                locked=bool(unmet),
                locked_by=unmet,
                needs_practice=current == NEEDS_REVIEW,
                estimated_minutes=int(
                    node.estimated_minutes or DEFAULT_ESTIMATED_MINUTES
                ),
            )
        )

    completion = evaluate_course_completion(
        [
            _CompletionRow(
                node_id=node.id,
                criticality=node.criticality,
                archived=bool(node.archived),
                state=state_value(node.id),
                mastery=float(getattr(states.get(node.id), "mastery", 0.0) or 0.0),
            )
            for node in nodes
        ]
    )
    return NodeListRead(
        course_id=course.id,
        delivery_mode=str(getattr(course.delivery_mode, "value", course.delivery_mode)),
        schema_version=int(course.schema_version or 1),
        nodes=rows,
        can_complete=completion.can_complete,
        blocked_by=list(completion.blocked_by),
        progress_percent=completion.progress_percent,
    )


class _CompletionRow:
    """Structural stand-in for ``NodeProgressLike`` (§7.5). Deliberately not the ORM row:
    the rule is over ``(node, learner state)`` and neither table holds both halves."""

    __slots__ = ("archived", "criticality", "mastery", "node_id", "state")

    def __init__(
        self,
        *,
        node_id: uuid.UUID,
        criticality: Any,
        archived: bool,
        state: str,
        mastery: float,
    ) -> None:
        self.node_id = node_id
        self.criticality = criticality
        self.archived = archived
        self.state = state
        self.mastery = mastery


# --------------------------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------------------------
@router.post("/{node_id}/probe", response_model=ProbeSessionRead)
async def start_probe(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    llm: RuntimeFastLLMDep,
    open_llm: OptionalEvalLLMDep,
    reprobe: bool = Query(default=False),
) -> ProbeSessionRead:
    """Open the pre-assessment — which **is** the productive wait of §9.1.

    ``ProbeSessionRead.from_session`` is the only sanctioned projection: it enumerates what
    may travel, so the answer key cannot leak even if a column is added later.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    service = _probe_service(db, llm, open_llm)
    profile = await LearnerProfileRepository(db).get_by_user(user.id)
    skill_level = await _user_skill_level(db, user.id, node.skill_id)

    source_context = ""
    if not node.probe_items:
        # Only pay for the source read when the items are not pre-generated (§7.1 source 3).
        source_context = await load_source_context(db, node, user.org_id)

    session = await service.start_probe(
        user_id=user.id,
        node=node,
        schema_version=int(course.schema_version or 1),
        profile=profile,
        user_skill_level=skill_level,
        source_context=source_context,
        reprobe=reprobe,
    )
    await db.commit()
    return session.to_read()


@router.post("/{node_id}/probe/answer", response_model=ProbeAnswerResult)
async def answer_probe(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    body: ProbeAnswerRequest,
    llm: RuntimeFastLLMDep,
    open_llm: OptionalEvalLLMDep,
) -> ProbeAnswerResult:
    """Grade one probe item; close the probe when the last required one lands.

    The one thing this route adds on top of ``ProbeService``: when the verdict finally comes
    out ``mastered``, the render that ``render_hint="prefetch"`` started in the background is
    **cancelled** (§9.1). Without it the learner would be pinned to a screen for a node they
    just skipped, and the tokens would be spent anyway.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    probe_repo = NodeProbeRepository(db)
    probe = await probe_repo.get_by_id(body.probe_id)
    if probe is None or probe.user_id != user.id or probe.node_id != node.id:
        raise NotFoundError("node_probes", str(body.probe_id))

    service = _probe_service(db, llm, open_llm)
    profile = await LearnerProfileRepository(db).get_by_user(user.id)
    skill_level = await _user_skill_level(db, user.id, node.skill_id)

    outcome = await service.submit_answer(
        user_id=user.id,
        node=node,
        probe=probe,
        item_id=body.item_id,
        answer=body.answer,
        profile=profile,
        user_skill_level=skill_level,
        latency_ms=body.latency_ms,
    )

    if outcome.verdict == MASTERED:
        # A node the probe skipped still closes the node, so it can also be the last
        # critical node of the course (§7.5). No ``user_skills`` write here on purpose:
        # ``probe_score`` is two or three items answered cold, which is enough to skip a
        # node and not enough to certify a competence to the whole organisation.
        await _enrollment_service(db).close_dynamic_if_mastered(
            course=course, user_id=user.id
        )
    await db.commit()

    if outcome.verdict == MASTERED:
        NodeRenderService.cancel(user.id, node.id)

    return ProbeAnswerResult(
        item_id=outcome.item_id,
        score=outcome.score,
        passed=outcome.passed,
        verdict=outcome.verdict,
        estimate=outcome.estimate,
        next_item_id=outcome.next_item_id,
        render_hint=outcome.render_hint,
        feedback=outcome.feedback,
    )


# --------------------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------------------
@router.post("/{node_id}/render", response_model=NodeRenderAccepted, status_code=202)
async def request_render(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    body: NodeRenderRequest | None = None,
) -> NodeRenderAccepted:
    """``202 {request_id, cached}``. ``409 node_not_reviewed`` for an unreviewed node.

    ``preview: true`` is admin-only and is what makes ``shadow`` mode safe: it generates with
    the admin's profile, pins nothing, and persists ``is_preview = true`` so the row is
    excluded from the cache (§3.4).
    """
    payload = body or NodeRenderRequest()
    node, course = await _load_dynamic_node(db, user, node_id)
    if payload.preview and not _is_admin(user):
        raise ForbiddenError("Only an admin can generate a preview render.")

    service = NodeRenderService(db)
    result = await service.request_render(
        user=user,
        node=node,
        course=course,
        force=payload.force,
        preview=payload.preview,
    )
    await db.commit()
    return NodeRenderAccepted(
        request_id=result.request_id,
        cached=result.cached,
        render_id=result.render_id,
    )


@router.post(
    "/{node_id}/modalities/{modality}",
    response_model=MediaArtifactAccepted,
    status_code=202,
)
async def request_node_modality(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    modality: RuntimeModality,
    body: NodeModalityRequest | None = None,
) -> MediaArtifactAccepted:
    """Prepare audio or video when the learner activates it in the node player.

    This deliberately bypasses the course-overview authoring policy: it is an enrolled
    learner delivery route, protected by the same dynamic-node gate as the web render.
    The returned media row is an internal async result/cache, not a course definition.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    payload = body or NodeModalityRequest()
    artifact, _created = await request_runtime_modality(
        db,
        course=course,
        node=node,
        modality=modality,
        language=payload.language,
    )
    return MediaArtifactAccepted(
        artifact_id=artifact.id,
        status=str(getattr(artifact.status, "value", artifact.status)),
    )


@router.get("/{node_id}/render")
async def get_render(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID
) -> Any:
    """The **pinned** render. Recomputes nothing (§5.5).

    This is the mechanism behind the "Estable" row of the spatial-stability table: the key is
    not recalculated here, so answering an item cannot change the screen and a TanStack
    refetch on window focus returns the same bytes. ``202`` while there is nothing pinned
    yet; only ``POST …/render {"force": true}`` repins.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    service = NodeRenderService(db)
    service.assert_reviewed(node)

    render = await service.pinned_render(
        user_id=user.id, node_id=node.id, node=node, course=course, user=user
    )
    if render is None:
        running = in_flight_for(user.id, node.id)
        return JSONResponse(
            status_code=202,
            content={
                "status": "generating" if running else "pending",
                "request_id": running.request_id if running else None,
            },
        )

    served = await service.serve(user_id=user.id, render=render, cached=True)
    await db.commit()
    return NodeRenderRead.of(served)


@router.get("/{node_id}/renders", response_model=NodeRenderHistoryRead)
async def list_renders(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID
) -> NodeRenderHistoryRead:
    """"Ver la version anterior" (§5.5): the renders **this learner** was served.

    Sourced from ``node_render_views``, never from ``node_renders`` alone: the render table
    is shared by everybody in the bucket, so "any version of this node that exists" would
    list screens this person never saw.
    """
    node, _course = await _load_dynamic_node(db, user, node_id)
    renders = await NodeRenderService(db).history(user_id=user.id, node_id=node.id)
    return NodeRenderHistoryRead(
        renders=[
            NodeRenderHistoryItem(
                render_id=render.id,
                created_at=render.created_at,
                ui_format=str(getattr(render.ui_format, "value", render.ui_format)),
                status=str(getattr(render.status, "value", render.status)),
            )
            for render in renders
        ]
    )


@router.get("/{node_id}/renders/{render_id}", response_model=NodeRenderRead)
async def get_render_version(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID, render_id: uuid.UUID
) -> NodeRenderRead:
    """One version out of the list above — what makes "Ver la version anterior" real.

    Without this route the version list was a list of dead links: the client could only
    reopen a version it still happened to be holding in memory from the current session,
    so a reload emptied the feature. The authorization is the ``node_render_views`` row,
    not the org: ``node_renders`` is shared by the whole bucket, so "a render of a node in
    my organisation" would hand a learner screens they were never served. A row in
    ``node_render_views`` is the record that *this* person was shown *this* render (§2.1),
    which is exactly the set the history endpoint lists.

    Nothing is pinned and no view is recorded: reopening an old version is looking back at
    something already seen, not being served it, and moving ``first_seen_at`` would corrupt
    the evidence a certificate is justified with.
    """
    node, _course = await _load_dynamic_node(db, user, node_id)
    render = await NodeRenderRepository(db).get_scoped(render_id, user.org_id)
    if render is None or render.node_id != node.id or render.status not in SERVABLE_STATUSES:
        raise NotFoundError("node_renders", str(render_id))
    seen = await NodeRenderViewRepository(db).get(user_id=user.id, render_id=render.id)
    if seen is None:
        raise NotFoundError("node_renders", str(render_id))
    return NodeRenderRead.of(ServedRender.of(render, cached=True))


@router.get("/{node_id}/render/stream")
async def stream_render(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    request_id: str = Query(...),
) -> StreamingResponse:
    """SSE for one render request (§9.2). Channel: ``node:{request_id}``.

    Events: ``render_step``, ``ui_format``, ``ui_block``, ``ui_done``, ``node_skipped``,
    ``error``. The stream closes on the first terminal one.
    """
    await _load_dynamic_node(db, user, node_id)
    owner = owner_of_request(request_id)
    if owner is not None and owner != user.id:
        # Somebody else's render is running under this id. 404 rather than 403: the request
        # id of another learner is not a resource this caller may know exists.
        raise NotFoundError("node_renders", request_id)
    channel = node_channel(request_id)

    async def event_stream() -> AsyncIterator[str]:
        async for event in subscribe(channel):
            yield format_sse(event["type"], event["data"])
            if event["type"] in _TERMINAL_EVENTS:
                break

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


# --------------------------------------------------------------------------------------
# Answer, hint
# --------------------------------------------------------------------------------------
@router.post("/{node_id}/answer", response_model=NodeAttemptResult)
async def answer_node_item(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    body: NodeAnswerRequest,
    open_llm: OptionalEvalLLMDep,
) -> NodeAttemptResult:
    """Grade one item of a served render and move the learner state (§7.3, §7.4).

    ``body.hints_used`` is read and discarded. The count that decides whether
    ``correct_answer`` is revealed comes from ``node_attempts.hints_used``, which only
    ``POST /nodes/{id}/hint`` increments — a number the client fills in cannot govern the
    revelation of the answer key.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    render, item_props, key_entry = await _resolve_item(
        db, user, node, body.render_id, body.item_id
    )

    attempts = NodeAttemptRepository(db)
    await attempts.lock_attempt(body.attempt_id)
    request_digest = _node_answer_digest(body)
    existing_attempt = await attempts.get_attempt(body.attempt_id)
    if existing_attempt is not None:
        if (
            existing_attempt.user_id != user.id
            or existing_attempt.node_id != node.id
            or existing_attempt.render_id != render.id
            or existing_attempt.item_id != body.item_id
            or existing_attempt.request_digest != request_digest
        ):
            raise ConflictError(
                "attempt_id is already associated with another answer",
                field="attempt_id",
            )
        existing_state = await LearnerNodeStateRepository(db).get_by_user_and_node(
            user.id, node.id
        )
        state_value = str(
            getattr(existing_state.state, "value", existing_state.state)
            if existing_state is not None
            else "learning"
        )
        reveal = bool(existing_attempt.passed) or int(existing_attempt.hints_used or 0) >= HINT_LIMIT
        return NodeAttemptResult(
            score=float(existing_attempt.score),
            passed=bool(existing_attempt.passed),
            feedback=existing_attempt.feedback,
            correct_answer=_correct_answer(key_entry) if reveal else None,
            mastery=float(getattr(existing_state, "mastery", 0.0) or 0.0),
            state=state_value,
            consecutive_correct=int(
                getattr(existing_state, "consecutive_correct", 0) or 0
            ),
            consecutive_failed=int(
                getattr(existing_state, "consecutive_failed", 0) or 0
            ),
            next=_next_action(passed=bool(existing_attempt.passed), state=state_value),
            show_worked_solution=False,
        )
    hints_used = await attempts.hints_used_for_item(
        user_id=user.id, node_id=node.id, item_id=body.item_id
    )
    item_failures = await attempts.count_failures_for_item(
        user_id=user.id, node_id=node.id, item_id=body.item_id
    )

    item_type = item_type_of(item_props)
    if item_type in ("practical_case", "dialogue") and open_llm is not None:
        from src.services.llm_grading import grade_open_answer

        result = await grade_open_answer(
            open_llm, item_type, content_for(item_props, key_entry), body.answer
        )
    else:
        result = grade_item(item_props, key_entry, body.answer)

    error_kind = None if result.passed else classify_error(item_props, key_entry, body.answer)

    await attempts.record(
        id=body.attempt_id,
        user_id=user.id,
        node_id=node.id,
        render_id=render.id,
        item_id=body.item_id,
        item_type=item_type,
        bloom_level=item_props.get("bloom_level"),
        answer=body.answer if isinstance(body.answer, dict) else {"answer": body.answer},
        score=result.score,
        passed=result.passed,
        # The server's count, not the client's. A new attempt inherits the hints already
        # spent on this item so the quota cannot be reset by answering again.
        hints_used=hints_used,
        latency_ms=body.latency_ms,
        feedback=result.feedback,
        request_digest=request_digest,
    )
    mastery_result = await MasteryEvidenceService(
        db,
        states=LearnerNodeStateRepository(db),
        profile_repository=LearnerProfileRepository(db),
    ).apply(
        user_id=user.id,
        node=node,
        course=course,
        score=result.score,
        passed=result.passed,
        error_kind=error_kind,
        hints_used=hints_used,
        prior_failures=item_failures,
    )
    state = mastery_result.state
    transition = mastery_result.transition
    await db.commit()

    reveal = result.passed or hints_used >= HINT_LIMIT
    state_value = str(getattr(state.state, "value", state.state))
    return NodeAttemptResult(
        score=result.score,
        passed=result.passed,
        feedback=result.feedback,
        correct_answer=_correct_answer(key_entry) if reveal else None,
        mastery=float(state.mastery or 0.0),
        state=state_value,
        consecutive_correct=int(state.consecutive_correct or 0),
        consecutive_failed=int(state.consecutive_failed or 0),
        next=_next_action(passed=result.passed, state=state_value),
        show_worked_solution=transition.show_worked_solution,
    )


@router.post("/{node_id}/hint", response_model=NodeHintResult)
async def get_hint(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID, body: NodeHintRequest
) -> NodeHintResult:
    """One hint, escalating, with ``attempt-before-hint`` and a hard cap of 3 (§7.4).

    ``409`` when there is no attempt yet — the whole point of the rule is that a hint follows
    an honest try — and ``409`` once the quota is spent, at which point the next failure shows
    the worked solution and the node moves to ``needs_review``.

    The hints are **deterministic**, derived from the item and its key. No LLM call: a hint is
    a disclosure decision, and the amount disclosed at each step has to be reviewable rather
    than sampled.
    """
    node, _course = await _load_dynamic_node(db, user, node_id)
    _render, item_props, key_entry = await _resolve_item(
        db, user, node, body.render_id, body.item_id
    )

    attempts = NodeAttemptRepository(db)
    tries = await attempts.count_for_item(
        user_id=user.id, node_id=node.id, item_id=body.item_id
    )
    hints_used = await attempts.hints_used_for_item(
        user_id=user.id, node_id=node.id, item_id=body.item_id
    )
    if not may_offer_hint(item_attempts=tries, hints_used=hints_used):
        if tries < 1:
            raise ConflictError(
                "Intentalo una vez antes de pedir una pista.", field="item_id"
            )
        raise ConflictError(
            "Ya has usado las tres pistas de este item.", field="hints_used"
        )

    level = hints_used + 1
    hint = _hint_for(level, node=node, item_props=item_props, key_entry=key_entry)

    latest = await attempts.latest_for_item(
        user_id=user.id, node_id=node.id, item_id=body.item_id
    )
    if latest is not None:
        await attempts.update(latest, hints_used=level)
    states = LearnerNodeStateRepository(db)
    state = await states.get_or_create(user_id=user.id, node_id=node.id)
    state.hints_used = max(int(state.hints_used or 0), level)
    await db.commit()

    return NodeHintResult(
        hint=hint, hints_used=level, hints_remaining=max(0, HINT_LIMIT - level)
    )


# --------------------------------------------------------------------------------------
# Feedback, events, waive
# --------------------------------------------------------------------------------------
@router.post("/{node_id}/feedback", status_code=204)
async def submit_feedback(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID, body: NodeFeedbackRequest
) -> Response:
    """End-of-node feedback. Upsert on ``UNIQUE (user_id, node_id)``.

    ``difficulty`` is what fires ``bajar_dificultad`` / ``subir_dificultad`` (§3.3), so the
    signals are applied in the same transaction as the row.
    """
    node, _course = await _load_dynamic_node(db, user, node_id)

    existing = (
        await db.execute(
            select(NodeFeedback).where(
                NodeFeedback.user_id == user.id, NodeFeedback.node_id == node.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            NodeFeedback(
                user_id=user.id,
                node_id=node.id,
                difficulty=body.difficulty,
                unclear=body.unclear,
            )
        )
    else:
        existing.difficulty = body.difficulty
        existing.unclear = body.unclear
    await db.flush()

    profile = await LearnerProfileRepository(db).get_by_user(user.id)
    if profile is not None:
        state = await LearnerNodeStateRepository(db).get_by_user_and_node(
            user.id, node.id
        )
        await _profile_service(db).apply_signals(
            profile=profile,
            context=await _signal_context(
                db, user, node, state, difficulty=body.difficulty
            ),
        )
    await db.commit()
    return Response(status_code=204)


@router.post("/{node_id}/events", status_code=204)
async def record_events(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID, body: NodeEventsRequest
) -> Response:
    """Append instrumentation events (§3.3).

    ``refresh_format_vector`` is **not** called here. See the module docstring: it is
    ``O(events in the window)`` and the vector is only read when a node opens, so the
    refresh happens when a node closes. The events accumulate meanwhile, which is exactly
    what the calibration period of §6.4 assumes.
    """
    node, _course = await _load_dynamic_node(db, user, node_id)
    events = [
        EventInput(
            type=event.type,
            element=event.element,
            # The path node, always. See ``NodeEventInput``: a body-supplied node id was
            # only bounded by the foreign key, which accepts any node in any organisation.
            node_id=node.id,
            element_id=event.element_id,
            ms=event.ms,
        )
        for event in body.events
    ]
    await _profile_service(db).record_events(user_id=user.id, events=events)
    await db.commit()
    return Response(status_code=204)


@router.post("/{node_id}/waive", response_model=NodeStateRead)
async def waive_node(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID, body: NodeWaiveRequest | None = None
) -> NodeStateRead:
    """The human escape hatch of §7.4: an admin accredits a node as ``mastered``.

    ``mastery`` is deliberately left untouched. A waiver is an accreditation by somebody who
    has watched the person work, not a measurement, and inventing a number here would end up
    printed on a certificate as if it had been measured. The ``audit_log`` row records who
    did it, which is the whole point of having a documented escape hatch instead of an
    undocumented one.
    """
    if not _is_admin(user):
        raise ForbiddenError("Only an admin can waive a node.")
    node, course = await _load_dynamic_node(db, user, node_id)
    payload = body or NodeWaiveRequest()

    states = LearnerNodeStateRepository(db)
    target_user_id = payload.user_id or user.id
    state = await states.get_by_user_and_node(target_user_id, node.id)
    if state is None:
        raise NotFoundError("learner_node_states", f"{target_user_id}/{node.id}")
    await states.waive(state, waived_by=user.id)
    await AuditLogRepository(db).record(
        org_id=user.org_id,
        actor_id=user.id,
        action="node_waived",
        subject=node_subject(node.id),
        detail={"reason": payload.reason, "user_id": str(target_user_id)},
    )
    # §7.5 counts a waived node as mastered, so this can be what closes the course. No
    # ``user_skills`` write: a waiver is an accreditation, and `mastery` was deliberately
    # left untouched above, so there is no measured number to translate.
    await _enrollment_service(db).close_dynamic_if_mastered(
        course=course, user_id=target_user_id
    )
    await db.commit()
    return NodeStateRead.of(state)


# --------------------------------------------------------------------------------------
# GET /render-kit
# --------------------------------------------------------------------------------------
@render_kit_router.get("", response_model=UIKitRead)
async def get_render_kit(user: CurrentUser) -> UIKitRead:
    """The frozen kit, served (§11.3).

    Read straight from the build-time artefacts (``load_artifact`` is ``lru_cache``d), so
    this endpoint cannot disagree with the catalogue the prompt was generated from or with
    the ``catalog_version`` baked into every ``cache_key``. It is a *contract*, not
    content: no learner data is touched, which is why it takes a session-less
    ``CurrentUser`` and no ``DBSession``.

    Authenticated: the component list describes a v2 surface, and there is no reason
    for it to be public.
    """
    artifact = load_artifact()
    return UIKitRead(
        catalog_id=artifact.catalog_id,
        catalog_version=artifact.catalog_version,
        catalog_digest=artifact.catalog_digest,
        root=artifact.root,
        ui_spec_version=UI_SPEC_VERSION,
        library_versions={
            name: str(version)
            for name, version in artifact.library_versions.items()
            if version
        },
        components=[
            UIKitComponentRead(
                name=str(component["name"]),
                description=(
                    str(component["description"])
                    if component.get("description")
                    else None
                ),
                signature=str(component["signature"]),
            )
            for component in artifact.prompt_components
        ],
        render_components=(
            list(artifact.render_components)
            if artifact.render_components is not None
            else None
        ),
    )


# --------------------------------------------------------------------------------------
# Item resolution, hints and signals
# --------------------------------------------------------------------------------------
async def _resolve_item(
    db: DBSession,
    user: Any,
    node: CourseNode,
    render_id: uuid.UUID,
    item_id: str,
) -> tuple[NodeRender, dict, dict | None]:
    """Find the ``QuizItem`` props in the served spec and its key entry.

    The props come from ``node_renders.ui_spec`` (server-side) rather than from the request:
    a client that could name its own question could also name its own options. The key entry
    comes from ``node_renders.answer_key``, which never left the server.
    """
    render = await NodeRenderRepository(db).get_scoped(render_id, user.org_id)
    if render is None or render.node_id != node.id:
        raise NotFoundError("node_renders", str(render_id))

    components = (render.ui_spec or {}).get("components") or []
    for component in components:
        if component.get("type") != "QuizItem":
            continue
        props = dict(component.get("props") or {})
        if str(props.get("item_id") or component.get("id")) != item_id:
            continue
        props.setdefault("item_id", item_id)
        key_entry = (render.answer_key or {}).get(item_id)
        return render, props, key_entry

    raise ValidationError(
        f"Item {item_id!r} is not part of render {render_id}", field="item_id"
    )


def _correct_answer(key_entry: dict | None) -> dict | None:
    """The revealable part of the key: the solution and its explanation, nothing else."""
    if not key_entry:
        return None
    revealed = {
        field: key_entry[field]
        for field in ("correct", "correct_order", "blanks", "explanation")
        if field in key_entry
    }
    return revealed or None


def _next_action(*, passed: bool, state: str) -> str:
    if not passed:
        return "retry"
    if state == MASTERED:
        return "next_node"
    return "next_item"


def _hint_for(
    level: int, *, node: CourseNode, item_props: dict, key_entry: dict | None
) -> str:
    """Three escalating hints, and nothing beyond them (§7.4).

    1. Point back at the idea of the node. No item-specific information at all.
    2. A structural nudge that depends on the item type: two distractors ruled out for a
       ``test``, the first step named for ``order_steps``, the shape of the gap for
       ``fill_blank``.
    3. The worked explanation from the key. At this point ``correct_answer`` is revealed on
       the next answer anyway (``hints_used >= 3``), so withholding the reasoning while
       handing over the answer would be the worse of the two.
    """
    key = key_entry or {}
    if level <= 1:
        return f"Vuelve a la idea del nodo: {node.summary}"

    if level == 2:
        item_type = item_type_of(item_props)
        options = list(item_props.get("options") or [])
        if item_type == "test" and isinstance(key.get("correct"), int) and len(options) >= 3:
            wrong = [
                index for index in range(len(options)) if index != key["correct"]
            ][:2]
            listed = " y ".join(f'"{options[index]}"' for index in wrong)
            return f"Puedes descartar {listed}."
        if item_type == "order_steps":
            order = list(key.get("correct_order") or [])
            steps = list(item_props.get("steps") or options)
            if order and 0 <= int(order[0]) < len(steps):
                return f'El primer paso es "{steps[int(order[0])]}".'
        if item_type == "fill_blank":
            blanks = [str(value) for value in (key.get("blanks") or [])]
            if blanks:
                shape = ", ".join(
                    f"{len(blank)} caracteres, empieza por '{blank[:1]}'"
                    for blank in blanks
                    if blank
                )
                return f"Lo que falta: {shape}."
        return (
            "Relee el enunciado y quedate solo con el dato que decide la respuesta; "
            "lo demas es contexto."
        )

    explanation = key.get("explanation")
    if isinstance(explanation, str) and explanation.strip():
        return explanation.strip()
    return (
        "Es la opcion que se sigue directamente de la regla del nodo; comparala con el "
        "resumen y decide."
    )


async def _signal_context(
    db: DBSession,
    user: Any,
    node: CourseNode,
    state: LearnerNodeState | None,
    *,
    difficulty: str | None = None,
) -> NodeSignalContext:
    """Assemble the five trigger inputs of §3.3 from Postgres.

    ``unmastered_prerequisites`` is the LEFT-join query ``LearnerNodeStateRepository`` shipped
    without a caller: a prerequisite the learner never opened has **no** state row at all, so
    an inner join would return nothing for exactly the learner ``revisar_prerrequisito``
    exists for.
    """
    unmastered = await LearnerNodeStateRepository(db).unmastered_prerequisites(
        user_id=user.id, node_id=node.id
    )
    recent = await LearningEventRepository(db).recent_types_for_node(
        user_id=user.id, node_id=node.id, limit=3
    )
    resolved_difficulty = difficulty or await _feedback_difficulty(db, user.id, node.id)
    return NodeSignalContext(
        node_id=node.id,
        consecutive_failed=int(getattr(state, "consecutive_failed", 0) or 0),
        consecutive_correct=int(getattr(state, "consecutive_correct", 0) or 0),
        last_error_kind=getattr(state, "last_error_kind", None),
        difficulty=resolved_difficulty,
        recent_event_types=tuple(recent),
        unmastered_prerequisites=len(unmastered),
    )
