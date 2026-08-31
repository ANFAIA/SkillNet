"""The runtime employee surface (§11.3): node list, probe, render, answer, hint.

A course that is not dynamic 404s: it has no nodes, and saying so with a 403 would leak
the existence of a surface that does not apply.

Where the wiring left dangling by other batches gets connected:

* ``LearnerProfileService.record_events`` -> ``POST /nodes/{id}/events``.
* ``LearnerProfileService.apply_signals`` -> ``/answer``, through
  ``MasteryEvidenceService``, which fills ``NodeSignalContext`` from the learner's own
  measured evidence. ``POST /nodes/{id}/feedback`` used to be the second caller; it was
  removed on 2026-08-29 with the rest of the declared-difficulty path (see
  ``docs/design/future-lesson-feedback.md``).
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

from fastapi import APIRouter, Depends, Header, Query, Response
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
from src.config import settings
from src.core.logging import get_logger
from src.core.sse import format_sse, subscribe
from src.deps.auth import CurrentUser
from src.deps.db import DBSession
from src.deps.llm import get_optional_llm_service
from src.llm.client import LLMService, resolve_llm_config
from src.llm.fixtures import maybe_fixture_llm
from src.models import (
    Course,
    CourseNode,
    NodeRender,
    NodeRenderStatus,
    Organization,
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
    NodeAnswerRequest,
    NodeAttemptResult,
    NodeCompletionRead,
    NodeEventsRequest,
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
from src.services.activity_hints import (
    back_to_node,
    discard_options,
    first_step,
    generic_explanation,
    generic_structure,
    missing_text,
)
from src.services.course_access import assert_learner_can_open, is_admin
from src.services.course_delivery import resolve_delivery
from src.services.enrollment_service import EnrollmentService
from src.services.language_policy import resolve_language
from src.services.learner_profile_service import LearnerProfileService
from src.services.mastery_service import (
    HINT_LIMIT,
    WORKED_SOLUTION_FAILURES,
    MASTERED,
    may_offer_hint,
)
from src.services.node_progression import (
    CourseProgression,
    course_progression,
    resolve_navigation,
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
    fallback_retry_available,
    in_flight_for,
    owner_of_request,
)
from src.services.probe_service import ProbeService
from src.services.runtime_modalities import RuntimeModality, request_runtime_modality
from src.services.skill_service import SkillService

logger = get_logger(__name__)


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


async def _assert_course_open(db: DBSession, user: Any, course: Course) -> None:
    """The v1 rule of ``GET /courses/{id}`` (``routes/courses.py``), applied to v2.

    Both halves now live in ``services/course_access.py`` — enrolled, and the course not
    archived — because v1 and v2 were spelling the enrollment half out separately and the
    archive half was spelled out nowhere. This wrapper stays for the two callers below and
    to keep ``EnrollmentRepository`` named in *this* module, which is the seam the route
    tests replace with a double.

    Why the rule at all: org scoping is **not** an access rule.
    ``CourseNodeRepository.get_scoped`` and ``CourseRepository.get_scoped`` only prove the
    row belongs to the caller's organisation, which every colleague shares; without this
    check any authenticated employee could enumerate the node graph of a course nobody
    assigned them, open its probes, and make ``POST /nodes/{id}/render`` spend real tokens
    on a node they were never meant to see. v1 forbids exactly that over the same data.

    Admins are exempt for the same reason they are in v1: the preview of §11.3 and the
    waiver of §7.4 are creator tools, and nobody enrolls a creator in the course they are
    reviewing.
    """
    await assert_learner_can_open(
        user=user, course=course, enrollments=EnrollmentRepository(db)
    )


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
    await _assert_course_open(db, user, course)
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
    """One definition of the role read, shared with ``services/course_access.py``."""
    return is_admin(user)


async def _progression(
    db: DBSession, user: Any, course: Course
) -> tuple[list[CourseNode], CourseProgression]:
    """This learner's standing in this course, read once and shared by both callers.

    ``GET /courses/{id}/nodes`` renders it and ``POST /nodes/{id}/complete`` enforces it.
    They go through the same function so a client can never be told a lesson is open and
    then refused when it finishes it — the disagreement that a lock spelled out inside one
    endpoint always ends in, because the endpoint is not reusable so the rule gets copied.
    """
    nodes = list(
        await CourseNodeRepository(db).list_for_course(course.id, include_archived=False)
    )
    states = await LearnerNodeStateRepository(db).states_for_nodes(
        user_id=user.id, node_ids=[node.id for node in nodes]
    )
    return nodes, course_progression(
        nodes,
        states,
        navigation=resolve_navigation(course, is_admin=_is_admin(user)),
    )


# --------------------------------------------------------------------------------------
# GET /courses/{course_id}/nodes
# --------------------------------------------------------------------------------------
@course_nodes_router.get("/{course_id}/nodes", response_model=NodeListRead)
async def list_course_nodes(
    user: CurrentUser, db: DBSession, course_id: uuid.UUID
) -> NodeListRead:
    """The node list with per-learner state and the completion rule of §7.5.

    This route **serialises**; it does not decide. Where a learner stands is one question
    and ``services/node_progression`` is the one place that answers it — including what
    "done" means, which this route used to spell out for itself and got wrong: it compared
    prerequisites against ``mastered`` while the rest of the system had moved to
    ``node_is_done``, so a finished expository node locked its successor for ever.
    """
    course = await CourseRepository(db).get_scoped(course_id, user.org_id)
    if course is None or resolve_delivery(course) != "dynamic":
        raise NotFoundError("courses", str(course_id))
    await _assert_course_open(db, user, course)

    nodes, progression = await _progression(db, user, course)
    by_id = {node.id: node for node in nodes}

    rows = [
        NodeSummaryRead(
            id=item.node_id,
            title=by_id[item.node_id].title,
            summary=by_id[item.node_id].summary,
            criticality=str(
                getattr(
                    by_id[item.node_id].criticality,
                    "value",
                    by_id[item.node_id].criticality,
                )
            ),
            position=item.position,
            state=item.state,
            mastery=item.mastery,
            done=item.done,
            available=item.available,
            # "Where was I?" — see NodeSummaryRead. Null for a node never served to
            # this learner, including the ones the prefetch already created a row for.
            first_seen_at=item.first_seen_at,
            # The other half of "done". `state` cannot carry it: an expository node
            # has no graded item, so it never leaves `not_started` however completely
            # it was read. See `NodeSummaryRead.completed_at`.
            completed_at=item.completed_at,
        )
        for item in progression.nodes
    ]
    return NodeListRead(
        course_id=course.id,
        delivery_mode=str(getattr(course.delivery_mode, "value", course.delivery_mode)),
        schema_version=int(course.schema_version or 1),
        nodes=rows,
        next_node_id=progression.next_node_id,
        can_complete=progression.can_complete,
        blocked_by=list(progression.blocked_by),
        progress_percent=progression.progress_percent,
    )


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
    accept_language: Annotated[str | None, Header()] = None,
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
        # ``payload.language`` used to default to ``"es"``, which meant an English course
        # narrated its podcast in Spanish unless the client thought to say otherwise. It is
        # optional now, and the course answers when nobody asked.
        language=resolve_language(
            requested=payload.language,
            course=course,
            accept_language_header=accept_language,
        ),
    )
    return MediaArtifactAccepted(
        artifact_id=artifact.id,
        status=str(getattr(artifact.status, "value", artifact.status)),
    )


@router.get("/{node_id}/render")
async def get_render(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    preview_pref: str | None = Query(default=None),
) -> Any:
    """The **pinned** render. Recomputes nothing (§5.5).

    This is the mechanism behind the "Estable" row of the spatial-stability table: the key is
    not recalculated here, so answering an item cannot change the screen and a TanStack
    refetch on window focus returns the same bytes. ``202`` while there is nothing pinned
    yet; only ``POST …/render {"force": true}`` repins.

    ``preview_pref=audio|visual`` is the onboarding hook: when the node has a pre-baked demo
    variant for that preference bucket it is returned as a cache hit, never generated, so the
    admin tour can flip between variants instantly. Absent (or a node with no pre-baked
    variant), behaviour is exactly as before.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
    service = NodeRenderService(db)
    service.assert_reviewed(node)

    if preview_pref is not None:
        prebaked = await service.prebaked_preview(node=node, bucket=preview_pref)
        if prebaked is not None:
            served = ServedRender.of(prebaked, cached=True)
            return NodeRenderRead.of(served)

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
    # A lesson handed to a browser is the honest "the learner was here" moment, and the
    # only one: `POST /render` is also fired by the anticipatory prefetch for the nodes
    # ahead, so stamping there would mark nodes nobody opened. Idempotent — the stamp is
    # never moved on a re-read.
    await LearnerNodeStateRepository(db).mark_opened(user_id=user.id, node_id=node.id)
    # Same moment, same reason: a lesson on the learner's screen is what "the learner
    # started this course" means, and the dynamic branch had nobody stamping it — a course
    # at 57% still read "Pendiente" and "Cursos activos" counted 0. Idempotent (it only
    # moves an `assigned` row, and never rewrites `started_at`), and internally gated on
    # `resolve_delivery`, so v1 keeps its own transition in `routes/lessons.py`.
    await _enrollment_service(db).mark_dynamic_started(course=course, user_id=user.id)
    # "Preparándose…": a **legacy_stepper** shell (a hard ``fallback`` is one too) served
    # only because the node's knowledge pack is not ready yet — an adaptive episode is
    # still coming and will replace it once the pack lands. An honest legacy decline (pack
    # ready, generation chose legacy) is *not* preparing and is served normally.
    preparing = (
        settings.ADAPTIVE_EPISODES
        and served.shell_mode == "legacy_stepper"
        and not await service.node_pack_ready(node=node, course=course)
    )
    # `ready` is retained, `fallback` is not. The learner keeps the backup content on *this*
    # response — blanking a served screen to go and generate would be strictly worse — and
    # one regeneration is asked for in the background. It rewrites the same `cache_key` in
    # place, so a run that comes out `ready` replaces the degraded screen here and for the
    # whole bucket, and a run that fails again changes nothing. This is the only place that
    # can trigger it: the client stops asking `POST /render` the moment `GET /render` has
    # something served, which is exactly how a transient failure became permanent.
    #
    # Two exclusions. A "preparing" fallback is not a failure at all — its knowledge pack is
    # still generating, regenerating now could only produce another fallback, and the client
    # already re-arms a request when that pin drops. And the budget peek keeps a node that
    # fails deterministically from spending an LLM cycle per page view.
    #
    # Guarded, and that guard is load-bearing. Only the *graph* is fire-and-forget:
    # everything `request_render` does before spawning it runs inline here — the profile
    # read, `load_runtime_knowledge`, the longitudinal events, the media and source-image
    # queries — and that path carries real assertions. An upgrade attempt that raises
    # would leave `unhandled_error_handler` turning a screen we had ALREADY built and
    # served into a 500, which is the exact opposite of what this block is for.
    if (
        not preparing
        and served.status == NodeRenderStatus.FALLBACK.value
        and fallback_retry_available(render.cache_key)
    ):
        try:
            await service.request_render(user=user, node=node, course=course)
        except Exception:
            logger.warning(
                "Upgrading the fallback render failed; serving the backup content",
                extra={"node_id": str(node.id), "cache_key": render.cache_key},
                exc_info=True,
            )
    await db.commit()
    return NodeRenderRead.of(served, preparing=preparing)


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
    accept_language: Annotated[str | None, Header()] = None,
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
        # A replay has no ``transition`` to ask, so rule 8 is re-derived from the same two
        # facts that produced it: this item's failures, and that the stored attempt failed.
        # Without it a client whose first response was lost — the exact case ``attempt_id``
        # exists for — replays into ``correct_answer: null`` and never sees the solution
        # that unlocks the step. One extra count on a path that only runs on a duplicate.
        replayed_worked_solution = not existing_attempt.passed and (
            await attempts.count_failures_for_item(
                user_id=user.id, node_id=node.id, item_id=body.item_id
            )
            >= WORKED_SOLUTION_FAILURES
        )
        reveal = (
            bool(existing_attempt.passed)
            or int(existing_attempt.hints_used or 0) >= HINT_LIMIT
            or replayed_worked_solution
        )
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
            next=_next_action(
                passed=bool(existing_attempt.passed),
                state=state_value,
                show_worked_solution=replayed_worked_solution,
            ),
            show_worked_solution=replayed_worked_solution,
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
            open_llm,
            item_type,
            content_for(item_props, key_entry),
            body.answer,
            # The feedback is text the learner reads, so it follows the course, not the
            # language the grader prompt happens to be written in.
            language=resolve_language(
                course=course, accept_language_header=accept_language
            ),
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
        item_failures=item_failures,
    )
    state = mastery_result.state
    transition = mastery_result.transition
    await db.commit()

    if transition.increment_nodes_completed:
        # Progress moved forward: pre-warm the next nodes on this learner's own key so the
        # next lessons are ready when they get there (sliding window). Fire-and-forget.
        from src.services.node_render_service import spawn_prewarm_sliding_window

        spawn_prewarm_sliding_window(
            user_id=user.id,
            node_id=node.id,
            course_id=node.course_id,
            org_id=node.org_id,
        )

    # `show_worked_solution` is the third door, and it has to be here or the panel opens
    # empty. Rule 8 used to require `hints_used >= HINT_LIMIT`, so the middle condition
    # covered it by construction; since the exit stopped depending on the learner *asking*
    # for help, a fourth failure with no hints requested sets the flag while this gate
    # still says no — "here is the worked solution" with nothing inside it.
    reveal = result.passed or hints_used >= HINT_LIMIT or transition.show_worked_solution
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
        next=_next_action(
            passed=result.passed,
            state=state_value,
            show_worked_solution=transition.show_worked_solution,
        ),
        show_worked_solution=transition.show_worked_solution,
    )


