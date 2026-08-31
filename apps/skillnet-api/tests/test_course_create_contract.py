"""``POST /courses`` spreads its body into the service, so the two must stay in sync.

The route does this::

    payload = body.model_dump(exclude={"document_ids"})
    course = await service.create(org_id=..., created_by=..., **payload)

Which means **every field added to ``CourseCreate`` becomes a keyword argument of
``CourseService.create``**, and forgetting the other half is not a type error, not a lint
error and not a unit-test failure: it is a ``TypeError`` at runtime, on the one request
that creates a course. Adding ``language`` to the schema did exactly that, and the only
thing that caught it was the integration suite — which needs a live PostgreSQL and so does
not run in CI.

This test is the cheap half of that check. It compares the two signatures directly, with
no database, no network and no route, so the next person to add a course field finds out
in the fast suite instead of in production.
"""

import inspect

from src.schemas.course import CourseCreate
from src.services.course_service import CourseService

#: What the route strips out before spreading, and therefore what the service is allowed
#: not to know about. Kept in sync by the test below, so it cannot rot silently either.
ROUTE_EXCLUDES = {"document_ids"}


def test_every_course_create_field_is_a_service_argument() -> None:
    spread = set(CourseCreate.model_fields) - ROUTE_EXCLUDES
    accepted = set(inspect.signature(CourseService.create).parameters)
    missing = sorted(spread - accepted)
    assert not missing, (
        f"CourseService.create does not accept {missing}, but POST /courses spreads "
        f"CourseCreate into it. Every request to create a course would raise TypeError. "
        f"Add the argument to the service, or exclude the field in the route and here."
    )


def test_the_route_still_spreads_the_body() -> None:
    """The premise of the test above, checked rather than assumed.

    If the route stops spreading — say it starts listing arguments one by one — this file
    is guarding a contract that no longer exists, and should be deleted rather than left
    passing for the wrong reason.
    """
    source = inspect.getsource(__import__("src.routes.courses", fromlist=["create_course"]).create_course)
    assert "**payload" in source
    assert 'exclude={"document_ids"}' in source, (
        "The route's exclude set changed; update ROUTE_EXCLUDES to match."
    )
