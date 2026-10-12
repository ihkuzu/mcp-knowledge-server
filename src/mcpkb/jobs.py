import asyncio
import time

import httpx


class JobError(RuntimeError):
    pass


class InferqClient:
    """Small client for the async-inference-service job API."""

    def __init__(self, base_url: str, timeout: float = 5.0, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, url: str, **kwargs) -> dict:
        try:
            resp = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            raise JobError(f"inference service unreachable: {error.__class__.__name__}") from error
        if resp.status_code == 404:
            raise JobError("job not found")
        if resp.status_code >= 400:
            raise JobError(f"inference service returned {resp.status_code}")
        return resp.json()

    async def submit(self, text: str, idempotency_key: str | None = None) -> dict:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return await self._call("POST", "/v1/jobs", json={"text": text}, headers=headers)

    async def get(self, job_id: str) -> dict:
        return await self._call("GET", f"/v1/jobs/{job_id}")

    async def wait(self, job_id: str, seconds: float, interval: float = 0.2) -> dict:
        deadline = time.monotonic() + seconds
        job = await self.get(job_id)
        while job["status"] in ("queued", "running") and time.monotonic() < deadline:
            await asyncio.sleep(interval)
            job = await self.get(job_id)
        return job