@router.post("/{node_id}/hint", response_model=NodeHintResult)
async def get_hint(
    user: CurrentUser,
    db: DBSession,
    node_id: uuid.UUID,
    body: NodeHintRequest,
    accept_language: Annotated[str | None, Header()] = None,
) -> NodeHintResult:
    """One hint, escalating, with ``attempt-before-hint`` and a hard cap of 3 (§7.4).

    ``409`` when there is no attempt yet — the whole point of the rule is that a hint follows
    an honest try — and ``409`` once the quota is spent, at which point the next failure of
    that item hands over the worked solution and closes it (rule 8 of §7.3).

    The hints are **deterministic**, derived from the item and its key. No LLM call: a hint is
    a disclosure decision, and the amount disclosed at each step has to be reviewable rather
    than sampled.
    """
    node, course = await _load_dynamic_node(db, user, node_id)
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
    hint = _hint_for(
        level,
        node=node,
        item_props=item_props,
        key_entry=key_entry,
        language=resolve_language(
            course=course, accept_language_header=accept_language
        ),
    )

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
# Events, waive
# --------------------------------------------------------------------------------------
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


@router.post("/{node_id}/complete", response_model=NodeCompletionRead)
async def complete_node(
    user: CurrentUser, db: DBSession, node_id: uuid.UUID
) -> NodeCompletionRead:
    """The learner reached the end of this node's content.

    **``completed_at`` is a separate dimension from mastery, and this route writes only
    it.** ``state``, ``mastery`` and ``attempts_count`` are left exactly as they were:
    getting to the last screen is not a demonstration of anything, and writing a mastery
    number here would put an invented figure on the same axis as measured ones — the axis
    ``SkillService.record_mastery`` derives a skill level from. What the stamp *does*
    change is progress, because ``mastery_service.node_is_done`` counts a node as done
    when it is mastered **or** finished; before it existed, an expository node (no graded
    item, so ``mastered`` unreachable by rule 6 of §7.3) counted as zero progress no
    matter how completely it was read, and a course made of them reported 0%.

    Idempotent in both halves. ``mark_completed`` never moves a stamp that is already
    there, and ``close_dynamic_if_mastered`` is a recompute that no-ops when the
    enrollment already agrees with the verdict — so a client may call this on every
    "next node" press without tracking whether it already did.

    The closure call is the same one ``POST /nodes/{id}/waive`` makes, and for the same
    reason: finishing the last node of a course can be what completes it, and nothing else
    on this path would notice. It is gated on ``resolve_delivery`` internally, so v1 keeps
    its own rule.

    **A node the server never served cannot be finished** (``node_not_seen``). Everything
    else on this route is asserted by the client: the ids are handed out by
    ``GET /courses/{course_id}/nodes``, so without this check a learner could POST here
    once per node and close the course — stamped, ``COMPLETED``, skills granted — without
    a single lesson ever being rendered to them. That mattered less when the certificate
    carried a score and a fabricated pass showed up as a low one; it is the whole claim
    now that closure is what a certificate asserts **and** what accredits the course's
    skills.

    ``first_seen_at`` is the right fact to ask for and it already exists: it is stamped by
    ``GET /nodes/{node_id}/render`` alone — never by the anticipatory prefetch, which is
    why ``mark_opened`` was deliberately kept out of ``get_or_create`` — and its own
    docstring already calls it "part of the evidence a certificate is justified with".
    So this is one more reader of a fact the system was already recording, not a new
    mechanism. 409 rather than 403: the node is not forbidden, it is *not yet* open, and
    rendering it makes the same call succeed.

    **And in a sequential course, a lesson whose predecessor is unfinished is refused too**
    (``node_locked``). Same argument, one step further: a client that only hides the next
    lesson has made the course's order a suggestion, and the one place order has teeth is
    the write that moves progress. The rule is not spelled out here — the route asks
    ``node_progression`` for the same snapshot ``GET /courses/{id}/nodes`` renders, so the
    list and the refusal cannot drift apart. Admins are exempt through
    ``resolve_navigation``, by role and not by enrollment: a preview must not stop at
    lesson two. 409 for the same reason as above — finishing the previous lesson makes
    this call succeed.

    The order of the two checks is not arbitrary. ``node_not_seen`` comes first because it
    holds in every mode and is about this node alone; ``node_locked`` is a statement about
    a *different* node, and only a course that opted in has one to make.
    """
    node, course = await _load_dynamic_node(db, user, node_id)

    state_repo = LearnerNodeStateRepository(db)
    seen = await state_repo.get_by_user_and_node(user.id, node.id)
    if seen is None or seen.first_seen_at is None:
        raise ConflictError(
            "This lesson has not been opened yet, so it cannot be marked as finished.",
            field="node_not_seen",
        )

    _nodes, standing = await _progression(db, user, course)
    entry = next(
        (item for item in standing.nodes if item.node_id == node.id), None
    )
    if entry is not None and not entry.available:
        raise ConflictError(
            "This course is taken in order, and the previous lesson is not finished yet.",
            field="node_locked",
        )

    state = await state_repo.mark_completed(user_id=user.id, node_id=node.id)
    _enrollment, completion = await _enrollment_service(db).close_dynamic_if_mastered(
        course=course, user_id=user.id
    )
    await db.commit()

    return NodeCompletionRead(
        node_id=node.id,
        completed_at=state.completed_at,
        # Echoed, not written. A client seeing `not_started` here next to a timestamp is
        # reading the two columns doing their two different jobs.
        state=str(getattr(state.state, "value", state.state)),
        mastery=float(state.mastery or 0.0),
        progress_percent=completion.progress_percent if completion else 0,
        can_complete=bool(completion.can_complete) if completion else False,
    )


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


