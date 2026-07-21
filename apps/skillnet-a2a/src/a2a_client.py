"""Simple A2A client for testing the SkillNet agent."""

import httpx


class SkillNetA2AClient:
    """Client that sends messages to the SkillNet A2A server."""

    def __init__(self, url: str = "http://localhost:5000", auth_key: str = "") -> None:
        self.url = url.rstrip("/")
        self.auth_key = auth_key

    async def get_agent_card(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.url}/.well-known/agent.json")
            resp.raise_for_status()
            return resp.json()

    async def send_message(self, text: str, task_id: str | None = None) -> dict:
        headers = {}
        if self.auth_key:
            headers["Authorization"] = f"Bearer {self.auth_key}"

        payload = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "id": task_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                },
            },
            "id": 1,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def get_task(self, task_id: str) -> dict:
        headers = {}
        if self.auth_key:
            headers["Authorization"] = f"Bearer {self.auth_key}"

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"id": task_id},
            "id": 2,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
