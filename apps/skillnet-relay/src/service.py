"""Judging a stored report and filing it. Never raises: the outcome is on the row."""

from __future__ import annotations

import logging
from typing import Any

from src import github
from src.config import Settings
from src.judge import Complete, judge
from src.store import Store

log = logging.getLogger(__name__)


async def process(receipt: str, *, cfg: Settings, store: Store, complete: Complete, http: Any):
    try:
        row = store.get(receipt)
        if row is None or row["status"] != "queued":
            return
        if not github.configured(cfg):
            store.update(receipt, status="failed", verdict={"error": "The relay is not configured"})
            return

        candidates = await github.open_issues(cfg, http)
        try:
            verdict = await judge(
                complete,
                title=row["title"],
                body=row["body"],
                page_path=row["page_path"],
                environment=row["environment"],
                candidates=candidates,
            )
        except Exception as exc:
            log.warning("could not judge report %s: %s", receipt, type(exc).__name__)
            store.update(receipt, status="failed", verdict={"error": "The report could not be judged"})
            return

        data = verdict.model_dump()
        if not verdict.genuine:
            store.update(receipt, status="discarded", verdict=data)
            return
        try:
            url = await github.publish(
                cfg,
                http,
                verdict,
                page_path=row["page_path"],
                environment=row["environment"],
                candidates=candidates,
                reporters_of=store.count_for_issue,
            )
        except Exception as exc:
            log.warning("could not file report %s: %s", receipt, type(exc).__name__)
            store.update(receipt, status="failed", verdict={**data, "error": "GitHub refused the issue"})
            return
        store.update(receipt, status="issue", verdict=data, issue_url=url)
    except Exception:
        log.exception("could not process report %s", receipt)