def _next_action(*, passed: bool, state: str, show_worked_solution: bool = False) -> str:
    """What the client should do next with this item.

    ``show_worked_solution`` wins over the failure, and that ordering is the whole point
    of rule 8 (§7.4): once the worked solution has been handed over there is nothing left
    to retry, and answering ``retry`` would send the learner back to the item they just
    failed for the fourth time — the loop the rule exists to break.
    """
    if show_worked_solution:
        return "next_item"
    if not passed:
        return "retry"
    if state == MASTERED:
        return "next_node"
    return "next_item"


def _hint_for(
    level: int,
    *,
    node: CourseNode,
    item_props: dict,
    key_entry: dict | None,
    language: str | None = None,
) -> str:
    """Three escalating hints for a ``QuizItem``, and nothing beyond them (§7.4).

    1. Point back at the idea of the node. No item-specific information at all.
    2. A structural nudge that depends on the item type: two distractors ruled out for a
       ``test``, the first step named for ``order_steps``, the shape of the gap for
       ``fill_blank``.
    3. The worked explanation from the key. At this point ``correct_answer`` is revealed on
       the next answer anyway (``hints_used >= 3``), so withholding the reasoning while
       handing over the answer would be the worse of the two.

    **What this function decides and what it does not.** It decides *how much* of the key
    a ``QuizItem`` discloses at each rung; the sentences themselves come from
    ``src/services/activity_hints.py``, which is also the Didact ladder. The two used to
    hold separate copies of the same six sentences and had already drifted apart in
    wording and in accents — a learner met a different rule depending on which kind of
    question was on screen. Only the traversal is item-shaped: a ``QuizItem`` addresses
    its options by index and a Didact activity by id, so the walking stays here.
    """
    key = key_entry or {}
    if level <= 1:
        return back_to_node(node.summary, language)

    if level == 2:
        item_type = item_type_of(item_props)
        options = list(item_props.get("options") or [])
        if item_type == "test" and isinstance(key.get("correct"), int) and len(options) >= 3:
            wrong = [
                index for index in range(len(options)) if index != key["correct"]
            ][:2]
            return discard_options([options[index] for index in wrong], language)
        if item_type == "order_steps":
            order = list(key.get("correct_order") or [])
            steps = list(item_props.get("steps") or options)
            if order and 0 <= int(order[0]) < len(steps):
                return first_step(steps[int(order[0])], language)
        if item_type == "fill_blank":
            blanks = [str(value) for value in (key.get("blanks") or [])]
            parts = [(len(blank), blank[:1]) for blank in blanks if blank]
            if parts:
                return missing_text(parts, language)
        return generic_structure(language)

    explanation = key.get("explanation")
    if isinstance(explanation, str) and explanation.strip():
        return explanation.strip()
    return generic_explanation(language)
