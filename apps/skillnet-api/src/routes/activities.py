"""Authenticated API for rich declarative activities."""

import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, Response

from src.core.exceptions import ConflictError, NotFoundError, ValidationError
from src.deps.auth import AdminUser, CurrentUser
from src.deps.db import DBSession
from src.repositories.activity_definition_repo import (
    ActivityDefinitionRepository,
    ActivityStateRepository,
)
from src.repositories.course_node_repo import CourseNodeRepository
from src.repositories.course_repo import CourseRepository
from src.repositories.learning_event_repo import LearningEventRepository
from src.schemas.activity import (
    ActivityAction,
    ActivityAssetRead,
    ActivityDefinitionCreate,
    ActivityDefinitionRead,
    ActivityProgressRead,
    DidactEventEnvelope,
    ActivityOperationRead,
    ActivityStateRead,
    ActivitySolutionRead,
    ActivityStateWrite,
    ActivitySubmission,
)
from src.schemas.learning_experience import (
    ExperienceAttemptRead,
    ExperienceAttemptSubmission,
)
from src.schemas.node import NodeHintResult
from src.models.activity_definition import ActivityDefinition, ActivityFamily
from src.models.learning_event import LearningEvent
from src.services.activity_definitions import (
    BROKEN_EVALUATION_REASONS,
    ActivityDefinitionService,
    operation_payload,
    public_feedback,
    validated_score,
)
from src.services.activity_hints import activity_hint
from src.services.language_policy import resolve_language
from src.services.activity_ports import PortDeclined
from src.services.activity_solution import render_solution, revealed_solution
from src.services.media.activity_assets import ActivityAssetResolver
from src.services.activity_progress import project_activity_progress
from src.services.experience_attempt_service import ExperienceAttemptService
from src.services.mastery_evidence_service import MasteryEvidenceService
from src.services.mastery_service import HINT_LIMIT, may_offer_hint
from src.repositories.learner_activity_state_repo import LearnerActivityStateRepository
from src.repositories.learner_node_state_repo import LearnerNodeStateRepository
from src.repositories.learner_profile_repo import LearnerProfileRepository
from src.repositories.media_artifact_repo import MediaArtifactRepository

router = APIRouter(prefix="/activities", tags=["Activities"])

#: ``learning_events.type`` under which one graded ``/evaluate`` verdict is recorded.
#: The ``didact.`` prefix is what keeps it inert: ``recent_types_for_node`` excludes it, so
#: the row cannot displace the three legacy signals that drive adaptation.
GRADED_EVENT_TYPE = "graded"
_GRADED_EVENT_ROW_TYPE = f"didact.{GRADED_EVENT_TYPE}"


def _service(db: DBSession) -> ActivityDefinitionService:
    return ActivityDefinitionService(ActivityDefinitionRepository(db), ActivityStateRepository(db))


def _family(activity: ActivityDefinition) -> str:
    return str(getattr(activity.family, "value", activity.family))


@router.post("", response_model=ActivityDefinitionRead, status_code=201)
async def create_activity(user: AdminUser, db: DBSession, body: ActivityDefinitionCreate) -> ActivityDefinitionRead:
    course = await CourseRepository(db).get_scoped(body.course_id, user.org_id)
    if course is None:
        raise NotFoundError("courses", str(body.course_id))
    node = await CourseNodeRepository(db).get_scoped(body.node_id, user.org_id)
    if node is None or node.course_id != course.id:
        raise ValidationError("node_id does not belong to course_id", field="node_id")
    service = _service(db)
    activity = await service.create(org_id=user.org_id, body=body)
    await db.commit()
    return ActivityDefinitionRead.of(activity, missing_ports=service.missing_ports(activity))


