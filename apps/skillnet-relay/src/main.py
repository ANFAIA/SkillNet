"""The relay: instances send reports here, the judge reads them, GitHub gets the issue."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from src.config import Settings, settings
from src.judge import Complete, llm_complete
from src.service import process
from src.store import Store

log = logging.getLogger(__name__)

#: A report still queued after this many seconds was cut short by a restart.
REQUEUE_AFTER = 60.0


class ReportIn(BaseModel):
    # A random id the instance made for itself. It groups reports and counts duplicates; it
    # proves nothing, which is why the address is limited too.
    instance_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)
    page_path: str | None = Field(default=None, max_length=500)
    environment: str | None = Field(default=None, max_length=300)


class ReportQueued(BaseModel):
    receipt: str
    status: str


class ReportOut(BaseModel):
    status: str
    severity: str | None = None
    reason: str | None = None
    issue_url: str | None = None


def _client_ip(request: Request) -> str:
    # Behind the reverse proxy the real address is the first of X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_app(
    cfg: Settings = settings, complete: Complete | None = None, http: Any = None
) -> FastAPI:
    store = Store(cfg.DB_PATH)
    judge_complete = complete or llm_complete(cfg)
    owned_http = http is None
    client = http or httpx.AsyncClient(timeout=15)

    async def run(receipt: str) -> None:
        await process(receipt, cfg=cfg, store=store, complete=judge_complete, http=client)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        store.purge_raw(cfg.RAW_RETENTION_DAYS)
        for receipt in store.stale_queued(REQUEUE_AFTER):
            await run(receipt)
        yield
        if owned_http:
            await client.aclose()

    app = FastAPI(title="SkillNet bug-report relay", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/reports", response_model=ReportQueued, status_code=202)
    async def submit(report: ReportIn, request: Request, background: BackgroundTasks):
        if not cfg.ENABLED:
            raise HTTPException(503, "Reports are switched off")

        instance = str(report.instance_id)
        title, body = report.title.strip(), report.body.strip()
        if not title or not body:
            raise HTTPException(422, "Add a title and a description")

        text_hash = hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()
        existing = store.find_duplicate(instance, text_hash)
        if existing:
            return ReportQueued(receipt=existing, status=store.get(existing)["status"])

        ip_hash = hashlib.sha256(_client_ip(request).encode()).hexdigest()
        if store.count_global() >= cfg.GLOBAL_DAILY_CAP:
            raise HTTPException(429, "The relay is full for today, try again tomorrow")
        if store.count_instance(instance) >= cfg.INSTANCE_DAILY_CAP:
            raise HTTPException(429, "This instance has reached today's limit")
        if store.count_ip(ip_hash) >= cfg.IP_HOURLY_CAP:
            raise HTTPException(429, "Too many reports from this address, try later")

        receipt = uuid.uuid4().hex
        store.insert(
            receipt=receipt,
            instance_id=instance,
            ip_hash=ip_hash,
            text_hash=text_hash,
            title=title,
            body=body,
            page_path=report.page_path,
            # One line, so it cannot add markdown or a second paragraph to the issue.
            environment=" ".join((report.environment or "").split()) or None,
        )
        background.add_task(run, receipt)
        return ReportQueued(receipt=receipt, status="queued")

    @app.get("/v1/reports/{receipt}", response_model=ReportOut)
    async def status(receipt: str) -> ReportOut:
        row = store.get(receipt)
        if row is None:
            raise HTTPException(404, "No such report")
        verdict = row["verdict"] or {}
        return ReportOut(
            status=row["status"],
            severity=verdict.get("severity"),
            reason=verdict.get("reason"),
            issue_url=row["issue_url"],
        )

    return app
