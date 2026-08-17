"""NovaForge SDK — synchronous and async API clients."""

import asyncio
import json
import time
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from backend.sdk.models import (
    User, Organization, Repository, Conversation, Message,
    Agent, AgentRun, PipelineResult, Notification,
    BillingPlan, Subscription, FeatureFlag,
    DevSession, ContextResult, CodeActionResult, ReviewResult, SearchResultItem,
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

    # ─── DevTools ──────────────────────────────────────────────────────

    def create_devtools_session(
        self,
        client_type: str,
        client_version: str = "1.0.0",
        org_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        workspace_root: Optional[str] = None,
    ) -> DevSession:
        payload: dict[str, Any] = {
            "client_type": client_type,
            "client_version": client_version,
        }
        if org_id is not None:
            payload["org_id"] = org_id
        if repo_id is not None:
            payload["repo_id"] = repo_id
        if workspace_root is not None:
            payload["workspace_root"] = workspace_root
        data = self.post("/devtools/sessions", payload)
        return DevSession(**{k: v for k, v in data.items() if k in DevSession.__dataclass_fields__})

    def get_devtools_session(self, session_id: str) -> DevSession:
        data = self.get(f"/devtools/sessions/{session_id}")
        return DevSession(**{k: v for k, v in data.items() if k in DevSession.__dataclass_fields__})

    def delete_devtools_session(self, session_id: str) -> dict:
        return self.delete(f"/devtools/sessions/{session_id}")

    def collect_context(
        self,
        session_id: str,
        file_path: Optional[str] = None,
        language: Optional[str] = None,
        selection: Optional[str] = None,
        imports: Optional[list[str]] = None,
        max_context_tokens: int = 4096,
    ) -> ContextResult:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "max_context_tokens": max_context_tokens,
        }
        if file_path is not None:
            payload["file_path"] = file_path
        if language is not None:
            payload["language"] = language
        if selection is not None:
            payload["selection"] = selection
        if imports is not None:
            payload["imports"] = imports
        data = self.post("/devtools/context", payload)
        return ContextResult(**{k: v for k, v in data.items() if k in ContextResult.__dataclass_fields__})

    def code_action(
        self,
        action: str,
        file_path: str,
        language: str,
        code: str,
        session_id: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        stream: bool = False,
    ) -> CodeActionResult:
        payload: dict[str, Any] = {
            "action": action,
            "file_path": file_path,
            "language": language,
            "code": code,
            "session_id": session_id,
            "stream": stream,
        }
        if start_line is not None:
            payload["start_line"] = start_line
        if end_line is not None:
            payload["end_line"] = end_line
        data = self.post("/devtools/code-actions", payload)
        return CodeActionResult(**{k: v for k, v in data.items() if k in CodeActionResult.__dataclass_fields__})

    def review_code(
        self,
        session_id: str,
        file_path: Optional[str] = None,
        code: Optional[str] = None,
        pr_number: Optional[int] = None,
        review_type: str = "standard",
        stream: bool = False,
    ) -> ReviewResult:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "review_type": review_type,
            "stream": stream,
        }
        if file_path is not None:
            payload["file_path"] = file_path
        if code is not None:
            payload["code"] = code
        if pr_number is not None:
            payload["pr_number"] = pr_number
        data = self.post("/devtools/review", payload)
        return ReviewResult(**{k: v for k, v in data.items() if k in ReviewResult.__dataclass_fields__})

    def run_agent_from_ide(
        self,
        session_id: str,
        agent_name: str,
        task: str,
        stream: bool = False,
    ) -> dict:
        return self.post("/devtools/agents/run", {
            "session_id": session_id,
            "agent_name": agent_name,
            "task": task,
            "stream": stream,
        })

    def search_code(
        self,
        session_id: str,
        query: str,
        search_type: str = "semantic",
        repository_id: Optional[str] = None,
        file_pattern: Optional[str] = None,
        limit: int = 20,
    ) -> list[SearchResultItem]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if file_pattern is not None:
            payload["file_pattern"] = file_pattern
        data = self.post("/devtools/search", payload)
        return [
            SearchResultItem(**{k: v for k, v in item.items() if k in SearchResultItem.__dataclass_fields__})
            for item in data
        ]

    def run_workflow_from_ide(
        self,
        session_id: str,
        workflow_id: str,
        inputs: Optional[dict[str, Any]] = None,
        stream: bool = False,
    ) -> dict:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "workflow_id": workflow_id,
            "stream": stream,
        }
        if inputs is not None:
            payload["inputs"] = inputs
        return self.post("/devtools/workflows/run", payload)

    def get_capabilities(self, client_type: str) -> dict:
        return self.get("/devtools/capabilities", params={"client_type": client_type})

    def get_git_status(self) -> dict:
        return self.get("/devtools/git/status")

    def get_git_diff(self, file_path: Optional[str] = None, staged: bool = False) -> dict:
        params: dict[str, Any] = {"staged": staged}
        if file_path is not None:
            params["file_path"] = file_path
        return self.get("/devtools/git/diff", params=params)

    def get_git_context(self) -> dict:
        return self.get("/devtools/git/context")

    def get_diagnostics(self, file_path: Optional[str] = None) -> dict:
        params: dict[str, Any] = {}
        if file_path is not None:
            params["file_path"] = file_path
        return self.get("/devtools/diagnostics", params=params)


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

    # ─── DevTools ──────────────────────────────────────────────────────

    async def create_devtools_session(
        self,
        client_type: str,
        client_version: str = "1.0.0",
        org_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        workspace_root: Optional[str] = None,
    ) -> DevSession:
        payload: dict[str, Any] = {
            "client_type": client_type,
            "client_version": client_version,
        }
        if org_id is not None:
            payload["org_id"] = org_id
        if repo_id is not None:
            payload["repo_id"] = repo_id
        if workspace_root is not None:
            payload["workspace_root"] = workspace_root
        data = await self.post("/devtools/sessions", payload)
        return DevSession(**{k: v for k, v in data.items() if k in DevSession.__dataclass_fields__})

    async def get_devtools_session(self, session_id: str) -> DevSession:
        data = await self.get(f"/devtools/sessions/{session_id}")
        return DevSession(**{k: v for k, v in data.items() if k in DevSession.__dataclass_fields__})

    async def delete_devtools_session(self, session_id: str) -> dict:
        return await self.delete(f"/devtools/sessions/{session_id}")

    async def collect_context(
        self,
        session_id: str,
        file_path: Optional[str] = None,
        language: Optional[str] = None,
        selection: Optional[str] = None,
        imports: Optional[list[str]] = None,
        max_context_tokens: int = 4096,
    ) -> ContextResult:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "max_context_tokens": max_context_tokens,
        }
        if file_path is not None:
            payload["file_path"] = file_path
        if language is not None:
            payload["language"] = language
        if selection is not None:
            payload["selection"] = selection
        if imports is not None:
            payload["imports"] = imports
        data = await self.post("/devtools/context", payload)
        return ContextResult(**{k: v for k, v in data.items() if k in ContextResult.__dataclass_fields__})

    async def code_action(
        self,
        action: str,
        file_path: str,
        language: str,
        code: str,
        session_id: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        stream: bool = False,
    ) -> CodeActionResult:
        payload: dict[str, Any] = {
            "action": action,
            "file_path": file_path,
            "language": language,
            "code": code,
            "session_id": session_id,
            "stream": stream,
        }
        if start_line is not None:
            payload["start_line"] = start_line
        if end_line is not None:
            payload["end_line"] = end_line
        data = await self.post("/devtools/code-actions", payload)
        return CodeActionResult(**{k: v for k, v in data.items() if k in CodeActionResult.__dataclass_fields__})

    async def review_code(
        self,
        session_id: str,
        file_path: Optional[str] = None,
        code: Optional[str] = None,
        pr_number: Optional[int] = None,
        review_type: str = "standard",
        stream: bool = False,
    ) -> ReviewResult:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "review_type": review_type,
            "stream": stream,
        }
        if file_path is not None:
            payload["file_path"] = file_path
        if code is not None:
            payload["code"] = code
        if pr_number is not None:
            payload["pr_number"] = pr_number
        data = await self.post("/devtools/review", payload)
        return ReviewResult(**{k: v for k, v in data.items() if k in ReviewResult.__dataclass_fields__})

    async def run_agent_from_ide(
        self,
        session_id: str,
        agent_name: str,
        task: str,
        stream: bool = False,
    ) -> dict:
        return await self.post("/devtools/agents/run", {
            "session_id": session_id,
            "agent_name": agent_name,
            "task": task,
            "stream": stream,
        })

    async def search_code(
        self,
        session_id: str,
        query: str,
        search_type: str = "semantic",
        repository_id: Optional[str] = None,
        file_pattern: Optional[str] = None,
        limit: int = 20,
    ) -> list[SearchResultItem]:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if file_pattern is not None:
            payload["file_pattern"] = file_pattern
        data = await self.post("/devtools/search", payload)
        return [
            SearchResultItem(**{k: v for k, v in item.items() if k in SearchResultItem.__dataclass_fields__})
            for item in data
        ]

    async def run_workflow_from_ide(
        self,
        session_id: str,
        workflow_id: str,
        inputs: Optional[dict[str, Any]] = None,
        stream: bool = False,
    ) -> dict:
        payload: dict[str, Any] = {
            "session_id": session_id,
            "workflow_id": workflow_id,
            "stream": stream,
        }
        if inputs is not None:
            payload["inputs"] = inputs
        return await self.post("/devtools/workflows/run", payload)

    async def get_capabilities(self, client_type: str) -> dict:
        return await self.get("/devtools/capabilities", params={"client_type": client_type})

    async def get_git_status(self) -> dict:
        return await self.get("/devtools/git/status")

    async def get_git_diff(self, file_path: Optional[str] = None, staged: bool = False) -> dict:
        params: dict[str, Any] = {"staged": staged}
        if file_path is not None:
            params["file_path"] = file_path
        return await self.get("/devtools/git/diff", params=params)

    async def get_git_context(self) -> dict:
        return await self.get("/devtools/git/context")

    async def get_diagnostics(self, file_path: Optional[str] = None) -> dict:
        params: dict[str, Any] = {}
        if file_path is not None:
            params["file_path"] = file_path
        return await self.get("/devtools/diagnostics", params=params)
