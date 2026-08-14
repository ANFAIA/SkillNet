"""Bounded smoke test for course-level generation (v1 or v2)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import ApiFailure, Client, poll_until


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def wait_job(client: Client, job_id: str, deadline: float) -> dict[str, Any]:
    # v2 has an intentional intermediate terminal state: the proposal is ready
    # for human review before validation. v1 uses completed/succeeded.
    terminal = {"completed", "succeeded", "schema_proposed", "failed", "error"}
    status, payload = poll_until(
        deadline,
        2.0,
        lambda: client.request("GET", f"/generation-jobs/{job_id}"),
        lambda result: result[0] == 200 and str(result[1].get("status", "")).lower() in terminal,
    )
    if status != 200:
        raise ApiFailure(f"job {job_id}: HTTP {status}: {payload}")
    return payload


def run(kind: str, idea: dict[str, Any], config: dict[str, Any], out: Path) -> dict[str, Any]:
    started = time.monotonic()
    result: dict[str, Any] = {
        "kind": kind,
        "idea": idea,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "errors": [],
    }
    client = Client(config.get("base_url", "http://localhost:3000"), timeout=float(config.get("http_timeout", 25)))
    try:
        admin_password = os.environ.get("SKILLNET_TEST_ADMIN_PASSWORD")
        if not admin_password:
            raise ApiFailure("set SKILLNET_TEST_ADMIN_PASSWORD before running")
        client.login(config.get("admin_email", "admin@skillnet.dev"), admin_password)
        document = client.expect("POST", "/documents/from-idea", {"title": idea["title"], "idea": idea["idea"]})
        result["document"] = document
        doc_id = document["id"]
        status, document = poll_until(
            float(config.get("document_timeout", 120)), 2.0,
            lambda: client.request("GET", f"/documents/{doc_id}"),
            lambda item: item[0] == 200 and item[1].get("status") in {"ready", "failed"},
        )
        if status != 200 or document.get("status") != "ready":
            raise ApiFailure(f"documento no listo: {status} {document}")
        result["document_ready"] = document
        course = client.expect("POST", "/courses", {
            "title": idea["course_title"],
            "description": idea.get("description", ""),
            "source_document_id": doc_id,
        })
        result["course"] = course
        course_id = course["id"]
        if kind == "v1":
            accepted = client.expect("POST", f"/courses/{course_id}/generate", {})
            result["generation_accepted"] = accepted
            result["generation_job"] = wait_job(client, accepted["job_id"], float(config.get("generation_timeout", 300)))
            result["course_detail"] = client.expect("GET", f"/courses/{course_id}")
        else:
            accepted = client.expect("POST", f"/courses/{course_id}/schema/propose", {"source_document_id": doc_id, "intent_density": int(idea.get("intent_density", 2))})
            result["schema_accepted"] = accepted
            result["schema_job"] = wait_job(client, accepted["job_id"], float(config.get("schema_timeout", 300)))
            schema = client.expect("GET", f"/courses/{course_id}/schema")
            result["schema_before_review"] = schema
            for node in schema.get("nodes", []):
                node_id = node.get("id")
                if node_id:
                    status, payload = client.request("POST", f"/courses/{course_id}/schema/nodes/{node_id}/review")
                    if status not in (200, 201):
                        result["errors"].append(f"review {node_id}: {status} {payload}")
            status, payload = client.request("POST", f"/courses/{course_id}/schema/validate")
            result["schema_validation"] = {"status": status, "payload": payload}
            result["schema_after_validation"] = client.expect("GET", f"/courses/{course_id}/schema")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(str(exc))
    result["duration_s"] = round(time.monotonic() - started, 3)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    write(out / "course-generation.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("v1", "v2"), required=True)
    parser.add_argument("--idea", type=Path, required=True)
    parser.add_argument("--slug", default="", help="selecciona una idea dentro de una lista")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    idea = json.loads(args.idea.read_text(encoding="utf-8"))
    if isinstance(idea, list):
        if not args.slug:
            raise SystemExit("--slug es obligatorio cuando el fichero contiene una lista")
        idea = next((row for row in idea if row.get("slug") == args.slug), None)
        if idea is None:
            raise SystemExit(f"idea no encontrada: {args.slug}")
    result = run(args.kind, idea, json.loads(args.config.read_text(encoding="utf-8")), args.out)
    print(json.dumps({"kind": result["kind"], "errors": len(result["errors"]), "duration_s": result["duration_s"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
