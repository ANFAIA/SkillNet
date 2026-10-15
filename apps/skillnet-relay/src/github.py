"""The GitHub side. The token is read here and nowhere else, and never logged or returned."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.config import Settings
from src.judge import CANDIDATE_TITLE_CHARS, MAX_CANDIDATES, Verdict

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
COMMENT_BODY_CHARS = 600


def configured(cfg: Settings) -> bool:
    return bool(cfg.GITHUB_TOKEN and "/" in cfg.GITHUB_REPO)


def _headers(cfg: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def open_issues(cfg: Settings, http: Any) -> list[dict[str, Any]]:
    """Open issues for the duplicate check (pull requests skipped). Empty when GitHub cannot be
    asked: the report is then filed as a new issue."""
    try:
        response = await http.get(
            f"{GITHUB_API}/repos/{cfg.GITHUB_REPO}/issues",
            params={"state": "open", "per_page": 50},
            headers=_headers(cfg),
        )
        if response.status_code >= 300:
            return []
        found = [
            {
                "number": int(i["number"]),
                "title": str(i["title"])[:CANDIDATE_TITLE_CHARS],
                "url": i.get("html_url"),
            }
            for i in response.json()
            if "pull_request" not in i
        ]
        return found[:MAX_CANDIDATES]
    except Exception as exc:
        # The exception text can carry the request; the type is enough.
        log.warning("could not list open issues: %s", type(exc).__name__)
        return []


async def comment_on_issue(
    cfg: Settings, http: Any, number: int, verdict: Verdict, reporters: int
) -> None:
    text = (
        f"Another person reported this: {verdict.title.strip() or 'Bug report'}. "
        f"{verdict.body.strip()[:COMMENT_BODY_CHARS]}"
    )
    if reporters > 1:
        text += f"\n\nReported by {reporters} people so far."
    response = await http.post(
        f"{GITHUB_API}/repos/{cfg.GITHUB_REPO}/issues/{number}/comments",
        json={"body": text},
        headers=_headers(cfg),
    )
    if response.status_code >= 300:
        raise RuntimeError(f"GitHub answered {response.status_code}")


async def create_issue(
    cfg: Settings, http: Any, verdict: Verdict, page_path: str | None, environment: str | None
) -> str:
    lines = [verdict.body.strip()]
    if page_path:
        lines += ["", f"Page: `{page_path}`"]
    if environment:
        lines += ["", f"Environment: {environment}"]
    lines += ["", "_Reported from a SkillNet instance and triaged automatically._"]
    response = await http.post(
        f"{GITHUB_API}/repos/{cfg.GITHUB_REPO}/issues",
        json={
            "title": verdict.title.strip() or "Bug report",
            "body": "\n".join(lines),
            "labels": ["bug-report", f"severity:{verdict.severity}", verdict.kind],
        },
        headers=_headers(cfg),
    )
    if response.status_code >= 300:
        # The status is enough to act on; the body may echo the request.
        raise RuntimeError(f"GitHub answered {response.status_code}")
    return response.json()["html_url"]


async def publish(
    cfg: Settings,
    http: Any,
    verdict: Verdict,
    *,
    page_path: str | None,
    environment: str | None,
    candidates: list[dict[str, Any]],
    reporters_of: Callable[[str], int],
) -> str:
    """A comment on the issue it repeats, or a new issue. Returns the issue URL."""
    if verdict.duplicate_of is not None:
        known = {c["number"]: c.get("url") for c in candidates}
        url = (
            known.get(verdict.duplicate_of)
            or f"https://github.com/{cfg.GITHUB_REPO}/issues/{verdict.duplicate_of}"
        )
        await comment_on_issue(cfg, http, verdict.duplicate_of, verdict, reporters_of(url) + 1)
        return url
    return await create_issue(cfg, http, verdict, page_path, environment)