@router.get("/{activity_id}/definition", response_model=ActivityDefinitionRead)
async def get_activity_definition(user: CurrentUser, db: DBSession, activity_id: uuid.UUID) -> ActivityDefinitionRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    response = ActivityDefinitionRead.of(
        activity, missing_ports=service.missing_ports(activity)
    )
    if "assets" not in (activity.required_ports or []):
        return response
    asset_ref = (activity.public_definition or {}).get("assetRef")
    if not isinstance(asset_ref, str):
        return response.model_copy(
            update={"status": "declined", "decline_reason": "missing_asset_ref"}
        )
    resolved = await ActivityAssetResolver(MediaArtifactRepository(db)).resolve(
        activity, asset_ref
    )
    if isinstance(resolved, PortDeclined):
        return response.model_copy(
            update={"status": "declined", "decline_reason": resolved.reason}
        )
    if activity.component_id in {"didact.hotspot", "didact.label-diagram"}:
        if not resolved.mime_type.startswith("image/") or not resolved.width or not resolved.height:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "spatial_asset_dimensions_required",
                }
            )
        key = "regions" if activity.component_id == "didact.hotspot" else "targets"
        spatial_ids = {
            str(item.get("id"))
            for item in (activity.public_definition or {}).get(key, [])
            if isinstance(item, dict) and item.get("id")
        }
        if not spatial_ids or not spatial_ids.issubset(resolved.verified_region_ids):
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "grounded_geometry_not_verified",
                }
            )
    if activity.component_id == "didact.interactive-media":
        definition = (activity.public_definition or {}).get("definition") or {}
        media = definition.get("media") if isinstance(definition, dict) else {}
        kind = media.get("kind") if isinstance(media, dict) else None
        authored_duration = media.get("durationMs") if isinstance(media, dict) else None
        if (
            resolved.duration_ms is None
            or authored_duration != resolved.duration_ms
            or resolved.duration_ms > 14_400_000
        ):
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "verified_media_duration_required",
                }
            )
        if kind == "audio" and not resolved.transcript:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "audio_transcript_required",
                }
            )
        if kind == "video" and media.get("noSpeech") is not True and not resolved.captions:
            return response.model_copy(
                update={
                    "status": "declined",
                    "decline_reason": "video_captions_required",
                }
            )
    return response


@router.post("/{activity_id}/events", status_code=204)
async def record_activity_event(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    body: DidactEventEnvelope,
) -> Response:
    """Record EventPort telemetry without changing mastery or ``format_vector``.

    A later node may consume only the bounded scored-evidence projection; the open
    render remains pinned and exposure/completion events stay inert.
    """
    activity = await _service(db).get(activity_id, user.org_id)
    if body.activity_id != activity.id:
        raise ValidationError("activity_id does not match the requested activity", field="activity_id")
    if body.component_id != activity.component_id:
        raise ValidationError("component_id does not match the activity definition", field="component_id")

    payload = body.payload.model_dump(mode="json", exclude_none=True)
    await LearningEventRepository(db).record_didact_event(
        event_id=body.event_id,
        user_id=user.id,
        node_id=activity.node_id,
        event_type=body.type,
        metadata={
            "schema_version": body.version,
            "activity_id": str(activity.id),
            "component_id": activity.component_id,
            "occurred_at": body.occurred_at.isoformat(),
            "payload": payload,
        },
    )
    await db.commit()
    return Response(status_code=204)


@router.get("/{activity_id}/state", response_model=ActivityStateRead)
async def get_activity_state(user: CurrentUser, db: DBSession, activity_id: uuid.UUID) -> ActivityStateRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    row = await service.states.get_for_learner(activity.id, user.id)
    learner = await LearnerActivityStateRepository(db).get_for_learner(
        activity.id, user.id
    )
    return ActivityStateRead.of(
        activity.id,
        row,
        solution_revealed=bool(getattr(learner, "solution_revealed_at", None)),
        failures=int(getattr(learner, "failures_count", 0) or 0),
    )


@router.get("/{activity_id}/assets/{asset_ref}", response_model=ActivityAssetRead)
async def resolve_activity_asset(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    asset_ref: str,
) -> ActivityAssetRead:
    """Resolve an opaque ref through the activity's server-owned scope."""
    activity = await _service(db).get(activity_id, user.org_id)
    resolved = await ActivityAssetResolver(MediaArtifactRepository(db)).resolve(
        activity, asset_ref
    )
    if isinstance(resolved, PortDeclined):
        raise NotFoundError("activity_assets", resolved.reason)
    return ActivityAssetRead(**resolved.as_payload())


