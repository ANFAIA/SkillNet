"""The relay end to end, with a fake model and a fake GitHub and a real SQLite file."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from src.config import Settings
from src.main import create_app
from src.store import Store

TOKEN = "ghp_this_must_never_leave_the_relay"

GENUINE = {
    "genuine": True,
    "severity": "medium",
    "kind": "bug",
    "title": "Save button does nothing",
    "body": "Steps: open a lesson, press save.",
    "reason": "A feature is broken.",
    "duplicate_of": None,
}


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
        return FakeResponse(self.post_status, {"html_url": "https://github.com/o/r/issues/99"})


def fake_model(verdict):
    calls: list[str] = []

    async def complete(system: str, user: str) -> str:
        calls.append(user)
        if isinstance(verdict, Exception):
            raise verdict
        return json.dumps(verdict)

    complete.calls = calls
    return complete


def make_cfg(tmp_path, **overrides) -> Settings:
    values = {
        "DB_PATH": str(tmp_path / "relay.db"),
        "GITHUB_TOKEN": TOKEN,
        "GITHUB_REPO": "o/r",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def report(**overrides) -> dict:
    body = {
        "instance_id": str(uuid.uuid4()),
        "title": "save",
        "body": "it does not save",
        "page_path": "/lesson/1",
        "environment": "Firefox 130",
    }
    body.update(overrides)
    return body


@pytest.fixture
def make(tmp_path):
    def build(verdict=GENUINE, http=None, **cfg_overrides):
        cfg = make_cfg(tmp_path, **cfg_overrides)
        complete = fake_model(verdict)
        http = http or FakeHTTP()
        app = create_app(cfg, complete=complete, http=http)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        return client, http, complete, cfg, app

    return build


async def test_a_genuine_report_becomes_an_issue(make):
    client, http, _, _, _ = make()
    sent = await client.post("/v1/reports", json=report())
    assert sent.status_code == 202
    receipt = sent.json()["receipt"]

    got = (await client.get(f"/v1/reports/{receipt}")).json()
    assert got["status"] == "issue"
    assert got["issue_url"] == "https://github.com/o/r/issues/99"
    assert got["severity"] == "medium"
    url, body = http.posts[0]
    assert url.endswith("/repos/o/r/issues")
    assert body["labels"] == ["bug-report", "severity:medium", "bug"]


async def test_the_token_never_appears_in_any_response(make):
    client, _, _, _, _ = make()
    sent = await client.post("/v1/reports", json=report())
    receipt = sent.json()["receipt"]
    status = await client.get(f"/v1/reports/{receipt}")
    health = await client.get("/health")
    for response in (sent, status, health):
        assert TOKEN not in response.text


async def test_the_status_does_not_return_the_reporter_text(make):
    client, _, _, _, _ = make()
    receipt = (await client.post("/v1/reports", json=report(body="secret detail"))).json()["receipt"]
    assert "secret detail" not in (await client.get(f"/v1/reports/{receipt}")).text


async def test_a_troll_is_discarded_and_nothing_reaches_github(make):
    client, http, _, _, _ = make({**GENUINE, "genuine": False, "reason": "Spam."})
    receipt = (await client.post("/v1/reports", json=report())).json()["receipt"]
    got = (await client.get(f"/v1/reports/{receipt}")).json()
    assert got["status"] == "discarded"
    assert got["reason"] == "Spam."
    assert http.posts == []


async def test_a_report_that_repeats_an_open_issue_comments_on_it(make):
    http = FakeHTTP(issues=[{"number": 5, "title": "Save broken", "html_url": "https://x/5"}])
    client, http, _, _, _ = make({**GENUINE, "duplicate_of": 5}, http=http)
    receipt = (await client.post("/v1/reports", json=report())).json()["receipt"]
    got = (await client.get(f"/v1/reports/{receipt}")).json()
    assert got["issue_url"] == "https://x/5"
    url, body = http.posts[0]
    assert url.endswith("/issues/5/comments")
    assert "1 people" not in body["body"]


async def test_a_model_failure_marks_the_report_failed(make):
    client, _, _, _, _ = make(RuntimeError("down"))
    receipt = (await client.post("/v1/reports", json=report())).json()["receipt"]
    assert (await client.get(f"/v1/reports/{receipt}")).json()["status"] == "failed"


async def test_a_github_refusal_marks_the_report_failed(make):
    client, _, _, _, _ = make(http=FakeHTTP(post_status=403))
    receipt = (await client.post("/v1/reports", json=report())).json()["receipt"]
    assert (await client.get(f"/v1/reports/{receipt}")).json()["status"] == "failed"


async def test_without_a_token_the_report_fails_instead_of_waiting(make):
    client, http, _, _, _ = make(GITHUB_TOKEN="")
    receipt = (await client.post("/v1/reports", json=report())).json()["receipt"]
    assert (await client.get(f"/v1/reports/{receipt}")).json()["status"] == "failed"
    assert http.posts == []


async def test_the_same_text_from_the_same_instance_is_not_judged_twice(make):
    client, _, complete, _, _ = make()
    one = report()
    first = (await client.post("/v1/reports", json=one)).json()["receipt"]
    second = (await client.post("/v1/reports", json=one)).json()["receipt"]
    assert first == second
    assert len(complete.calls) == 1


async def test_an_instance_cannot_send_more_than_its_daily_cap(make):
    client, _, _, _, _ = make(INSTANCE_DAILY_CAP=2)
    instance = str(uuid.uuid4())
    for n in range(2):
        ok = await client.post("/v1/reports", json=report(instance_id=instance, title=f"t{n}"))
        assert ok.status_code == 202
    over = await client.post("/v1/reports", json=report(instance_id=instance, title="t3"))
    assert over.status_code == 429


async def test_one_address_is_limited_even_across_instances(make):
    client, _, _, _, _ = make(IP_HOURLY_CAP=2)
    for n in range(2):
        assert (await client.post("/v1/reports", json=report(title=f"t{n}"))).status_code == 202
    assert (await client.post("/v1/reports", json=report(title="t3"))).status_code == 429


async def test_the_global_cap_bounds_the_total(make):
    client, _, _, _, _ = make(GLOBAL_DAILY_CAP=1)
    assert (await client.post("/v1/reports", json=report(title="a"))).status_code == 202
    assert (await client.post("/v1/reports", json=report(title="b"))).status_code == 429


async def test_the_off_switch_refuses_everything(make):
    client, http, complete, _, _ = make(ENABLED=False)
    assert (await client.post("/v1/reports", json=report())).status_code == 503
    assert http.posts == [] and complete.calls == []


async def test_a_bad_instance_id_or_an_empty_report_is_refused(make):
    client, _, _, _, _ = make()
    assert (await client.post("/v1/reports", json=report(instance_id="nope"))).status_code == 422
    assert (await client.post("/v1/reports", json=report(body="   "))).status_code == 422
    assert (await client.post("/v1/reports", json=report(title=""))).status_code == 422


async def test_an_unknown_receipt_is_a_404(make):
    client, _, _, _, _ = make()
    assert (await client.get("/v1/reports/doesnotexist")).status_code == 404


async def test_a_report_cut_short_by_a_restart_is_judged_again_at_startup(make):
    client, http, _, cfg, app = make()
    store = Store(cfg.DB_PATH)
    store.insert(
        receipt="r1", instance_id="i", ip_hash="h", text_hash="t",
        title="save", body="it does not save", created_at=1.0,
    )
    async with app.router.lifespan_context(app):
        pass
    assert store.get("r1")["status"] == "issue"
    assert len(http.posts) == 1


async def test_old_reports_lose_their_text_but_keep_the_outcome(make):
    client, _, _, cfg, app = make(RAW_RETENTION_DAYS=1)
    store = Store(cfg.DB_PATH)
    store.insert(
        receipt="old", instance_id="i", ip_hash="h", text_hash="t",
        title="save", body="it does not save", status="issue",
        issue_url="https://github.com/o/r/issues/1", created_at=1.0,
    )
    async with app.router.lifespan_context(app):
        pass
    row = store.get("old")
    assert row["body"] == "" and row["title"] == ""
    assert row["issue_url"] == "https://github.com/o/r/issues/1"
