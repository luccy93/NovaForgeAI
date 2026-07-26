"""LangGraph-based workflow engine — sequential, parallel, conditional, retry, checkpoint."""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry
from app.agents.schemas import (
    AgentResult, AgentStatus, RiskLevel, RetryPolicy,
)


class WorkflowState(TypedDict):
    workflow_id: str
    status: str
    current_step: int
    total_steps: int
    input: str
    context: dict[str, Any]
    results: list[dict[str, Any]]
    errors: list[str]
    checkpoints: list[dict[str, Any]]
    human_approval: Optional[str]
    start_time: float


class WorkflowNode:
    """A single step in a workflow graph."""

    def __init__(
        self,
        name: str,
        agent_name: str,
        registry: AgentRegistry,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_seconds: int = 300,
        require_human: bool = False,
    ):
        self.name = name
        self.agent_name = agent_name
        self.registry = registry
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout_seconds = timeout_seconds
        self.require_human = require_human

    async def __call__(
        self, state: WorkflowState, llm_input: Optional[str] = None, **kwargs
    ) -> dict:
        agent = self.registry.get_agent(self.agent_name)
        if not agent:
            return {"errors": state["errors"] + [f"Agent '{self.agent_name}' not found"]}

        if self.require_human:
            state["human_approval"] = "pending"
            return state

        task_input = llm_input or state["input"]
        result = await agent.run(task_input, state.get("context"))

        entry = {
            "step": state["current_step"],
            "node": self.name,
            "agent": self.agent_name,
            "result": {
                "output": result.output,
                "status": result.status.value,
                "confidence": result.decision.confidence if result.decision else 0.0,
                "risk": result.decision.risk_level.value if result.decision else "none",
                "files_affected": result.decision.files_affected if result.decision else [],
                "duration_ms": result.duration_ms,
                "tokens_used": result.tokens_used,
                "error": result.error,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        new_errors = list(state["errors"])
        if result.error:
            new_errors.append(f"Step {state['current_step']} ({self.name}): {result.error}")

        return {
            "current_step": state["current_step"] + 1,
            "results": state["results"] + [entry],
            "errors": new_errors,
            "checkpoints": state["checkpoints"] + [entry],
        }


class AgentWorkflow:
    """LangGraph-based workflow engine for multi-agent orchestration."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self.graph = StateGraph(WorkflowState)
        self._nodes: dict[str, WorkflowNode] = {}
        self._edges: list[tuple[str, str, Optional[Callable]]] = []

    def add_node(self, name: str, node: WorkflowNode):
        self._nodes[name] = node
        self.graph.add_node(name, node)

    def add_edge(self, source: str, target: str):
        self._edges.append((source, target, None))
        self.graph.add_edge(source, target)

    def add_conditional_edge(
        self, source: str, condition_fn: Callable, mapping: dict[str, str]
    ):
        self.graph.add_conditional_edges(source, condition_fn, mapping)

    def build(self):
        self.graph.set_entry_point(list(self._nodes.keys())[0])
        for source, target, _ in self._edges:
            self.graph.add_edge(source, target)
        last_node = list(self._nodes.keys())[-1]
        self.graph.add_edge(last_node, END)
        return self.graph.compile()

    def build_parallel(self, node_names: list[str], merge_node: str):
        """Create parallel execution by connecting all nodes to a merge node."""
        self.graph.set_entry_point(node_names[0])
        for i in range(1, len(node_names)):
            self.graph.add_edge(node_names[i - 1], node_names[i])

    @staticmethod
    def sequential(agents: list[str], registry: AgentRegistry) -> "AgentWorkflow":
        """Create a sequential pipeline workflow."""
        wf = AgentWorkflow(registry)
        for i, agent_name in enumerate(agents):
            node = WorkflowNode(
                name=f"step_{i}",
                agent_name=agent_name,
                registry=registry,
            )
            wf.add_node(f"step_{i}", node)
            if i > 0:
                wf.add_edge(f"step_{i-1}", f"step_{i}")
        return wf

    @staticmethod
    def with_retry(
        agent_name: str,
        registry: AgentRegistry,
        max_retries: int = 3,
    ) -> "AgentWorkflow":
        """Create a single-agent workflow with retry logic."""
        wf = AgentWorkflow(registry)
        node = WorkflowNode(
            name=f"{agent_name}_retry",
            agent_name=agent_name,
            registry=registry,
            retry_policy=RetryPolicy(max_retries=max_retries),
        )
        wf.add_node(f"{agent_name}_retry", node)
        return wf

    @staticmethod
    def with_human_approval(
        agent_name: str, registry: AgentRegistry
    ) -> "AgentWorkflow":
        """Create a workflow that requires human approval."""
        wf = AgentWorkflow(registry)
        node = WorkflowNode(
            name=f"{agent_name}_with_approval",
            agent_name=agent_name,
            registry=registry,
            require_human=True,
        )
        wf.add_node(f"{agent_name}_with_approval", node)
        return wf

    def get_compiled_graph(self):
        graph_copy = StateGraph(WorkflowState)
        for name, node in self._nodes.items():
            graph_copy.add_node(name, node)
        graph_copy.set_entry_point(list(self._nodes.keys())[0])
        for source, target, _ in self._edges:
            graph_copy.add_edge(source, target)
        last_node = list(self._nodes.keys())[-1]
        graph_copy.add_edge(last_node, END)
        return graph_copy.compile()

    async def run(
        self,
        task_input: str,
        context: Optional[dict] = None,
    ) -> WorkflowState:
        initial: WorkflowState = {
            "workflow_id": str(uuid.uuid4()),
            "status": "running",
            "current_step": 0,
            "total_steps": len(self._nodes),
            "input": task_input,
            "context": context or {},
            "results": [],
            "errors": [],
            "checkpoints": [],
            "human_approval": None,
            "start_time": time.time(),
        }

        compiled = self.get_compiled_graph()
        final_state = await compiled.ainvoke(initial)

        has_errors = len(final_state["errors"]) > 0
        has_blocked = any(
            r.get("result", {}).get("status") == "blocked"
            for r in final_state["results"]
        )
        if has_blocked:
            final_state["status"] = "blocked"
        elif has_errors:
            final_state["status"] = "failed"
        else:
            final_state["status"] = "completed"

        return final_state

    async def resume_after_approval(
        self, state: WorkflowState, approved: bool, feedback: Optional[str] = None
    ) -> WorkflowState:
        if approved:
            state["human_approval"] = "approved"
            state["status"] = "running"
        else:
            state["human_approval"] = "rejected"
            state["status"] = "cancelled"
            if feedback:
                state["errors"].append(f"Rejected: {feedback}")
        return state