@router.get("/{activity_id}/progress", response_model=ActivityProgressRead)
async def get_activity_progress(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
) -> ActivityProgressRead:
    """Read server-owned node mastery. Writes are intentionally absent."""
    activity = await _service(db).get(activity_id, user.org_id)
    row = await LearnerNodeStateRepository(db).get_by_user_and_node(user.id, activity.node_id)
    return ActivityProgressRead(**project_activity_progress(activity.component_id, row).as_payload())


@router.put("/{activity_id}/state", response_model=ActivityStateRead)
async def save_activity_state(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivityStateWrite) -> ActivityStateRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    row = await service.states.save(activity=activity, user_id=user.id, state=body.state)
    await db.commit()
    return ActivityStateRead.of(activity.id, row)


@router.post("/{activity_id}/evaluate", response_model=ActivityOperationRead)
async def evaluate_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivitySubmission) -> ActivityOperationRead:
    """Grade one submission — and, when it is the node's test, **keep the verdict**.

    This endpoint used to be entirely learner-agnostic: it scored, answered, and committed
    nothing. That was fine while it only served artifact-shaped activities, and wrong from
    the moment the default closer of a node became a Didact activity authored at runtime.
    Those are materialized without an ``ImplementationBinding``, so the client cannot use
    ``POST /activities/{id}/attempts`` and posts here instead — which meant the **main
    check of every node was graded and thrown away**: no attempt row, no mastery, no
    countable failure, therefore no rule that could ever let the learner out of it.

    The persistence is scoped to the ``assessment`` family, and that boundary is the whole
    design. An artifact, a simulation or a media activity is not a measurement of anyone,
    and letting one move mastery would put a number on a certificate that nobody earned.
    Everything else keeps the old, stateless behaviour byte for byte.
    """
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    if _family(activity) != ActivityFamily.ASSESSMENT.value:
        return ActivityOperationRead(**operation_payload(await service.evaluate(activity, body.submission)))
    return await _evaluate_assessment(user=user, db=db, service=service, activity=activity, body=body)


