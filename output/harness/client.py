"""Shared stdlib-only API client for the SkillNet testing harness.

Every call has a hard timeout and poll loops have deadlines: a stuck API must
never hang a round. Errors are raised as ApiFailure and are expected to be
captured into the journey log by the caller.
"""

from __future__ import annotations

import http.cookiejar
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_TIMEOUT = 30.0


class ApiFailure(RuntimeError):
    """An API call returned an unexpected status or could not be made."""

    def __init__(self, message: str, *, status: int | None = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class Client:
    base_url: str
    timeout: float = DEFAULT_TIMEOUT
    jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    def __post_init__(self) -> None:
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        form: bool = False,
        timeout: float | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base_url.rstrip('/')}/api/v1{path}"
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            if form:
                data = urllib.parse.urlencode(body).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                detail = {"detail": raw.decode(errors="replace")[:800]}
            return exc.code, detail
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiFailure(f"{method} {path} sin respuesta: {exc}") from exc

    def expect(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        form: bool = False,
        ok: tuple[int, ...] = (200, 201, 202, 204),
        timeout: float | None = None,
    ) -> Any:
        status, payload = self.request(method, path, body, form=form, timeout=timeout)
        if status not in ok:
            raise ApiFailure(
                f"{method} {path} -> {status}: {json.dumps(payload, ensure_ascii=False)[:600]}",
                status=status,
                body=payload,
            )
        return payload

    def login(self, email: str, password: str) -> None:
        self.expect(
            "POST",
            "/auth/login",
            {"username": email, "password": password},
            form=True,
            ok=(200, 204),
        )


def poll_until(deadline_s: float, interval_s: float, fn, done) -> Any:
    """Call ``fn`` until ``done(result)`` or the deadline. ``fn`` returns (status, payload)."""
    deadline = time.monotonic() + deadline_s
    last = None
    while True:
        last = fn()
        if done(last):
            return last
        if time.monotonic() >= deadline:
            raise ApiFailure(f"timeout de {deadline_s}s agotado; ultimo estado: {str(last)[:300]}")
        time.sleep(interval_s)


def run_psql(sql: str, *, db_service: str = "db", user: str = "skillnet",
             database: str = "skillnet", workdir: str, timeout: float = 25.0) -> str:
    """Run one SQL statement inside the compose db container. Never hangs the round."""
    cmd = [
        "docker", "compose", "exec", "-T", db_service,
        "psql", "-U", user, "-d", database, "-tA", "-c", sql,
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=workdir
    )
    if proc.returncode != 0:
        raise ApiFailure(f"psql fallo: {proc.stderr.strip()[:400]}")
    return proc.stdout.strip()
