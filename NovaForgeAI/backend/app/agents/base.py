"""Base agent class with identity, memory, tools, telemetry, and retry."""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.agents.schemas import (
    AgentConfig, AgentResult, AgentStatus, AgentDecision,
    ToolResult, RetryPolicy, RiskLevel,
)
from app.agents.tools import ToolRegistry
from app.agents.memory import MemoryStore
from app.agents.safety import SafetyChecker
from app.agents.decision_engine import DecisionEngine


class BaseAgent:
    """Foundation for all NovaForge agents."""

    def __init__(
        self,
        config: AgentConfig,
        tool_registry: Optional[ToolRegistry] = None,
        memory_store: Optional[MemoryStore] = None,
        safety_checker: Optional[SafetyChecker] = None,
        decision_engine: Optional[DecisionEngine] = None,
    ):
        self.config = config
        self.tool_registry = tool_registry or ToolRegistry()
        self.memory = memory_store or MemoryStore()
        self.safety = safety_checker or SafetyChecker()
        self.decision_engine = decision_engine or DecisionEngine()
        self._llm: Optional[BaseChatModel] = None
        self._session_id: Optional[str] = None

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = self._create_llm()
        return self._llm

    def _create_llm(self) -> BaseChatModel:
        model_name = self.config.model
        temp = self.config.temperature
        max_tok = self.config.max_tokens

        if settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_name, temperature=temp, max_tokens=max_tok,
                api_key=settings.openai_api_key, timeout=self.config.timeout_seconds,
            )
        if settings.anthropic_api_key:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_name, temperature=temp, max_tokens=max_tok,
                api_key=settings.anthropic_api_key,
            )
        if settings.google_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name, temperature=temp, max_tokens=max_tok,
                api_key=settings.google_api_key,
            )

        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name, temperature=temp, max_tokens=max_tok,
            api_key="sk-placeholder", timeout=self.config.timeout_seconds,
        )

    async def run(self, task_input: str, context: Optional[dict] = None) -> AgentResult:
        start = time.monotonic()
        self._session_id = str(uuid.uuid4())
        tool_calls: list[ToolResult] = []
        error: Optional[str] = None
        status = AgentStatus.completed
        decision: Optional[AgentDecision] = None
        output = ""
        tokens_used = 0

        safe = await self.safety.check_input(task_input, self.config.permissions)
        if not safe.allowed:
            status = AgentStatus.failed
            error = safe.reason
            output = f"Safety check failed: {safe.reason}"
            return self._result(output, status, tool_calls, error, start)

        for attempt in range(self.config.retry_policy.max_retries + 1):
            try:
                system_prompt = await self._build_system_prompt(context)
                user_prompt = await self._build_user_prompt(task_input, context)

                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]

                response = await asyncio.wait_for(
                    self.llm.agenerate([[m for m in messages]]),
                    timeout=self.config.timeout_seconds,
                )
                output = response.generations[0][0].text
                if response.llm_output:
                    tokens_used = response.llm_output.get("token_usage", {}).get("total_tokens", 0)

                tool_results = await self._execute_tools(output, context)
                tool_calls.extend(tool_results)

                decision = await self.decision_engine.analyze(
                    task_input, output, tool_calls, context
                )

                if decision.risk_level in (RiskLevel.high, RiskLevel.critical) and self.config.require_human_approval:
                    status = AgentStatus.blocked
                    output = f"BLOCKED: High-risk action requires approval.\n{output}"
                    break

                break

            except asyncio.TimeoutError:
                error = f"Timeout after {self.config.timeout_seconds}s"
                status = AgentStatus.failed
                if attempt < self.config.retry_policy.max_retries:
                    delay = min(
                        self.config.retry_policy.backoff_base ** attempt,
                        self.config.retry_policy.max_delay,
                    )
                    await asyncio.sleep(delay)
                    continue
            except Exception as e:
                error = str(e)
                status = AgentStatus.failed
                if attempt < self.config.retry_policy.max_retries and isinstance(
                    e, self.config.retry_policy.retryable_exceptions
                ):
                    delay = min(
                        self.config.retry_policy.backoff_base ** attempt,
                        self.config.retry_policy.max_delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        duration = int((time.monotonic() - start) * 1000)

        ctx = context or {}
        await self.memory.store(
            scope="short_term",
            key=f"run:{self._session_id}",
            value={
                "agent": self.config.name,
                "input": task_input,
                "output": output,
                "status": status.value,
                "duration_ms": duration,
                "tokens_used": tokens_used,
                "error": error,
                "decision": decision,
                "organization_id": str(ctx.get("organization_id", "")),
                "repository_id": str(ctx.get("repository_id", "")),
            },
        )

        return AgentResult(
            agent_name=self.config.name,
            status=status,
            output=output,
            decision=decision,
            tool_calls=tool_calls,
            duration_ms=duration,
            tokens_used=tokens_used,
            model_used=self.config.model,
            error=error,
        )

    async def _build_system_prompt(self, context: Optional[dict] = None) -> str:
        parts = [
            f"You are {self.config.name}, a {self.config.role.value} agent in NovaForge AI.",
            f"Role: {self.config.role.value}",
            f"Goals: {', '.join(self.config.goals)}",
        ]
        if context:
            repo = context.get("repository") or context.get("repo_name")
            if repo:
                parts.append(f"Working on repository: {repo}")
            org = context.get("organization_id")
            if org:
                parts.append(f"Organization: {org}")
        return "\n".join(parts)

    async def _build_user_prompt(self, task_input: str, context: Optional[dict] = None) -> str:
        parts = [f"## Task\n{task_input}"]
        if context:
            ctx_str = "\n".join(f"{k}: {v}" for k, v in context.items() if k not in ("organization_id", "repository_id"))
            if ctx_str:
                parts.append(f"## Context\n{ctx_str}")
        tools_desc = self.tool_registry.describe(self.config.permissions)
        if tools_desc:
            parts.append(f"## Available Tools\n{tools_desc}")
        parts.append("\nProvide your response with evidence, confidence score, and risk assessment.")
        return "\n\n".join(parts)

    async def _execute_tools(self, output: str, context: Optional[dict] = None) -> list[ToolResult]:
        results = []
        tool_calls = self.tool_registry.parse_calls(output)
        for tc in tool_calls[: self.config.max_tool_calls]:
            if tc.name not in self.config.permissions and "read" not in self.config.permissions and "*" not in self.config.permissions:
                results.append(ToolResult(success=False, output="", error=f"Permission denied: {tc.name}"))
                continue
            result = await self.tool_registry.execute(tc.name, **tc.params)
            results.append(result)
        return results

    def _result(self, output: str, status: AgentStatus, tool_calls: list, error: Optional[str], start: float) -> AgentResult:
        return AgentResult(
            agent_name=self.config.name, status=status, output=output,
            tool_calls=tool_calls, duration_ms=int((time.monotonic() - start) * 1000),
            error=error, model_used=self.config.model,
        )