async def _evaluate_assessment(
    *,
    user: Any,
    db: DBSession,
    service: ActivityDefinitionService,
    activity: ActivityDefinition,
    body: ActivitySubmission,
) -> ActivityOperationRead:
    """Score, apply the verdict to the learner domain, and project what may be revealed."""
    node = await CourseNodeRepository(db).get_scoped(activity.node_id, user.org_id)
    course = await CourseRepository(db).get_scoped(activity.course_id, user.org_id)
    if node is None or node.archived or course is None:
        # An activity whose node or course is gone or archived still grades; there is just
        # no learner state to move. Failing here would break a preview for no gain.
        return ActivityOperationRead(**operation_payload(await service.evaluate(activity, body.submission)))

    states = LearnerNodeStateRepository(db)
    counters = LearnerActivityStateRepository(db)
    mastery = MasteryEvidenceService(
        db, states=states, profile_repository=LearnerProfileRepository(db)
    )
    # Taken before anything is read. The idempotency lookup below and the transition it
    # protects have to sit inside one critical section, or two clicks read the same streak
    # and both write a failure onto it.
    await mastery.lock_learner_node(user_id=user.id, node_id=node.id)

    events = LearningEventRepository(db)
    digest = _evaluation_digest(activity_id=activity.id, body=body)
    if body.attempt_id is not None:
        recorded = await events.get_by_id(body.attempt_id)
        if recorded is not None:
            return _replayed_verdict(
                activity=activity, user=user, node_id=node.id, event=recorded, digest=digest
            )

    state_row = await states.get_by_user_and_node(user.id, node.id)
    evaluated = await service.evaluate(activity, body.submission)
    if isinstance(evaluated, PortDeclined):
        # Nothing was scored, so nothing is counted. A defective activity must not spend
        # the learner's failures on a question it was never able to ask them.
        return _declined_verdict(evaluated, state_row)

    # Read before the verdict is applied and before anything is incremented: both numbers
    # are contracted as the state *standing* when this submission arrived. Counting first
    # would fire rule 8 one failure early.
    counter_row = await counters.get_for_learner(activity.id, user.id)
    outcome, score, passed, error_kind = validated_score(evaluated)
    result = await mastery.apply(
        user_id=user.id,
        node=node,
        course=course,
        score=score,
        passed=passed,
        error_kind=error_kind,
        # Both numbers are this activity's own, from ``learner_activity_states``. They
        # used to come from ``learner_node_states`` — node-wide, and wrong here in the way
        # that matters: ``item_failures`` is contracted as "failures of *this* question",
        # so passing the node's ``consecutive_failed`` meant three failures on one
        # activity plus one on the next opened the second one's answer. The disclosure
        # count has the same defect in the other direction: ``learner_node_states.hints_used``
        # is only written by ``POST /nodes/{id}/hint``, which no Didact activity goes
        # through, so it read zero for ever.
        hints_used=int(getattr(counter_row, "hints_used", 0) or 0),
        item_failures=int(getattr(counter_row, "failures_count", 0) or 0),
    )
    await counters.record_attempt(activity=activity, user_id=user.id, passed=passed)

    state_value = str(getattr(result.state.state, "value", result.state.state))
    show_worked_solution = bool(result.transition.show_worked_solution)
    payload = {
        **evaluated,
        "state": state_value,
        "mastery": float(result.state.mastery or 0.0),
        "show_worked_solution": show_worked_solution,
        "solution": revealed_solution(
            activity, passed=passed, show_worked_solution=show_worked_solution
        ),
    }
    if body.attempt_id is not None:
        await events.record_didact_event(
            event_id=body.attempt_id,
            user_id=user.id,
            node_id=node.id,
            event_type=GRADED_EVENT_TYPE,
            metadata={
                "activity_id": str(activity.id),
                "component_id": activity.component_id,
                "request_digest": digest,
                "outcome": outcome,
                "score": score,
                "passed": passed,
                "state": state_value,
                "mastery": payload["mastery"],
                "show_worked_solution": show_worked_solution,
            },
        )
    await db.commit()

    if result.transition.increment_nodes_completed:
        # Progress moved forward: pre-warm the next nodes on this learner's own key, the
        # same fire-and-forget the other two writers of mastery do.
        from src.services.node_render_service import spawn_prewarm_sliding_window

        spawn_prewarm_sliding_window(
            user_id=user.id,
            node_id=node.id,
            course_id=course.id,
            org_id=user.org_id,
        )
    return ActivityOperationRead(status="completed", result=payload, decline_reason=None)


