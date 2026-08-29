"""The admin dashboard reports no mark, and there is nothing left that could compute one.

``GET /stats`` carried ``avg_score`` — ``AVG(enrollments.score)`` over the org — until
2026-08-29. It was removed rather than narrowed, and the reason is the product's and not
the query's: **there are no exams here**. Nothing grades a course, so an average mark had
nothing to average. The column made it worse rather than causing it, by holding two
different quantities on one 0..1 scale — the completed-lessons fraction on the v1 path,
and mean node mastery in the v2 rows written before that date — which no query can
separate after the fact.

Two assertions, because the field and the query fail independently. Dropping the field and
leaving the ``AVG`` would keep an org-wide scan running for a number nobody reads;
recomputing it under another name would put the same mixture back on the dashboard with a
new label. ``enrollments.score`` itself stays, and this file says nothing about it: it is
the history of enrollments already closed, and the v1 rule still writes it.
"""

from __future__ import annotations

import inspect

from src.routes import stats as stats_route
from src.schemas.stats import StatsResponse


def test_the_stats_payload_carries_no_average_mark() -> None:
    assert "avg_score" not in StatsResponse.model_fields
    # Not just this one name: any mark-shaped field is the same mistake relabelled.
    assert not [
        name
        for name in StatsResponse.model_fields
        if "score" in name or "mark" in name or "grade" in name
    ]


def test_the_stats_query_no_longer_averages_enrollment_scores() -> None:
    """The read is gone too, not merely unreported.

    Deliberately over the source of the route module rather than over a response: the
    endpoint needs a live org to answer, and what is being pinned is that the column is
    not consulted at all — an assertion about the query, which a response cannot make.
    """
    source = inspect.getsource(stats_route)
    assert "Enrollment.score" not in source
    assert "func.avg" not in source
