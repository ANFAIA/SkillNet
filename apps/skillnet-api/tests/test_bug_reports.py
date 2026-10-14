"""Bug report triage: the judge, the GitHub calls and the outcome stored on the row.

No database and no network: the model and GitHub are fakes, the session is a stub.
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.config import settings
from src.models import BugReport
from src.services import bug_report_service as svc


class FakeLLM:
    def __init__(self, verdict: dict | Exception) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str, **kwargs) -> str:
        self.calls.append((system, user))
        if isinstance(self.verdict, Exception):
            raise self.verdict
        return json.dumps(self.verdict)


class FakeResponse:
    def __init__(self, status: int = 200, payload=None) -> None:
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self, issues=None, post_status: int = 201) -> None:
        self.issues = issues or []
        self.post_status = post_status
        self.posts: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        return FakeResponse(200, self.issues)

    async def post(self, url, json=None, **kwargs):
        self.posts.append((url, json))
        return FakeResponse(
            self.post_status, {"html_url": "https://github.com/o/r/issues/99"}
        )


class FakeRepo:
    async def count_for_issue(self, url: str) -> int:
        return 1


GENUINE = {
    "genuine": True,
    "severity": "medium",
    "kind": "bug",
    "title": "Save button does nothing",
    "body": "Steps: open a lesson, press save.",
    "reason": "A feature is broken.",
    "duplicate_of": None,
}


def _row() -> BugReport:
    return BugReport(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        title="save",
        body="it does not save",
        page_path="/lesson/1",
        environment=None,
        status="pending",
    )


@pytest.fixture
def github(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "t")
    monkeypatch.setattr(settings, "GITHUB_REPO", "o/r")


@pytest.fixture
def no_github(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(settings, "GITHUB_REPO", "")


async def test_a_duplicate_number_the_model_was_not_shown_is_ignored():
    llm = FakeLLM({**GENUINE, "duplicate_of": 7})
    verdict = await svc.judge(
        llm,
        title="t",
        body="b",
        page_path=None,
        candidates=[{"number": 3, "title": "other"}],
    )
    assert verdict.duplicate_of is None


async def test_a_duplicate_of_a_listed_issue_is_kept():
    llm = FakeLLM({**GENUINE, "duplicate_of": 3})
    verdict = await svc.judge(
        llm,
        title="t",
        body="b",
        page_path=None,
        candidates=[{"number": 3, "title": "other"}],
    )
    assert verdict.duplicate_of == 3
    assert "#3: other" in llm.calls[0][1]


async def test_a_genuine_report_becomes_an_issue(github):
    row, http = _row(), FakeHTTP()
    await svc._process(FakeRepo(), row, FakeLLM(GENUINE), http)
    assert row.status == "issue"
    assert row.issue_url == "https://github.com/o/r/issues/99"
    url, body = http.posts[0]
    assert url.endswith("/repos/o/r/issues")
    assert body["labels"] == ["bug-report", "severity:medium", "bug"]


async def test_a_report_that_repeats_an_open_issue_comments_on_it(github):
    row = _row()
    http = FakeHTTP(
        issues=[{"number": 5, "title": "Save broken", "html_url": "https://x/5"}]
    )
    await svc._process(FakeRepo(), row, FakeLLM({**GENUINE, "duplicate_of": 5}), http)
    assert row.status == "issue"
    assert row.issue_url == "https://x/5"
    url, body = http.posts[0]
    assert url.endswith("/issues/5/comments")
    assert "2 people" in body["body"]


async def test_pull_requests_are_not_duplicate_candidates(github):
    http = FakeHTTP(
        issues=[{"number": 1, "title": "a PR", "pull_request": {}, "html_url": "u"}]
    )
    assert await svc.open_issues(http) == []


async def test_a_report_that_is_not_genuine_is_discarded_and_not_filed(github):
    row, http = _row(), FakeHTTP()
    llm = FakeLLM({**GENUINE, "genuine": False, "reason": "Spam."})
    await svc._process(FakeRepo(), row, llm, http)
    assert row.status == "discarded"
    assert row.verdict["reason"] == "Spam."
    assert http.posts == []


async def test_without_github_a_genuine_report_waits_for_an_admin(no_github):
    row, http = _row(), FakeHTTP()
    await svc._process(FakeRepo(), row, FakeLLM(GENUINE), http)
    assert row.status == "pending"
    assert row.verdict["title"] == GENUINE["title"]
    assert http.posts == []


async def test_a_model_failure_marks_the_report_failed(github):
    row = _row()
    await svc._process(FakeRepo(), row, FakeLLM(RuntimeError("down")), FakeHTTP())
    assert row.status == "failed"
    assert "judged" in row.verdict["error"]


async def test_a_github_refusal_marks_the_report_failed_and_keeps_the_write_up(github):
    row = _row()
    await svc._process(FakeRepo(), row, FakeLLM(GENUINE), FakeHTTP(post_status=403))
    assert row.status == "failed"
    assert row.verdict["title"] == GENUINE["title"]
    assert row.issue_url is None


async def test_an_admin_files_a_discarded_report_without_the_genuine_check(github):
    row = _row()
    row.status = "discarded"
    row.verdict = {**GENUINE, "genuine": False}
    llm, http = FakeLLM(RuntimeError("must not be called")), FakeHTTP()
    url = await svc.file_by_admin(FakeRepo(), row, llm, http=http)
    assert url == "https://github.com/o/r/issues/99"
    assert row.status == "issue"
    assert llm.calls == []


def test_github_is_configured_only_with_a_token_and_a_repo(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "t")
    monkeypatch.setattr(settings, "GITHUB_REPO", "no-slash")
    assert svc.github_configured() is False
    monkeypatch.setattr(settings, "GITHUB_REPO", "o/r")
    assert svc.github_configured() is True


async def test_process_report_never_raises_even_when_the_database_does():
    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("database is down")

        async def __aexit__(self, *exc):
            return False

    await svc.process_report(
        uuid.uuid4(), FakeLLM(GENUINE), session_factory=BrokenSession
    )
