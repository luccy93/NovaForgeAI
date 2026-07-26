"""NovaForge SDK — synchronous and async API clients."""

import json
import time
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from backend.sdk.models import (
    User, Organization, Repository, Conversation, Message,
    Agent, AgentRun, PipelineResult, Notification,
    BillingPlan, Subscription, FeatureFlag,
)
from backend.sdk.exceptions import (
    NovaForgeError, AuthenticationError, NotFoundError,
    RateLimitError, ValidationError, ServerError, ConnectionError,
)


class BaseClient:
    """Base client with shared logic for sync and async clients."""

    BASE_PATH = "/api/v1"

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.access_token = access_token
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _build_url(self, path: str) -> str:
        return urljoin(self.base_url, f"{self.BASE_PATH}{path}")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise AuthenticationError(response.json().get("detail", "Unauthorized"))
        if response.status_code == 404:
            raise NotFoundError(response.json().get("detail", "Not found"))
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        if response.status_code == 422:
            raise ValidationError(str(response.json().get("detail", "Validation error")))
        if response.status_code >= 500:
            raise ServerError(f"Server error: {response.status_code}")
        if response.status_code >= 400:
            raise NovaForgeError(f"Request failed: {response.status_code}")
        return response.json()

    @staticmethod
    def _parse_user(data: dict) -> User:
        return User(**{k: v for k, v in data.items() if k in User.__dataclass_fields__})

    @staticmethod
    def _parse_org(data: dict) -> Organization:
        return Organization(**{k: v for k, v in data.items() if k in Organization.__dataclass_fields__})

    @staticmethod
    def _parse_repo(data: dict) -> Repository:
        return Repository(**{k: v for k, v in data.items() if k in Repository.__dataclass_fields__})

    @staticmethod
    def _parse_agent(data: dict) -> Agent:
        return Agent(**{k: v for k, v in data.items() if k in Agent.__dataclass_fields__})

    @staticmethod
    def _parse_notification(data: dict) -> Notification:
        return Notification(**{k: v for k, v in data.items() if k in Notification.__dataclass_fields__})


class NovaForgeClient(BaseClient):
    """Synchronous NovaForge API client."""

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = self._build_url(path)
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        last_error = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.request(method, url, headers=headers, **kwargs)
                return self._handle_response(resp)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(1 * (2 ** attempt))
                    continue
                raise ConnectionError(str(last_error))
        raise ConnectionError(str(last_error))

    def get(self, path: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, data: Optional[dict] = None) -> Any:
        return self._request("POST", path, json=data or {})

    def put(self, path: str, data: Optional[dict] = None) -> Any:
        return self._request("PUT", path, json=data or {})

    def patch(self, path: str, data: Optional[dict] = None) -> Any:
        return self._request("PATCH", path, json=data or {})

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ─── Auth ──────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> dict:
        return self.post("/auth/login", {"email": email, "password": password})

    def register(self, email: str, username: str, password: str) -> dict:
        return self.post("/auth/register", {"email": email, "username": username, "password": password})

    def me(self) -> User:
        return self._parse_user(self.get("/auth/me"))

    # ─── Organizations ─────────────────────────────────────────────────

    def list_organizations(self) -> list[Organization]:
        return [self._parse_org(o) for o in self.get("/organizations")]

    def create_organization(self, name: str, slug: str) -> Organization:
        return self._parse_org(self.post("/organizations", {"name": name, "slug": slug}))

    # ─── Repositories ──────────────────────────────────────────────────

    def list_repositories(self) -> list[Repository]:
        return [self._parse_repo(r) for r in self.get("/repositories")]

    # ─── Agents ────────────────────────────────────────────────────────

    def list_agents(self) -> list[Agent]:
        return [self._parse_agent(a) for a in self.get("/agents/v2")]

    def run_agent(self, name: str, task: str) -> dict:
        return self.post(f"/agents/v2/{name}/run", {"input": task})

    def run_pipeline(self, agents: list[str], task: str) -> dict:
        return self.post("/agents/v2/pipeline", {"agents": agents, "input": task})

    # ─── Notifications ─────────────────────────────────────────────────

    def list_notifications(self) -> list[Notification]:
        return [self._parse_notification(n) for n in self.get("/notifications")]


class AsyncNovaForgeClient(BaseClient):
    """Async NovaForge API client."""

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = self._build_url(path)
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.request(method, url, headers=headers, **kwargs)
                return self._handle_response(resp)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (2 ** attempt))
                    continue
                raise ConnectionError(str(last_error))
        raise ConnectionError(str(last_error))

    async def get(self, path: str, params: Optional[dict] = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: Optional[dict] = None) -> Any:
        return await self._request("POST", path, json=data or {})

    async def put(self, path: str, data: Optional[dict] = None) -> Any:
        return await self._request("PUT", path, json=data or {})

    async def patch(self, path: str, data: Optional[dict] = None) -> Any:
        return await self._request("PATCH", path, json=data or {})

    async def delete(self, path: str) -> Any:
        return await self._request("DELETE", path)

    async def login(self, email: str, password: str) -> dict:
        return await self.post("/auth/login", {"email": email, "password": password})

    async def me(self) -> User:
        return self._parse_user(await self.get("/auth/me"))

    async def list_agents(self) -> list[Agent]:
        return [self._parse_agent(a) for a in await self.get("/agents/v2")]

    async def run_agent(self, name: str, task: str) -> dict:
        return await self.post(f"/agents/v2/{name}/run", {"input": task})


import asyncio  # noqa: E402 (needed for async client sleep)
