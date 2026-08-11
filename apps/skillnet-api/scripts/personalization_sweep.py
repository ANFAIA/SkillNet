#!/usr/bin/env python
"""Barrido API reproducible de personalizacion de renders v2.

Por defecto es conservador: inicia sesion, lee perfil/matriculas/cursos/nodos y
captura solamente renders ya fijados. ``--force`` solicita y repinea un render por
usuario/nodo, puede gastar tokens y altera el render activo; por eso exige ademas
``--confirm-force I_UNDERSTAND``.

Las contrasenas se reciben por variables de entorno y nunca se escriben en la
salida. Ejemplo desde ``apps/skillnet-api``::

    $env:SWEEP_PASSWORD='...'
    uv run python scripts/personalization_sweep.py --base-url http://localhost:5174 \
      --output ../../docs/evidencia-testing/api-sweep

Para regenerar (operacion con coste y mutacion)::

    uv run python scripts/personalization_sweep.py --force \
      --confirm-force I_UNDERSTAND
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import http.cookiejar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_USERS = (
    "aitana.souto@laespiga.example",
    "diego.varela@laespiga.example",
    "lucia.fernandez@laespiga.example",
)
DEFAULT_COURSE = "Servicio de sala: de la comanda al cobro"
COMPONENT_RE = re.compile(r"(?m)^\s*([A-Z][A-Za-z0-9_]*)\s*\(")


class ApiFailure(RuntimeError):
    pass


@dataclass
class Client:
    base_url: str
    timeout: float = 30.0

    def __post_init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(
        self, method: str, path: str, body: Any = None, *, form: bool = False
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
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                detail = {"detail": raw.decode(errors="replace")[:500]}
            return exc.code, detail
        except urllib.error.URLError as exc:
            raise ApiFailure(f"No se pudo conectar con {url}: {exc.reason}") from exc

    def expect(self, method: str, path: str, body: Any = None, *, form: bool = False) -> Any:
        status, payload = self.request(method, path, body, form=form)
        if not 200 <= status < 300:
            raise ApiFailure(f"{method} {path} -> {status}: {payload}")
        return payload


def normalize_program(program: str) -> str:
    return "\n".join(line.rstrip() for line in program.strip().splitlines())


def summarize_render(render: dict[str, Any]) -> dict[str, Any]:
    program = normalize_program(str(render.get("program", "")))
    return {
        "render_id": render.get("render_id"),
        "node_id": render.get("node_id"),
        "ui_format": render.get("ui_format"),
        "status": render.get("status"),
        "backend": render.get("backend"),
        "cached": render.get("cached"),
        "sha256": hashlib.sha256(program.encode()).hexdigest(),
        "characters": len(program),
        "components": sorted(set(COMPONENT_RE.findall(program))),
        "program": program,
    }


def compare_programs(left: str, right: str) -> dict[str, Any]:
    a, b = normalize_program(left), normalize_program(right)
    diff = "\n".join(
        difflib.unified_diff(
            a.splitlines(), b.splitlines(), fromfile="left", tofile="right", lineterm=""
        )
    )
    return {
        "identical": a == b,
        "similarity": round(difflib.SequenceMatcher(None, a, b).ratio(), 4),
        "diff": diff,
    }


def safe_profile(profile: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "role_title",
        "goal",
        "experience_level",
        "preset",
        "accessibility",
        "nodes_completed",
        "format_vector",
        "onboarding_completed_at",
        "onboarding_skipped",
    }
    return {key: profile.get(key) for key in sorted(allowed) if key in profile}


def wait_for_render(client: Client, node_id: str, timeout: float, interval: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        status, payload = client.request("GET", f"/nodes/{node_id}/render")
        if status == 200:
            return payload
        if status != 202:
            raise ApiFailure(f"GET /nodes/{node_id}/render -> {status}: {payload}")
        if time.monotonic() >= deadline:
            raise ApiFailure(f"Timeout esperando el render del nodo {node_id}")
        time.sleep(interval)


def capture_user(
    *, base_url: str, email: str, password: str, course_title: str, force: bool,
    timeout: float, poll_interval: float
) -> dict[str, Any]:
    client = Client(base_url, timeout=min(timeout, 30.0))
    client.expect("POST", "/auth/login", {"username": email, "password": password}, form=True)
    me = client.expect("GET", "/auth/me")
    profile_status, profile = client.request("GET", "/users/me/learner-profile")
    enrollments = client.expect("GET", "/enrollments?limit=100").get("items", [])
    selected = next((row for row in enrollments if row.get("course_title") == course_title), None)
    if selected is None:
        raise ApiFailure(f"{email} no esta matriculado en {course_title!r}")
    course_id = str(selected["course_id"])
    course = client.expect("GET", f"/courses/{course_id}")
    node_list = client.expect("GET", f"/courses/{course_id}/nodes")
    snapshots: list[dict[str, Any]] = []
    for node in node_list.get("nodes", []):
        node_id = str(node["id"])
        request_meta = None
        if force:
            request_meta = client.expect("POST", f"/nodes/{node_id}/render", {"force": True})
        status, render = client.request("GET", f"/nodes/{node_id}/render")
        if status == 202 and force:
            render = wait_for_render(client, node_id, timeout, poll_interval)
            status = 200
        item = {"node": node, "render_request": request_meta, "render": None}
        if status == 200:
            item["render"] = summarize_render(render)
        elif status == 202:
            item["render_pending"] = render
        else:
            item["render_error"] = {"status": status, "body": render}
        snapshots.append(item)
    return {
        "email": email,
        "user": {key: me.get(key) for key in ("id", "email", "full_name", "role")},
        "profile": safe_profile(profile) if profile_status == 200 else None,
        "profile_status": profile_status,
        "course": course,
        "enrollment": selected,
        "node_list": node_list,
        "snapshots": snapshots,
    }


def build_comparisons(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    by_email = {
        user["email"]: {
            str(item["node"]["id"]): item for item in user.get("snapshots", [])
        }
        for user in users
    }
    for left_index, left in enumerate(users):
        for right in users[left_index + 1 :]:
            shared = sorted(set(by_email[left["email"]]) & set(by_email[right["email"]]))
            for node_id in shared:
                a = by_email[left["email"]][node_id]
                b = by_email[right["email"]][node_id]
                if not a.get("render") or not b.get("render"):
                    continue
                result = compare_programs(a["render"]["program"], b["render"]["program"])
                comparisons.append({
                    "left": left["email"], "right": right["email"], "node_id": node_id,
                    "node_title": a["node"].get("title"), **result,
                })
    return comparisons


def markdown_report(payload: dict[str, Any]) -> str:
    lines = ["# Barrido API de personalizacion", "", f"Fecha: {payload['created_at']}", ""]
    lines += ["## Perfiles", ""]
    for user in payload["users"]:
        lines.append(f"- {user['email']}: `{json.dumps(user.get('profile'), ensure_ascii=False)}`")
    lines += ["", "## Comparaciones", "", "| Nodo | Perfiles | Igual | Similitud |", "|---|---|---:|---:|"]
    for row in payload["comparisons"]:
        lines.append(
            f"| {row['node_title']} | {row['left']} ↔ {row['right']} | "
            f"{'sí' if row['identical'] else 'no'} | {row['similarity']:.4f} |"
        )
    if not payload["comparisons"]:
        lines.append("| — | No hay pares con renders fijados | — | — |")
    lines += ["", "Los diffs completos y programas OpenUI estan en `sweep.json`.", ""]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:5174")
    parser.add_argument("--output", type=Path, default=Path("personalization-sweep"))
    parser.add_argument("--course", default=DEFAULT_COURSE)
    parser.add_argument("--users", nargs="+", default=list(DEFAULT_USERS))
    parser.add_argument("--password-env", default="SWEEP_PASSWORD")
    parser.add_argument("--force", action="store_true", help="Regenera y repinea; cuesta y muta estado")
    parser.add_argument("--confirm-force", default="")
    parser.add_argument("--render-timeout", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.force and args.confirm_force != "I_UNDERSTAND":
        raise SystemExit("--force exige --confirm-force I_UNDERSTAND")
    password = os.environ.get(args.password_env)
    if not password:
        raise SystemExit(f"Define la variable {args.password_env}; no pases secretos como argumentos")
    users = []
    for email in args.users:
        print(f"Capturando {email}...")
        users.append(capture_user(
            base_url=args.base_url, email=email, password=password,
            course_title=args.course, force=args.force, timeout=args.render_timeout,
            poll_interval=args.poll_interval,
        ))
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "course": args.course,
        "force": args.force,
        "users": users,
    }
    payload["comparisons"] = build_comparisons(users)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "sweep.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(f"Resultados: {args.output.resolve()}")


if __name__ == "__main__":
    main()
