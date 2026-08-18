"""Async HTTP client for the SkillNet external API."""

import uuid

import httpx

from src.config import settings


class SkillNetClient:
    """Thin wrapper over SkillNet /ext/v1/ endpoints."""

    def __init__(self) -> None:
        self._base = settings.API_URL.rstrip("/")
        self._headers = {"Authorization": f"Bearer {settings.SKILLNET_API_KEY}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            headers=self._headers,
            timeout=30.0,
        )

    async def who_knows(self, skill: str, min_level: str | None = None) -> dict:
        async with self._client() as client:
            params: dict = {"skill": skill}
            if min_level:
                params["min_level"] = min_level
            resp = await client.get("/ext/v1/skills/who-knows", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_gap(self) -> dict:
        async with self._client() as client:
            resp = await client.get("/ext/v1/skills/gaps")
            resp.raise_for_status()
            return resp.json()

    async def verify_skill(
        self, user_id: str, skill_name: str, level: str, source: str = "manual"
    ) -> dict:
        async with self._client() as client:
            resp = await client.post(
                "/ext/v1/skills/verify",
                json={
                    "user_id": user_id,
                    "skill_name": skill_name,
                    "level": level,
                    "source": source,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def list_skills(self) -> dict:
        async with self._client() as client:
            resp = await client.get("/ext/v1/skills")
            resp.raise_for_status()
            return resp.json()

    async def get_user_skills(self, user_id: str) -> dict:
        async with self._client() as client:
            resp = await client.get(f"/ext/v1/skills/users/{user_id}/skills")
            resp.raise_for_status()
            return resp.json()

    async def create_course(
        self,
        title: str,
        *,
        document_id: str | None = None,
        intent_density: int = 3,
        enroll_user_id: str | None = None,
        generate_artifacts: list[str] | None = None,
    ) -> dict:
        """Create a course end to end in one call.

        The end-to-end flow (propose schema, generate knowledge packs with retry,
        review, validate, prewarm) runs server-side and can take a few minutes on a
        real provider, so this request uses a long timeout instead of the default 30s.
        """
        payload: dict = {"title": title, "intent_density": intent_density}
        if document_id:
            payload["document_id"] = document_id
        if enroll_user_id:
            payload["enroll_user_id"] = enroll_user_id
        if generate_artifacts:
            payload["generate_artifacts"] = generate_artifacts
        async with httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=600.0
        ) as client:
            resp = await client.post("/ext/v1/courses/full", json=payload)
            resp.raise_for_status()
            return resp.json()