def _evaluation_digest(*, activity_id: uuid.UUID, body: ActivitySubmission) -> str:
    """Canonical fingerprint of one submission, to tell a retry from a collision.

    Same job and same shape as ``attempt_request_digest`` on the ``/attempts`` path: an
    ``attempt_id`` that comes back with *different* content is a client bug, not a retry,
    and must not be handed the earlier verdict.
    """
    canonical = json.dumps(
        {
            "attempt_id": str(body.attempt_id),
            "activity_id": str(activity_id),
            "submission": body.submission,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _declined_verdict(
    declined: PortDeclined, state_row: Any
) -> ActivityOperationRead:
    """A decline that carries the learner through when the *activity* is what is broken.

    ``missing_evaluation_definition`` and ``unsupported_evaluation_mode`` are the third
    dead end of this flow, and the one the other two fixes cannot reach: the submission is
    never scored, so no failure is ever counted, so rule 8 never fires and the node never
    opens — whatever the learner does. The status stays ``declined`` and the reason still
    names the defect, because nothing was graded and pretending otherwise would be a lie;
    what changes is that ``result`` now carries ``show_worked_solution: true`` so the client
    can open the way forward on the first submission instead of after four pointless ones.

    Every other decline is left exactly as it was: a missing port or a disabled activity is
    already reported by ``GET /activities/{id}/definition``, so the client never rendered
    it and there is nobody stuck in front of it.
    """
    payload = operation_payload(declined)
    if declined.reason not in BROKEN_EVALUATION_REASONS:
        return ActivityOperationRead(**payload)
    return ActivityOperationRead(
        status="declined",
        decline_reason=declined.reason,
        result={
            "state": str(getattr(getattr(state_row, "state", None), "value", None) or "not_started"),
            "mastery": float(getattr(state_row, "mastery", 0.0) or 0.0),
            "show_worked_solution": True,
            "solution": None,
        },
    )


def _replayed_verdict(
    *,
    activity: ActivityDefinition,
    user: Any,
    node_id: uuid.UUID,
    event: LearningEvent,
    digest: str,
) -> ActivityOperationRead:
    """Rebuild the first verdict for a repeated ``attempt_id``, without grading again.

    The stored row keeps only bounded telemetry — the numbers, never the sentences. The
    reaction line and the worked solution are re-derived from the activity itself, so
    ``learning_events`` never has to hold authored content or an answer key.
    """
    metadata = dict(event.event_metadata or {})
    if (
        event.user_id != user.id
        or event.node_id != node_id
        or event.type != _GRADED_EVENT_ROW_TYPE
        or metadata.get("activity_id") != str(activity.id)
        or metadata.get("request_digest") != digest
    ):
        raise ConflictError(
            "attempt_id is already associated with another submission", field="attempt_id"
        )
    outcome = str(metadata.get("outcome") or "")
    passed = bool(metadata.get("passed"))
    show_worked_solution = bool(metadata.get("show_worked_solution"))
    return ActivityOperationRead(
        status="completed",
        decline_reason=None,
        result={
            "outcome": outcome,
            "passed": passed,
            "score": float(metadata.get("score") or 0.0),
            "feedback": public_feedback(activity.public_definition, outcome),
            "state": str(metadata.get("state") or "learning"),
            "mastery": float(metadata.get("mastery") or 0.0),
            "show_worked_solution": show_worked_solution,
            "solution": revealed_solution(
                activity, passed=passed, show_worked_solution=show_worked_solution
            ),
        },
    )


# --------------------------------------------------------------------------------------
# Asking for help: the hint ladder and the way out
# --------------------------------------------------------------------------------------
@router.post("/{activity_id}/hint", response_model=NodeHintResult)
async def get_activity_hint(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    accept_language: Annotated[str | None, Header()] = None,
) -> NodeHintResult:
    """One hint for one activity, escalating, with ``attempt-before-hint`` and a cap of 3.

    The same rules ``POST /nodes/{id}/hint`` applies to a ``QuizItem``, and deliberately
    the same response shape (``NodeHintResult``) so one client ladder serves both: ``409``
    while the learner has not tried yet, because a hint follows an honest attempt, and
    ``409`` once the quota is spent.

    **The count is the server's.** It comes from ``learner_activity_states.hints_used``,
    which only this route writes; there is no request body to read, and anything sent is
    ignored. Before this route existed the number on screen came from the node's own
    counter, which no Didact activity ever increments — so "te quedan 3 pistas" was true
    of something else and stayed true no matter how many were spent.

    The hints themselves are deterministic (:func:`activity_hint`): a disclosure decision
    has to be reviewable, not sampled.
    """
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    counters = LearnerActivityStateRepository(db)
    row = await counters.get_for_learner(activity.id, user.id)
    attempts = int(getattr(row, "attempts_count", 0) or 0)
    hints_used = int(getattr(row, "hints_used", 0) or 0)
    if not may_offer_hint(item_attempts=attempts, hints_used=hints_used):
        if attempts < 1:
            raise ConflictError(
                "Inténtalo una vez antes de pedir una pista.", field="activity_id"
            )
        raise ConflictError(
            "Ya has usado las tres pistas de esta actividad.", field="hints_used"
        )

    # The node is read for the first rung only, and its absence is not an error: an
    # archived node still has activities, and a learner in front of one still gets a hint.
    node = await CourseNodeRepository(db).get_scoped(activity.node_id, user.org_id)
    # The hint is read by the learner, so it comes out in the language of the course the
    # activity belongs to. Loaded from the node rather than from the request: a client that
    # could name the language of its own hints could disagree with the lesson beside it.
    course = (
        await CourseRepository(db).get_scoped(node.course_id, user.org_id)
        if node is not None
        else None
    )
    level = hints_used + 1
    hint = activity_hint(
        level,
        component_id=activity.component_id,
        public_definition=activity.public_definition,
        evaluation=(activity.private_definition or {}).get("evaluation"),
        node_summary=getattr(node, "summary", None),
        language=resolve_language(
            course=course, accept_language_header=accept_language
        ),
    )
    await counters.record_hint(activity=activity, user_id=user.id, level=level)
    await db.commit()
    return NodeHintResult(
        hint=hint, hints_used=level, hints_remaining=max(0, HINT_LIMIT - level)
    )


@router.post("/{activity_id}/solution", response_model=ActivitySolutionRead | None)
async def reveal_activity_solution(
    user: CurrentUser, db: DBSession, activity_id: uuid.UUID
) -> ActivitySolutionRead | None:
    """The learner asks to be shown the answer, and is shown it — on the record.

    The exit rule 8 opens by exhaustion, taken on purpose instead. One attempt is required
    (``409`` otherwise) for the same reason a hint requires one: the answer follows a try.

    **Nothing about mastery is written here.** Asking for the answer demonstrates nothing,
    so this route stamps ``solution_revealed_at`` and touches no other column — the shape
    ``POST /nodes/{id}/complete`` already uses to record that a node was worked through
    without putting an invented number on the scale a certificate is read from. Rule 8 is
    not fired either: the learner left the activity by their own decision, and dropping
    ``show_worked_solution`` on the node's state would make that look like a fourth
    failure.

    ``null`` is a valid answer, and the reason it is not a ``404``: ``render_solution``
    refuses the modes it cannot put into words, and "asked, nothing to print" still closes
    the activity and still has to let the learner move on. The stamp is written either
    way, so the two are indistinguishable to a later reader — which is correct, because
    what was recorded is that the learner asked and was answered.
    """
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    counters = LearnerActivityStateRepository(db)
    row = await counters.get_for_learner(activity.id, user.id)
    if int(getattr(row, "attempts_count", 0) or 0) < 1:
        raise ConflictError(
            "Inténtalo una vez antes de ver la solución.", field="activity_id"
        )

    await counters.mark_solution_revealed(activity=activity, user_id=user.id)
    await db.commit()
    written = render_solution(
        component_id=activity.component_id,
        public_definition=activity.public_definition,
        evaluation=(activity.private_definition or {}).get("evaluation"),
    )
    return ActivitySolutionRead(**written) if written else None


@router.post("/{activity_id}/attempts", response_model=ExperienceAttemptRead)
async def submit_experience_attempt(
    user: CurrentUser,
    db: DBSession,
    activity_id: uuid.UUID,
    body: ExperienceAttemptSubmission,
) -> ExperienceAttemptRead:
    """Evaluate once and atomically persist neutral evidence plus mastery.

    The client supplies identity, binding, raw submission and duration only. Scoring,
    evidence normalization and all learner-state changes remain server-owned.
    """

    result = await ExperienceAttemptService(db).submit(
        user=user, activity_id=activity_id, body=body
    )
    await db.commit()
    return result


@router.post("/{activity_id}/transition", response_model=ActivityOperationRead)
async def transition_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivityAction) -> ActivityOperationRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    return ActivityOperationRead(**operation_payload(await service.transition(activity, body.state, body.action)))


@router.post("/{activity_id}/execute", response_model=ActivityOperationRead)
async def execute_activity(user: CurrentUser, db: DBSession, activity_id: uuid.UUID, body: ActivitySubmission) -> ActivityOperationRead:
    service = _service(db)
    activity = await service.get(activity_id, user.org_id)
    return ActivityOperationRead(**operation_payload(await service.execute(activity, body.submission)))
