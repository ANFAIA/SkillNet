"""SkillNet A2A Server — JSON-RPC 2.0 over HTTP."""

import json
import logging
import uuid

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.agent_card import AGENT_CARD
from src.config import settings
from src.orchestrator import run as orchestrator_run

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillnet-a2a")


async def agent_card(request: Request) -> JSONResponse:
    """Serve the AgentCard at /.well-known/agent.json"""
    return JSONResponse(AGENT_CARD)


def require_auth_key() -> None:
    """Refuse to serve without a bearer token. Called once, at startup.

    The previous behaviour was ``if not A2A_AUTH_KEY: return True``, i.e. an unset token
    meant *authentication disabled*, and the default was unset. That is the wrong
    direction to fail in: this server holds a ``SKILLNET_API_KEY`` scoped
    ``skills:read``/``skills:write``/``users:read``, so an open instance hands those
    privileges to whoever reaches the port.

    Checked here rather than with ``${A2A_AUTH_KEY:?}`` in compose because Compose
    interpolates every service in the file whatever the active profiles are, so a required
    variable on an optional service breaks plain ``docker compose up`` for everybody.
    """
    if not settings.A2A_AUTH_KEY:
        raise RuntimeError(
            "A2A_AUTH_KEY is not set. This server exposes SkillNet data to external "
            "agents and will not start without a bearer token. Generate one with "
            '`python -c "import secrets; print(secrets.token_urlsafe(32))"` and put it in '
            "the .env as A2A_AUTH_KEY."
        )


def _verify_auth(request: Request) -> bool:
    """Verify the bearer token. ``require_auth_key`` guarantees one is configured."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return auth.removeprefix("Bearer ").strip() == settings.A2A_AUTH_KEY


async def jsonrpc_handler(request: Request) -> JSONResponse:
    """Handle JSON-RPC 2.0 requests following the A2A protocol."""
    if not _verify_auth(request):
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized"}, "id": None},
            status_code=401,
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
            status_code=400,
        )

    method = body.get("method", "")
    params = body.get("params", {})
    rpc_id = body.get("id")

    if method == "message/send":
        return await _handle_message_send(params, rpc_id)
    elif method == "tasks/get":
        return await _handle_task_get(params, rpc_id)
    else:
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": rpc_id,
        })


# In-memory task store (good enough for v0)
_tasks: dict[str, dict] = {}


async def _handle_message_send(params: dict, rpc_id: str | int | None) -> JSONResponse:
    """Handle message/send: run the orchestrator and return the result."""
    message = params.get("message", {})
    task_id = params.get("id") or str(uuid.uuid4())

    # Extract text from message parts
    parts = message.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    user_text = " ".join(text_parts).strip()

    if not user_text:
        # Try plain text field
        user_text = message.get("text", "")

    if not user_text:
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": "No text content in message"},
            "id": rpc_id,
        })

    logger.info("Task %s: processing message: %s", task_id, user_text[:100])

    try:
        result_text = await orchestrator_run(user_text)
    except Exception as exc:
        logger.error("Orchestrator failed: %s", exc)
        _tasks[task_id] = {"id": task_id, "status": {"state": "failed"}}
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": f"Agent error: {exc}"},
            "id": rpc_id,
        })

    task = {
        "id": task_id,
        "status": {"state": "completed"},
        "artifacts": [
            {
                "parts": [{"type": "text", "text": result_text}],
            }
        ],
    }
    _tasks[task_id] = task

    return JSONResponse({
        "jsonrpc": "2.0",
        "result": task,
        "id": rpc_id,
    })


async def _handle_task_get(params: dict, rpc_id: str | int | None) -> JSONResponse:
    """Handle tasks/get: return a stored task by ID."""
    task_id = params.get("id", "")
    task = _tasks.get(task_id)
    if task is None:
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": f"Task not found: {task_id}"},
            "id": rpc_id,
        })
    return JSONResponse({"jsonrpc": "2.0", "result": task, "id": rpc_id})


app = Starlette(
    routes=[
        Route("/.well-known/agent.json", agent_card, methods=["GET"]),
        Route("/", jsonrpc_handler, methods=["POST"]),
    ],
    # Fail at startup, not on the first unauthenticated request: a server that is open to
    # everyone must never reach the point of listening.
    on_startup=[require_auth_key],
)


def main() -> None:
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.A2A_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
