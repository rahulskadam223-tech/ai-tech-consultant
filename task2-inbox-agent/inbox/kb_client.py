"""HTTP client for Task 1 (the knowledge brain). Never imports Task 1 code."""
from __future__ import annotations

import httpx

from .models import KBResult


class KBUnavailable(Exception):
    """Task 1 is down or returned an error."""


class KnowledgeBrain:
    def __init__(self, base_url: str, timeout: float = 90.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/health")
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            raise KBUnavailable(f"Task 1 not reachable at {self.base_url}: {e}") from e

    async def query(self, question: str) -> KBResult:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(f"{self.base_url}/query", json={"question": question})
                r.raise_for_status()
                return KBResult.model_validate(r.json())
        except httpx.HTTPStatusError as e:
            raise KBUnavailable(f"Task 1 /query failed ({e.response.status_code}): {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise KBUnavailable(f"Task 1 not reachable at {self.base_url}: {e}") from e

    async def escalate(self, question: str) -> int:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/escalations", json={"question": question})
            r.raise_for_status()
            return int(r.json()["id"])
