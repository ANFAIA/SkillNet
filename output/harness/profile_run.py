"""Run one bounded learner journey against the live SkillNet API.

The script is deliberately defensive: a failed user, enrollment, render or
answer is recorded and does not prevent the JSON artifact from being written.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import ApiFailure, Client, poll_until, run_psql

QUIZ_RE = re.compile(
    r"QuizItem\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,"
)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_courses(admin: Client, wanted: list[str]) -> list[dict[str, Any]]:
    rows = admin.expect("GET", "/courses?limit=100").get("items", [])
    result = []
    for title in wanted:
        exact = next((row for row in rows if row.get("title") == title), None)
        if exact is None:
            needle = title.casefold()
            exact = next((row for row in rows if needle in row.get("title", "").casefold()), None)
        if exact is not None and exact.get("delivery_mode") == "dynamic":
            result.append(exact)
    return result


def ensure_user(admin: Client, profile: dict[str, Any], password: str) -> dict[str, Any]:
    email = profile["email"]
    status, payload = admin.request("GET", f"/users?search={email}&limit=100")
    if status == 200:
        found = next((row for row in payload.get("items", []) if row.get("email") == email), None)
        if found:
            return found
    status, payload = admin.request(
        "POST", "/users", {"email": email, "full_name": profile["full_name"], "password": password}
    )
    if status in (200, 201):
        return payload
    if status == 409:
        status, payload = admin.request("GET", f"/users?search={email}&limit=100")
        found = next((row for row in payload.get("items", []) if row.get("email") == email), None)
        if found:
            return found
    raise ApiFailure(f"no se pudo crear usuario {email}: {status} {payload}")


def submit_profile(user: Client, profile: dict[str, Any]) -> dict[str, Any] | None:
    body = {
        "role_title": profile.get("role_title"),
        "sector": profile.get("sector"),
        "goal": profile.get("goal"),
        "experience_level": profile.get("experience_level"),
        "preset": profile.get("preset"),
        "accessibility": profile.get("accessibility"),
        "learning_preferences": profile.get("learning_preferences"),
    }
    status, payload = user.request("POST", "/onboarding", body)
    if status in (200, 201):
        return payload
    # An already completed onboarding is not a journey failure.
    status, payload = user.request("GET", "/users/me/learner-profile")
    return payload if status == 200 else None


def set_profile_counters(profile: dict[str, Any], user_id: str, workdir: str) -> str:
    nodes = int(profile.get("nodes_completed", 0))
    vector = profile.get("format_vector") or {"texto": 0, "ejercicio": 0, "codigo": 0, "dato": 0}
    vector_json = json.dumps(vector, separators=(",", ":")).replace("'", "''")
    email = str(profile["email"]).replace("'", "''")
    sql = (
        "UPDATE learner_profiles SET nodes_completed = %d, format_vector = '%s'::jsonb "
        "WHERE user_id = (SELECT id FROM users WHERE email = '%s');"
        % (nodes, vector_json, email)
    )
    return run_psql(sql, workdir=workdir)


def answer_payload(item_type: str, strategy: str, index: int) -> dict[str, Any]:
    if strategy == "random":
        index = random.randint(0, 3)
    elif strategy == "last":
        index = 3
    elif strategy == "mixed" and index % 2:
        index = random.randint(0, 3)
    if item_type == "true_false":
        return {"answer": bool(index % 2 == 0)}
    if item_type == "fill_blank":
        return {"answers": ["respuesta"]}
    if item_type == "order_steps":
        return {"order": [0, 1, 2]}
    return {"selected": index}


def render_node(user: Client, node_id: str, force: bool, deadline: float) -> dict[str, Any]:
    accepted = user.expect("POST", f"/nodes/{node_id}/render", {"force": force}, ok=(202,))
    if accepted.get("cached") and accepted.get("render_id"):
        status, payload = user.request("GET", f"/nodes/{node_id}/render")
        if status == 200:
            return {"accepted": accepted, "render": payload}

    def check():
        return user.request("GET", f"/nodes/{node_id}/render")

    status, payload = poll_until(
        deadline,
        2.0,
        check,
        lambda result: result[0] == 200 or result[0] not in (202,),
    )
    if status != 200:
        raise ApiFailure(f"render {node_id} termino en {status}: {payload}")
    return {"accepted": accepted, "render": payload}


def run_profile(profile: dict[str, Any], config: dict[str, Any], out_dir: Path, workdir: str) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "profile": profile,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "errors": [],
        "courses": [],
    }
    base_url = config.get("base_url", "http://localhost:3000")
    admin_email = config.get("admin_email", "admin@skillnet.dev")
    admin_password = os.environ.get("SKILLNET_TEST_ADMIN_PASSWORD")
    password = os.environ.get("SKILLNET_TEST_EMPLOYEE_PASSWORD")
    if not admin_password or not password:
        raise ApiFailure(
            "set SKILLNET_TEST_ADMIN_PASSWORD and SKILLNET_TEST_EMPLOYEE_PASSWORD before running"
        )

    try:
        admin = Client(base_url, timeout=float(config.get("http_timeout", 25)))
        admin.login(admin_email, admin_password)
        employee = ensure_user(admin, profile, password)
        result["user"] = {key: employee.get(key) for key in ("id", "email", "full_name", "role")}
        user = Client(base_url, timeout=float(config.get("http_timeout", 25)))
        user.login(profile["email"], password)
        result["profile_saved"] = submit_profile(user, profile)
        try:
            set_profile_counters(profile, str(employee["id"]), workdir)
            result["profile_counters_updated"] = True
        except Exception as exc:  # noqa: BLE001 - artifact must survive setup failures
            result["errors"].append(f"profile counters: {exc}")
            result["profile_counters_updated"] = False

        requested_courses = list(config.get("courses", []))
        courses = resolve_courses(admin, requested_courses)
        result["resolved_courses"] = [{"id": row.get("id"), "title": row.get("title")} for row in courses]
        if requested_courses and len(courses) != len(requested_courses):
            resolved_titles = [str(row.get("title", "")) for row in courses]
            result["errors"].append(
                "requested dynamic courses did not all resolve: "
                f"requested={requested_courses!r}, resolved={resolved_titles!r}"
            )
        for course in courses:
            course_result: dict[str, Any] = {"course": course, "nodes": [], "errors": []}
            try:
                status, payload = admin.request(
                    "POST", "/enrollments", {"course_id": course["id"], "user_ids": [employee["id"]]}
                )
                course_result["enrollment_status"] = status
                course_result["enrollment"] = payload
                if status not in (200, 201, 409):
                    course_result["errors"].append(f"enrollment {status}: {payload}")
            except Exception as exc:  # noqa: BLE001
                course_result["errors"].append(f"enrollment: {exc}")
            try:
                node_list = user.expect("GET", f"/courses/{course['id']}/nodes")
                course_result["node_list"] = node_list
                nodes = node_list.get("nodes", [])[: int(config.get("max_nodes", 4))]
                for node in nodes:
                    node_result: dict[str, Any] = {"node": node}
                    try:
                        captured = render_node(
                            user,
                            str(node["id"]),
                            bool(config.get("force", False)),
                            float(config.get("render_timeout", 180)),
                        )
                        render = captured["render"]
                        program = str(render.get("program", ""))
                        node_result["render"] = {
                            "accepted": captured["accepted"],
                            "meta": {key: render.get(key) for key in ("render_id", "ui_format", "status", "backend", "cached")},
                            "program": program,
                            "characters": len(program),
                            "lines": len(program.splitlines()),
                            "components": sorted(set(re.findall(r"\b([A-Z][A-Za-z0-9_]*)\s*\(", program))),
                            "quiz_items": [
                                {"item_id": item_id, "item_type": item_type}
                                for item_id, item_type in QUIZ_RE.findall(program)
                            ],
                        }
                        strategy = config.get("answer_strategy", profile.get("answer_strategy", "none"))
                        answers = []
                        if strategy != "none":
                            for index, item in enumerate(node_result["render"]["quiz_items"]):
                                answer = answer_payload(item["item_type"], strategy, index)
                                status, response = user.request(
                                    "POST",
                                    f"/nodes/{node['id']}/answer",
                                    {
                                        "render_id": render["render_id"],
                                        "item_id": item["item_id"],
                                        "answer": answer,
                                    },
                                )
                                answers.append({"item": item, "status": status, "response": response})
                        node_result["answers"] = answers
                    except Exception as exc:  # noqa: BLE001
                        node_result["error"] = str(exc)
                    course_result["nodes"].append(node_result)
            except Exception as exc:  # noqa: BLE001
                course_result["errors"].append(f"node list/journey: {exc}")
            result["courses"].append(course_result)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"fatal setup: {exc}")
    result["duration_s"] = round(time.monotonic() - started, 3)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    save_json(out_dir / "journey.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--slug", default="", help="selecciona un perfil dentro de una lista")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workdir", default=str(Path.cwd()))
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    if isinstance(profile, list):
        if not args.slug:
            raise SystemExit("--slug es obligatorio cuando el fichero contiene una lista")
        profile = next((row for row in profile if row.get("slug") == args.slug), None)
        if profile is None:
            raise SystemExit(f"perfil no encontrado: {args.slug}")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = run_profile(profile, config, args.out, args.workdir)
    print(json.dumps({"slug": profile.get("slug"), "errors": len(result["errors"]), "duration_s": result["duration_s"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
