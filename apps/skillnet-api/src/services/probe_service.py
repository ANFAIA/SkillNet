"""The pre-assessment (§7.1): where the items come from, how they are graded, and the
rule that a learner gets exactly one scored shot per schema version.

Item sources, in strict order of preference:

1. ``course_nodes.probe_items`` / ``probe_answer_key`` — pre-generated when the schema
   was validated. **Zero tokens, zero wait**, and it is the normal case: items depend
   only on ``(node, source)``, so one generation per node serves the whole
   organization. This is also the prerequisite for §9.1 — if the probe needed an LLM
   call at open time, the "productive wait" would have its own wait in front of it,
   against a blank screen.
2. Existing v1 exercises of ``node.seed_lesson_id``, resampled. **Zero tokens.**
3. An LLM call (``runtime_fast``, ``json_mode``, ``max_tokens=500``), written back into
   the node so the next employee does not pay for it either.

The anti-retry rule (§3.4) is enforced here and by the partial unique index: one scored
probe per ``(user_id, node_id, schema_version)``. Re-entering a node serves the stored
verdict; it does not deal a new hand. Without it, two 4-option items can be
brute-forced in ~16 re-entries, which would mean skipping a ``critical`` safety node
without reading a line of content.

Repositories arrive by injection and are typed structurally, so the tests use in-memory
fakes and need neither a DB nor the network (§12.2).

``answer_key`` stays inside this module. What leaves it is ``ProbeSession``, whose
``probe`` is typed as ``ProbeRow`` (a protocol without that column), and whose
``to_read()`` produces the only shape a route may serialize — see
``src/schemas/probe.py`` and ``tests/test_probe_answer_key_privacy.py``.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from src.core.exceptions import ConflictError, LLMError, ValidationError
from src.core.logging import get_logger
from src.llm.parsing import parse_json_response
from src.llm.prompts.probe import (
    PROBE_GENERATOR_SYSTEM,
    PROBE_MAX_TOKENS,
    PROBE_TEMPERATURE,
    build_probe_prompt,
)
from src.services.mastery_service import (
    APPLY_FLOOR,
    LEARNING,
    MASTERED,
    NEEDS_REVIEW,
    NOT_STARTED,
    PROBING,
    ProbeVerdict,
    RenderHint,
    Transition,
    mastery_prior,
    may_reprobe,
    probe_verdict,
    requires_tiebreak,
    scaffold_band_for,
    threshold_for,
    tiebreak_verdict,
    transition_close_probe,
    transition_open_node,
)
from src.services.node_grading import (
    classify_error,
    content_for,
    grade_item,
    item_type_of,
    public_props,
    split_v1_content,
)

logger = get_logger(__name__)

ITEM_A, ITEM_B, ITEM_C = "a", "b", "c"
SELECTED_ITEMS = (ITEM_A, ITEM_B)
# Item A decides, so it carries the "apply" level; B checks comprehension.
REQUIRED_BLOOM = {ITEM_A: "apply", ITEM_B: "understand"}
TEST_OPTION_COUNT = 4
CONSTRUCTED_TYPES = ("fill_blank", "practical_case")


def _value(raw: object) -> str:
    return raw.value if isinstance(raw, enum.Enum) else str(raw)


# --- the item contract, enforced in code ------------------------------------


def validate_probe_items(
    items: Sequence[dict],
    answer_key: dict,
    criticality: object = "recommended",
) -> None:
    """Raise ``ValidationError`` unless the items honour §7.1.

    Public because the pre-generation step of B2 validates with the same function it
    will be served through: a contract checked in one place and served from another is
    two contracts.
    """
    by_id = {item.get("item_id"): item for item in items}
    for required in SELECTED_ITEMS:
        if required not in by_id:
            raise ValidationError(f"Probe is missing item {required!r}", field="items")

    for item_id in SELECTED_ITEMS:
        item = by_id[item_id]
        kind = item_type_of(item)
        if kind == "true_false":
            raise ValidationError(
                "true_false is no longer allowed in a probe: it raises the chance "
                "floor from 6.25% to 12.5% and the doubt band of the mastery rule "
                "stops being true.",
                field=f"items.{item_id}.item_type",
            )
        if kind != "test":
            raise ValidationError(
                f"Probe item {item_id!r} must be of type 'test', got {kind!r}",
                field=f"items.{item_id}.item_type",
            )
        options = item.get("options") or []
        if len(options) != TEST_OPTION_COUNT:
            raise ValidationError(
                f"Probe item {item_id!r} needs exactly {TEST_OPTION_COUNT} options, "
                f"got {len(options)}",
                field=f"items.{item_id}.options",
            )
        if item.get("bloom_level") != REQUIRED_BLOOM[item_id]:
            raise ValidationError(
                f"Probe item {item_id!r} must be bloom_level "
                f"{REQUIRED_BLOOM[item_id]!r}, got {item.get('bloom_level')!r}",
                field=f"items.{item_id}.bloom_level",
            )
        key = answer_key.get(item_id) or {}
        correct = key.get("correct")
        if not isinstance(correct, int) or isinstance(correct, bool):
            raise ValidationError(
                f"answer_key[{item_id!r}].correct must be the index of the right option",
                field=f"answer_key.{item_id}.correct",
            )
        if not 0 <= correct < TEST_OPTION_COUNT:
            raise ValidationError(
                f"answer_key[{item_id!r}].correct is out of range: {correct}",
                field=f"answer_key.{item_id}.correct",
            )

    tiebreak = by_id.get(ITEM_C)
    if tiebreak is None:
        if requires_tiebreak(criticality):
            raise ValidationError(
                "A critical node needs the constructed tie-break item 'c': on a "
                "critical node 'mastered' may never come out of selected-response "
                "items alone.",
                field="items",
            )
        return

    kind = item_type_of(tiebreak)
    if kind not in CONSTRUCTED_TYPES:
        raise ValidationError(
            f"Tie-break item must be a constructed-response type "
            f"{CONSTRUCTED_TYPES}, got {kind!r}",
            field="items.c.item_type",
        )
    if ITEM_C not in answer_key:
        raise ValidationError("answer_key has no entry for item 'c'", field="answer_key.c")
    if kind == "fill_blank" and not (answer_key[ITEM_C] or {}).get("blanks"):
        raise ValidationError(
            "A fill_blank tie-break needs its expected 'blanks'", field="answer_key.c"
        )


def served_items(items: Sequence[dict], *, criticality: object, tiebreak_used: bool) -> list[dict]:
    """The items the employee is allowed to see, answer-free.

    Item ``c`` travels up front only on a ``critical`` node, where it is mandatory
    (§7.1). Elsewhere it appears once the verdict has fallen into the doubt band, which
    is what ``tiebreak_used`` records — so a learner who masters cleanly never sees it.
    """
    expose_c = requires_tiebreak(criticality) or tiebreak_used
    out = []
    for item in items:
        if item.get("item_id") == ITEM_C and not expose_c:
            continue
        out.append(public_props(item))
    return out


def parse_probe_response(raw: str, *, criticality: object = "recommended") -> tuple[list[dict], dict]:
    """Parse and validate the generator's JSON. Raises ``LLMError`` on a bad shape.

    Validation failures are re-raised as ``LLMError`` (not ``ValidationError``): from
    the caller's point of view the model produced something unusable, which is a
    provider-side problem, not the employee's request being invalid.
    """
    payload = parse_json_response(raw)
    if not isinstance(payload, dict):
        raise LLMError("Probe generator did not return a JSON object.")
    items = payload.get("items")
    answer_key = payload.get("answer_key")
    if not isinstance(items, list) or not isinstance(answer_key, dict):
        raise LLMError("Probe generator response has no 'items'/'answer_key'.")
    try:
        validate_probe_items(items, answer_key, criticality)
    except ValidationError as exc:
        raise LLMError(f"Probe generator broke the item contract: {exc.message}") from exc
    return items, answer_key


def seed_probe_items(
    exercises: Sequence[Any],
    *,
    criticality: object = "recommended",
) -> tuple[list[dict], dict]:
    """Resample existing v1 exercises of the seed lesson as probe items (source 2).

    Selection is by **type and shape**, not by Bloom level: ``exercises`` has no
    ``bloom_level`` column (verified — it is ``lesson_id``, ``type``, ``content``,
    ``position``), so the level §7.1 asks for is *stamped* on the slot the exercise
    fills instead of being read from a column that does not exist. Slot A takes the
    first 4-option ``test``, slot B the next one, slot C the first constructed-response
    exercise.

    Returns ``([], {})`` when the lesson cannot fill slots A and B; the caller then
    falls through to the LLM.
    """
    tests = [
        ex
        for ex in exercises
        if _value(ex.type) == "test"
        and len((ex.content or {}).get("options") or []) == TEST_OPTION_COUNT
        and isinstance((ex.content or {}).get("correct"), int)
    ]
    if len(tests) < 2:
        return [], {}

    items: list[dict] = []
    answer_key: dict[str, dict] = {}
    for item_id, exercise in zip(SELECTED_ITEMS, tests[:2], strict=True):
        props, key = split_v1_content(
            exercise.type,
            exercise.content or {},
            item_id=item_id,
            bloom_level=REQUIRED_BLOOM[item_id],
        )
        items.append(props)
        answer_key[item_id] = key

    constructed = [ex for ex in exercises if _value(ex.type) in CONSTRUCTED_TYPES]
    if constructed:
        props, key = split_v1_content(
            constructed[0].type,
            constructed[0].content or {},
            item_id=ITEM_C,
            bloom_level="apply",
        )
        items.append(props)
        answer_key[ITEM_C] = key
    elif requires_tiebreak(criticality):
        # No constructed item to confirm with, and on a critical node selected-response
        # can never master. Refuse the sample instead of silently building a probe
        # whose best possible verdict is "learning".
        return [], {}

    return items, answer_key


def is_diagnostic_probe(profile: Any | None) -> bool:
    """The declared novice's first probe is shown but not scored (§7.1).

    Without this, the first thing the product does to somebody who has just declared
    they have no experience is hand them N x 2 guaranteed failures before a single line
    of content. It does not persist failures, does not score mastery and does not
    consume the single scored attempt.
    """
    if profile is None:
        return False
    experience = _value(getattr(profile, "experience_level", "unknown"))
    completed = getattr(profile, "nodes_completed", 0) or 0
    return experience == "none" and completed == 0


# --- results -----------------------------------------------------------------


class ProbeRow(Protocol):
    """The columns of ``node_probes`` a caller of this service may read.

    ``answer_key`` is **not** a member, on purpose: the row the service hands back
    is typed as this protocol, so reaching for the key does not type-check. It is
    the static half of the promise in §5.2 rule 5; the runtime half is
    ``ProbeSessionRead``, which enumerates what may be serialized.

    The answer flow (``submit_answer``) needs the real key and reads it from the row
    it is given — that is inside the service, where the key belongs.
    """

    id: Any
    node_id: Any
    schema_version: int
    attempt_no: int
    items: list
    answers: list
    score: float | None
    mastered: bool | None
    tiebreak_used: bool
    scored: bool
    completed_at: Any


@dataclass(frozen=True)
class ProbeSession:
    """What ``POST /nodes/{node_id}/probe`` needs to answer with.

    ``probe`` is the ORM row narrowed to ``ProbeRow``: the service still needs the
    real object (the next call grades against it), but nothing outside this module
    is typed to see ``answer_key``. **Never return this dataclass from a route** —
    return ``ProbeSessionRead.from_session(...)``, which is the only projection that
    guarantees the key does not travel (``src/schemas/probe.py``).
    """

    probe: ProbeRow | None
    items: list[dict]
    reused: bool
    verdict: ProbeVerdict | None
    diagnostic: bool

    def to_read(self):
        """The response body for this session, answer key excluded by construction."""
        from src.schemas.probe import ProbeSessionRead

        return ProbeSessionRead.from_session(self)


@dataclass(frozen=True)
class ProbeAnswerOutcome:
    """What ``POST /nodes/{node_id}/probe/answer`` needs to answer with (§11.3).

    ``verdict`` stays ``None`` until every required item is answered.
    """

    item_id: str
    score: float
    passed: bool
    verdict: ProbeVerdict | None
    estimate: float | None
    next_item_id: str | None
    render_hint: RenderHint | None
    transition: Transition | None = None
    feedback: str | None = None
    error_kind: str | None = None


# --- injected collaborators, typed structurally ------------------------------


class ProbeRepoLike(Protocol):
    async def get_scored(self, *, user_id: Any, node_id: Any, schema_version: int) -> Any: ...
    async def latest(self, *, user_id: Any, node_id: Any) -> Any: ...
    async def next_attempt_no(self, *, user_id: Any, node_id: Any) -> int: ...
    async def create(self, **kwargs: Any) -> Any: ...
    async def supersede(self, probe: Any) -> Any: ...
    async def update(self, obj: Any, **kwargs: Any) -> Any: ...


class AttemptRepoLike(Protocol):
    async def record(self, **kwargs: Any) -> Any: ...
    async def count_failures_for_item(
        self, *, user_id: Any, node_id: Any, item_id: str
    ) -> int: ...


class StateRepoLike(Protocol):
    async def get_or_create(self, *, user_id: Any, node_id: Any, mastery: float) -> Any: ...
    async def apply_transition(self, state: Any, transition: Transition) -> Any: ...


class ExerciseSourceLike(Protocol):
    async def list(self, **kwargs: Any) -> tuple[Sequence[Any], int]: ...


class ProbeService:
    """Serves and grades the pre-assessment.

    ``llm`` is the ``runtime_fast`` service used only as the last resort of §7.1;
    ``open_llm`` is the ``eval``-purpose service used to grade a ``practical_case``
    tie-break. Both may be ``None``: without them the service simply refuses to
    generate (and grades open answers with the deterministic fallback), never attempts
    a network call.
    """

    def __init__(
        self,
        *,
        probe_repo: ProbeRepoLike,
        attempt_repo: AttemptRepoLike,
        state_repo: StateRepoLike,
        exercise_repo: ExerciseSourceLike | None = None,
        llm: Any | None = None,
        open_llm: Any | None = None,
    ) -> None:
        self.probe_repo = probe_repo
        self.attempt_repo = attempt_repo
        self.state_repo = state_repo
        self.exercise_repo = exercise_repo
        self.llm = llm
        self.open_llm = open_llm

    # --- opening the probe --------------------------------------------------

    async def start_probe(
        self,
        *,
        user_id: uuid.UUID,
        node: Any,
        schema_version: int,
        profile: Any | None = None,
        user_skill_level: object | None = None,
        source_context: str = "",
        reprobe: bool = False,
        now: datetime | None = None,
    ) -> ProbeSession:
        """Open (or re-open) the probe for one node.

        Transition 1 of §7.3 happens here: requesting the probe moves the node to
        ``probing``, stamps ``first_seen_at`` and seeds ``mastery`` with the prior from
        ``user_skills``.
        """
        moment = now or datetime.now(timezone.utc)
        prior = mastery_prior(user_skill_level)
        state = await self.state_repo.get_or_create(
            user_id=user_id, node_id=node.id, mastery=prior
        )

        existing = await self.probe_repo.get_scored(
            user_id=user_id, node_id=node.id, schema_version=schema_version
        )

        if reprobe:
            await self._authorize_reprobe(state=state, existing=existing, now=moment)
        elif existing is not None:
            # The stored verdict is served; no new hand is dealt (§3.4).
            return self._session_for(existing, node=node)
        elif _value(state.state) in (LEARNING, MASTERED, NEEDS_REVIEW):
            # Past the probe with no scored row: the diagnostic probe of §7.1. The
            # probe is over for this node until a re-probe is authorized.
            latest = await self.probe_repo.latest(user_id=user_id, node_id=node.id)
            closed: ProbeVerdict = (
                "mastered" if _value(state.state) == MASTERED else "learning"
            )
            return ProbeSession(
                probe=latest,
                items=[],
                reused=True,
                verdict=closed,
                diagnostic=bool(latest is not None and not latest.scored),
            )

        items, answer_key, model = await self.build_items(
            node=node, source_context=source_context
        )
        diagnostic = is_diagnostic_probe(profile)
        attempt_no = await self.probe_repo.next_attempt_no(user_id=user_id, node_id=node.id)
        probe = await self.probe_repo.create(
            user_id=user_id,
            node_id=node.id,
            schema_version=schema_version,
            attempt_no=attempt_no,
            items=items,
            answer_key=answer_key,
            answers=[],
            scored=not diagnostic,
            model=model,
        )

        if _value(state.state) != PROBING:
            # A re-probe keeps the mastery already earned; a first open seeds the prior.
            seed = prior if _value(state.state) == NOT_STARTED else state.mastery
            await self.state_repo.apply_transition(state, transition_open_node(prior=seed))

        return ProbeSession(
            probe=probe,
            items=served_items(items, criticality=node.criticality, tiebreak_used=False),
            reused=False,
            verdict=None,
            diagnostic=diagnostic,
        )

    async def _authorize_reprobe(self, *, state: Any, existing: Any, now: datetime) -> None:
        """Re-probe only from ``needs_review`` and only 7 days after the last one (§3.4)."""
        latest = existing
        if latest is None:
            latest = await self.probe_repo.latest(
                user_id=state.user_id, node_id=state.node_id
            )
        completed_at = getattr(latest, "completed_at", None) if latest is not None else None
        if not may_reprobe(state=state.state, completed_at=completed_at, now=now):
            raise ConflictError(
                "A node can only be re-probed from 'needs_review' and at least "
                "7 days after the previous probe was completed.",
                field="state",
            )
        if latest is not None and latest.scored:
            await self.probe_repo.supersede(latest)

    def _session_for(self, probe: ProbeRow, *, node: Any) -> ProbeSession:
        verdict: ProbeVerdict | None = None
        if probe.completed_at is not None:
            verdict = "mastered" if probe.mastered else "learning"
        return ProbeSession(
            probe=probe,
            items=served_items(
                probe.items,
                criticality=node.criticality,
                tiebreak_used=probe.tiebreak_used,
            ),
            reused=True,
            verdict=verdict,
            diagnostic=not probe.scored,
        )

    # --- item sources ------------------------------------------------------

    async def build_items(
        self, *, node: Any, source_context: str = ""
    ) -> tuple[list[dict], dict, str | None]:
        """The three sources of §7.1, in order. Returns ``(items, answer_key, model)``."""
        if node.probe_items:
            items = list(node.probe_items)
            answer_key = dict(node.probe_answer_key or {})
            validate_probe_items(items, answer_key, node.criticality)
            return items, answer_key, None

        if node.seed_lesson_id is not None and self.exercise_repo is not None:
            items, answer_key = seed_probe_items(
                await self._seed_exercises(node), criticality=node.criticality
            )
            if items:
                validate_probe_items(items, answer_key, node.criticality)
                self._write_back(node, items, answer_key)
                return items, answer_key, None

        if self.llm is None:
            raise LLMError(
                f"Cannot build a probe for node {node.id}: it has no pre-generated "
                "items, its seed lesson cannot fill the slots, and no LLM is "
                "configured. Pre-generate the probe when validating the schema."
            )

        items, answer_key = await self._generate_items(node=node, source_context=source_context)
        self._write_back(node, items, answer_key)
        return items, answer_key, getattr(self.llm, "model", None)

    async def _seed_exercises(self, node: Any) -> Sequence[Any]:
        from src.models import Exercise  # local import: keeps this module ORM-free at top level

        rows, _total = await self.exercise_repo.list(  # type: ignore[union-attr]
            filters=[Exercise.lesson_id == node.seed_lesson_id],
            order_by=Exercise.position,
            limit=50,
        )
        return rows

    async def _generate_items(self, *, node: Any, source_context: str) -> tuple[list[dict], dict]:
        user_prompt = build_probe_prompt(
            title=node.title,
            summary=node.summary,
            outcome=getattr(node, "outcome", None),
            criticality=_value(node.criticality),
            source_context=source_context,
        )
        raw = await self.llm.complete(
            PROBE_GENERATOR_SYSTEM,
            user_prompt,
            temperature=PROBE_TEMPERATURE,
            max_tokens=PROBE_MAX_TOKENS,
            json_mode=True,
        )
        return parse_probe_response(raw, criticality=node.criticality)

    @staticmethod
    def _write_back(node: Any, items: list[dict], answer_key: dict) -> None:
        """Persist the items on the node so the next employee pays nothing (§7.1).

        Assignment (not in-place mutation) so SQLAlchemy sees the jsonb change; the
        caller's transaction commits it.
        """
        node.probe_items = items
        node.probe_answer_key = answer_key

    # --- answering ---------------------------------------------------------

    async def submit_answer(
        self,
        *,
        user_id: uuid.UUID,
        node: Any,
        probe: Any,
        item_id: str,
        answer: Any,
        profile: Any | None = None,
        user_skill_level: object | None = None,
        latency_ms: int | None = None,
        now: datetime | None = None,
    ) -> ProbeAnswerOutcome:
        """Grade one probe item and, when the last required one lands, close the probe."""
        moment = now or datetime.now(timezone.utc)
        if probe.completed_at is not None:
            raise ConflictError("This probe is already closed.", field="probe_id")

        items = {item.get("item_id"): item for item in probe.items}
        item = items.get(item_id)
        if item is None:
            raise ValidationError(f"Item {item_id!r} is not part of this probe", field="item_id")

        answers = list(probe.answers or [])
        if any(entry.get("item_id") == item_id for entry in answers):
            raise ConflictError(f"Item {item_id!r} was already answered.", field="item_id")

        key_entry = (probe.answer_key or {}).get(item_id)
        result = await self._grade(item, key_entry, answer)
        error_kind = None if result.passed else classify_error(item, key_entry, answer)

        answers.append(
            {
                "item_id": item_id,
                "answer": answer,
                "score": result.score,
                "passed": result.passed,
            }
        )
        probe.answers = answers  # reassign: jsonb change tracking

        if probe.scored:
            # A diagnostic probe persists no failures (§7.1), so no attempt row.
            await self.attempt_repo.record(
                user_id=user_id,
                node_id=node.id,
                probe_id=probe.id,
                item_id=item_id,
                item_type=item_type_of(item),
                bloom_level=item.get("bloom_level"),
                answer=answer if isinstance(answer, dict) else {"answer": answer},
                score=result.score,
                passed=result.passed,
                latency_ms=latency_ms,
                feedback=result.feedback,
            )

        scores = {entry["item_id"]: float(entry["score"]) for entry in answers}
        return await self._advance(
            user_id=user_id,
            node=node,
            probe=probe,
            items=items,
            scores=scores,
            item_id=item_id,
            result=result,
            error_kind=error_kind,
            profile=profile,
            user_skill_level=user_skill_level,
            now=moment,
        )

    async def _grade(self, item: dict, key_entry: dict | None, answer: Any) -> Any:
        item_type = item_type_of(item)
        if item_type in ("practical_case", "dialogue") and self.open_llm is not None:
            from src.services.llm_grading import grade_open_answer

            return await grade_open_answer(
                self.open_llm, item_type, content_for(item, key_entry), answer
            )
        return grade_item(item, key_entry, answer)

    async def _advance(
        self,
        *,
        user_id: uuid.UUID,
        node: Any,
        probe: Any,
        items: dict,
        scores: dict,
        item_id: str,
        result: Any,
        error_kind: str | None,
        profile: Any | None,
        user_skill_level: object | None,
        now: datetime,
    ) -> ProbeAnswerOutcome:
        """Decide what the verdict is (or is not yet) after one answer."""
        threshold = threshold_for(node.criticality, getattr(node, "mastery_threshold", None))
        has_c = ITEM_C in items

        if not all(slot in scores for slot in SELECTED_ITEMS):
            # Still mid-probe. §9.1: fire the background render as soon as "mastered"
            # is out of reach, which for a single answer means item A was failed.
            unreachable = item_id == ITEM_A and scores[ITEM_A] < APPLY_FLOOR
            missing = [slot for slot in SELECTED_ITEMS if slot not in scores]
            return ProbeAnswerOutcome(
                item_id=item_id,
                score=result.score,
                passed=result.passed,
                verdict=None,
                estimate=None,
                next_item_id=missing[0],
                render_hint="prefetch" if unreachable else None,
                feedback=result.feedback,
                error_kind=error_kind,
            )

        score_a, score_b = scores[ITEM_A], scores[ITEM_B]
        initial, estimate = probe_verdict(score_a, score_b, node.criticality, threshold)

        if ITEM_C in scores:
            verdict, score = tiebreak_verdict(
                score_a, score_b, scores[ITEM_C], node.criticality, threshold
            )
            from_tiebreak = True
        elif initial == "tiebreak":
            if has_c:
                probe.tiebreak_used = True
                return ProbeAnswerOutcome(
                    item_id=item_id,
                    score=result.score,
                    passed=result.passed,
                    verdict=None,
                    estimate=estimate,
                    next_item_id=ITEM_C,
                    render_hint=None,
                    feedback=result.feedback,
                    error_kind=error_kind,
                )
            # No constructed item to confirm with. Mastery is NOT granted: on a
            # critical node it may never come from selected response (§7.2 rule 3),
            # and elsewhere an unconfirmed 0.6 is exactly the doubt this rule exists
            # to resolve. The learner works the node; nothing is lost but a shortcut.
            logger.warning(
                "Probe %s fell into the doubt band with no tie-break item; "
                "resolving as 'learning'.",
                probe.id,
            )
            verdict, score, from_tiebreak = "learning", estimate, False
        else:
            verdict, score, from_tiebreak = initial, estimate, False

        return await self._close(
            user_id=user_id,
            node=node,
            probe=probe,
            verdict=verdict,
            score=score,
            initial=initial,
            score_a=score_a,
            from_tiebreak=from_tiebreak,
            item_id=item_id,
            result=result,
            error_kind=error_kind,
            profile=profile,
            user_skill_level=user_skill_level,
            now=now,
        )

    async def _close(
        self,
        *,
        user_id: uuid.UUID,
        node: Any,
        probe: Any,
        verdict: ProbeVerdict,
        score: float,
        initial: ProbeVerdict,
        score_a: float,
        from_tiebreak: bool,
        item_id: str,
        result: Any,
        error_kind: str | None,
        profile: Any | None,
        user_skill_level: object | None,
        now: datetime,
    ) -> ProbeAnswerOutcome:
        probe.score = score
        probe.mastered = verdict == MASTERED
        probe.completed_at = now

        transition = None
        if probe.scored:
            band = scaffold_band_for(
                experience_level=getattr(profile, "experience_level", None),
                verdict=initial,
                score_a=score_a,
            )
            state = await self.state_repo.get_or_create(
                user_id=user_id, node_id=node.id, mastery=mastery_prior(user_skill_level)
            )
            transition = transition_close_probe(
                verdict=verdict,
                score=score,
                prior=state.mastery,
                from_tiebreak=from_tiebreak,
                scaffold_band=band,
            )
            await self.state_repo.apply_transition(state, transition)

        return ProbeAnswerOutcome(
            item_id=item_id,
            score=result.score,
            passed=result.passed,
            verdict=verdict,
            estimate=score,
            next_item_id=None,
            render_hint="skip" if verdict == MASTERED else "prefetch",
            transition=transition,
            feedback=result.feedback,
            error_kind=error_kind,
        )
