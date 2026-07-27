"""``answer_key`` never leaves the server (§5.2 rule 5, §14.1).

The promise was made in §5.2 and had nothing enforcing it: ``ProbeService`` returned
the whole ``node_probes`` row — key included — to its caller, and the only reason
nothing leaked was that the routes which would serialize it do not exist yet (B5).
"Not exploitable today" is not the same as "closed".

So the test is the serialization test the spec asks for: dump the response model and
assert the key is absent, by field name *and* by value. Reusing the fakes of
``test_probe_reuse`` on purpose — the same objects the rest of the probe suite runs
against, so this cannot pass on a shape the service does not really produce.
"""

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.schemas.probe import ProbeRead, ProbeSessionRead
from src.services.probe_service import ITEM_A, ITEM_B, ProbeSession

from tests.test_probe_reuse import (
    build_service,
    canonical_node,
    make_items,
)

# The strings that must never appear in a response body: the index of the correct
# option and the explanation stored beside it.
LEAKY_VALUES = ("explanation", "30 dias con ticket", "Sin ticket, vale")


def _keys(payload) -> set[str]:
    """Every key at every depth of a dumped model."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(key)
            found |= _keys(value)
    elif isinstance(payload, list):
        for value in payload:
            found |= _keys(value)
    return found


async def _session() -> ProbeSession:
    items, key = make_items()
    node = canonical_node(probe_items=items, probe_answer_key=key)
    service, *_ = build_service(node=node)
    return await service.start_probe(
        user_id=uuid.uuid4(), node=node, schema_version=1
    )


# --------------------------------------------------------------- the model itself


def test_probe_read_has_no_answer_key_field() -> None:
    assert "answer_key" not in ProbeRead.model_fields
    assert "answer_key" not in ProbeSessionRead.model_fields


def test_probe_read_refuses_an_answer_key_that_is_handed_to_it() -> None:
    """``extra="forbid"``: a future caller cannot smuggle the column back in."""
    with pytest.raises(PydanticValidationError):
        ProbeRead(
            id=uuid.uuid4(),
            node_id=uuid.uuid4(),
            schema_version=1,
            attempt_no=1,
            scored=True,
            answer_key={ITEM_A: {"correct": 1}},
        )


# ------------------------------------------------------- the real service output


async def test_the_serialized_session_never_carries_the_answer_key() -> None:
    """The test §14.1 promises: dump the response model, assert the key is gone."""
    read = (await _session()).to_read()

    dumped = read.model_dump(mode="json")
    assert "answer_key" not in _keys(dumped)

    raw = json.dumps(dumped, ensure_ascii=False)
    assert "answer_key" not in raw
    for leak in LEAKY_VALUES:
        assert leak not in raw


async def test_the_served_items_carry_no_correct_option() -> None:
    """Twice-stripped: another column, and ``public_props`` on the way out."""
    read = (await _session()).to_read()

    assert [item["item_id"] for item in read.items][:2] == [ITEM_A, ITEM_B]
    for item in read.items:
        assert "correct" not in item
        assert "blanks" not in item
        assert "explanation" not in item
        # The question and the options do travel: that is the probe.
        assert "item_id" in item


async def test_the_session_still_carries_the_key_internally_for_grading() -> None:
    """The fix narrows what is *served*, not what the service can grade with.

    Without this, "no answer_key anywhere" could be satisfied by breaking grading.
    """
    session = await _session()
    assert session.probe is not None
    assert getattr(session.probe, "answer_key")[ITEM_A]["correct"] == 1


async def test_a_session_with_no_row_serializes_without_exploding() -> None:
    """The 'past the probe, nothing stored' path of ``start_probe``."""
    read = ProbeSession(
        probe=None, items=[], reused=True, verdict="mastered", diagnostic=False
    ).to_read()

    assert read.probe is None
    assert read.verdict == "mastered"
    assert "answer_key" not in json.dumps(read.model_dump(mode="json"))


async def test_the_read_model_reports_what_the_client_needs() -> None:
    """A narrowed type that dropped a needed field would be a different bug."""
    session = await _session()
    read = session.to_read()

    assert read.probe is not None
    assert read.probe.id == session.probe.id
    assert read.probe.schema_version == 1
    assert read.probe.attempt_no == 1
    assert read.probe.scored is True
    assert read.reused is False
    assert read.diagnostic is False
    assert read.verdict is None
