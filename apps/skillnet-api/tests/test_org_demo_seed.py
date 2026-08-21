"""Unit tests for the pre-baked, no-LLM onboarding demo course seed.

Runs under ``-m "not integration"``: no database and no API key. A lightweight fake
session stands in for ``AsyncSession`` so the idempotency contract is exercised without
Postgres.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.models import Course, CourseNode, NodeRender, NodeRenderStatus
from src.render.spec import parse_spec
from src.services.org_demo_seed import (
    PREVIEW_BUCKETS,
    build_showcase_specs,
    demo_preview_cache_key,
    seed_org_demo,
)


class _Result:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _FakeSession:
    """Records added rows and assigns ids on flush, like the DB's ``gen_random_uuid()``."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def execute(self, _statement: object) -> _Result:
        # The seed issues exactly one query: the existing-demo-course lookup.
        demo = next(
            (
                obj
                for obj in self.added
                if isinstance(obj, Course) and getattr(obj, "is_demo", False)
            ),
            None,
        )
        return _Result(demo)


def test_showcase_programs_validate_against_spec() -> None:
    """Both pre-baked programs parse and satisfy the §5.2 UISpec contract."""
    specs = build_showcase_specs()
    assert set(specs) == set(PREVIEW_BUCKETS)
    for _bucket, (spec, ui_format) in specs.items():
        assert spec.format == ui_format
        # Re-validating the dumped spec proves it is a legal UISpec end to end.
        revalidated = parse_spec(spec.model_dump(mode="json"))
        assert revalidated.root
        assert revalidated.component(revalidated.root) is not None


@pytest.mark.asyncio
async def test_seed_is_idempotent() -> None:
    """Running twice yields exactly one demo course, three nodes and two variants."""
    session = _FakeSession()
    org = SimpleNamespace(id=uuid.uuid4())

    first = await seed_org_demo(session, org)
    assert first is not None
    assert first.is_demo is True

    courses = [obj for obj in session.added if isinstance(obj, Course)]
    nodes = [obj for obj in session.added if isinstance(obj, CourseNode)]
    renders = [obj for obj in session.added if isinstance(obj, NodeRender)]
    assert len(courses) == 1
    assert len(nodes) == 3
    assert len(renders) == len(PREVIEW_BUCKETS) == 2

    # The showcase renders are keyed per bucket and kept out of the shared cache.
    showcase = min(nodes, key=lambda n: n.position)
    keys = {r.cache_key for r in renders}
    assert keys == {
        demo_preview_cache_key(showcase.id, bucket) for bucket in PREVIEW_BUCKETS
    }
    for render in renders:
        assert render.is_preview is True
        assert render.status is NodeRenderStatus.READY
        assert render.dialect
        assert render.node_id == showcase.id

    second = await seed_org_demo(session, org)
    assert second is first
    # Nothing new was added on the second run.
    assert len([obj for obj in session.added if isinstance(obj, Course)]) == 1
    assert len([obj for obj in session.added if isinstance(obj, CourseNode)]) == 3
    assert len([obj for obj in session.added if isinstance(obj, NodeRender)]) == 2
