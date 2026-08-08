"""AI Operating System Core — agent, workflow, memory, knowledge, execution, planning, scheduling, monitoring, recovery, learning runtimes."""

import hashlib
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional


class RuntimeStatus(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"
    SHUTDOWN = "shutdown"


class AgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    BLOCKED = "blocked"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class Agent:
    id: str
    name: str
    role: str
    capabilities: list[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    last_active: str = ""
    task_count: int = 0
    success_rate: float = 1.0


@dataclass
class MemoryEntry:
    id: str
    type: str  # decision, observation, conversation, fact, pattern, preference
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    timestamp: str = ""
    ttl: Optional[int] = None  # seconds
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduledTask:
    id: str
    name: str
    interval_seconds: int
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True
    callback: Optional[str] = ""
    max_retries: int = 3
    timeout_seconds: int = 300


@dataclass
class RuntimeMetrics:
    agents_active: int = 0
    agents_idle: int = 0
    agents_error: int = 0
    tasks_queued: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    memory_entries: int = 0
    uptime_seconds: float = 0.0
    last_health_check: str = ""


class AIOperatingSystem:
    """Core AI OS — coordinates all runtimes for autonomous engineering operations."""

    def __init__(self, os_id: str = "novaforge-os-1"):
        self.os_id = os_id
        self.status = RuntimeStatus.INITIALIZING
        self._lock = Lock()
        self._start_time = datetime.now(timezone.utc)

        # Runtimes
        self.agent_runtime = AgentRuntime(self)
        self.workflow_runtime = WorkflowRuntime(self)
        self.memory_runtime = MemoryRuntime(self)
        self.knowledge_runtime = KnowledgeRuntime(self)
        self.execution_runtime = ExecutionRuntime(self)
        self.planning_runtime = PlanningRuntime(self)
        self.scheduling_runtime = SchedulingRuntime(self)
        self.monitoring_runtime = MonitoringRuntime(self)
        self.recovery_runtime = RecoveryRuntime(self)
        self.learning_runtime = LearningRuntime(self)

        self.status = RuntimeStatus.RUNNING

    def get_metrics(self) -> RuntimeMetrics:
        return RuntimeMetrics(
            agents_active=self.agent_runtime.active_count(),
            agents_idle=self.agent_runtime.idle_count(),
            agents_error=self.agent_runtime.error_count(),
            tasks_queued=self.execution_runtime.queued_count(),
            tasks_completed=self.execution_runtime.completed_count(),
            tasks_failed=self.execution_runtime.failed_count(),
            memory_entries=self.memory_runtime.entry_count(),
            uptime_seconds=(datetime.now(timezone.utc) - self._start_time).total_seconds(),
            last_health_check=datetime.now(timezone.utc).isoformat(),
        )

    def health_check(self) -> dict:
        metrics = self.get_metrics()
        runtimes = {
            "agent": self.agent_runtime.status,
            "workflow": self.workflow_runtime.status,
            "memory": self.memory_runtime.status,
            "knowledge": self.knowledge_runtime.status,
            "execution": self.execution_runtime.status,
            "planning": self.planning_runtime.status,
            "scheduling": self.scheduling_runtime.status,
            "monitoring": self.monitoring_runtime.status,
            "recovery": self.recovery_runtime.status,
            "learning": self.learning_runtime.status,
        }
        degraded = any(s == RuntimeStatus.DEGRADED for s in runtimes.values())
        failed = any(s == RuntimeStatus.FAILED for s in runtimes.values())
        overall = RuntimeStatus.FAILED if failed else (RuntimeStatus.DEGRADED if degraded else RuntimeStatus.RUNNING)
        return {
            "os_id": self.os_id,
            "status": overall.value,
            "uptime_seconds": metrics.uptime_seconds,
            "runtimes": {k: v.value for k, v in runtimes.items()},
            "agents": {"active": metrics.agents_active, "idle": metrics.agents_idle, "error": metrics.agents_error},
            "tasks": {"queued": metrics.tasks_queued, "completed": metrics.tasks_completed, "failed": metrics.tasks_failed},
            "memory_entries": metrics.memory_entries,
            "timestamp": metrics.last_health_check,
        }

    def shutdown(self):
        self.status = RuntimeStatus.SHUTDOWN
        for rt in [self.agent_runtime, self.workflow_runtime, self.memory_runtime,
                   self.knowledge_runtime, self.execution_runtime, self.planning_runtime,
                   self.scheduling_runtime, self.monitoring_runtime, self.recovery_runtime,
                   self.learning_runtime]:
            rt.status = RuntimeStatus.SHUTDOWN


class AgentRuntime:
    """Manages agent lifecycle, assignment, and coordination."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.agents: dict[str, Agent] = {}
        self._lock = Lock()

    def register_agent(self, name: str, role: str, capabilities: list[str] = None) -> Agent:
        aid = f"agent-{uuid.uuid4().hex[:12]}"
        agent = Agent(
            id=aid, name=name, role=role,
            capabilities=capabilities or [],
            created_at=datetime.now(timezone.utc).isoformat(),
            last_active=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.agents[aid] = agent
        return agent

    def assign_task(self, agent_id: str, task_id: str) -> bool:
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent or agent.status != AgentStatus.IDLE:
                return False
            agent.status = AgentStatus.BUSY
            agent.current_task = task_id
            agent.last_active = datetime.now(timezone.utc).isoformat()
        return True

    def complete_task(self, agent_id: str, success: bool = True):
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent:
                return
            agent.status = AgentStatus.IDLE
            agent.current_task = None
            agent.task_count += 1
            if not success:
                agent.success_rate = (agent.success_rate * (agent.task_count - 1)) / max(agent.task_count, 1)
            agent.last_active = datetime.now(timezone.utc).isoformat()

    def find_available(self, capability: str = "") -> Optional[Agent]:
        for agent in self.agents.values():
            if agent.status == AgentStatus.IDLE:
                if not capability or capability in agent.capabilities:
                    return agent
        return None

    def find_best(self, task_requirements: list[str]) -> Optional[Agent]:
        best = None
        best_score = -1
        for agent in self.agents.values():
            if agent.status != AgentStatus.IDLE:
                continue
            score = sum(1 for r in task_requirements if r in agent.capabilities)
            if score > best_score:
                best_score = score
                best = agent
        return best

    def active_count(self) -> int:
        return sum(1 for a in self.agents.values() if a.status == AgentStatus.BUSY)

    def idle_count(self) -> int:
        return sum(1 for a in self.agents.values() if a.status == AgentStatus.IDLE)

    def error_count(self) -> int:
        return sum(1 for a in self.agents.values() if a.status == AgentStatus.ERROR)


class WorkflowRuntime:
    """Manages workflow execution lifecycle."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.active_workflows: dict[str, dict] = {}
        self._lock = Lock()

    def start_workflow(self, workflow_id: str, context: dict = None) -> bool:
        with self._lock:
            self.active_workflows[workflow_id] = {
                "id": workflow_id,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "steps_completed": 0,
                "total_steps": 0,
                "context": context or {},
            }
        return True

    def complete_step(self, workflow_id: str, step_name: str, result: Any = None):
        with self._lock:
            wf = self.active_workflows.get(workflow_id)
            if wf:
                wf["steps_completed"] += 1
                wf.setdefault("step_results", {})[step_name] = result

    def complete_workflow(self, workflow_id: str, status: str = "completed"):
        with self._lock:
            wf = self.active_workflows.get(workflow_id)
            if wf:
                wf["status"] = status
                wf["completed_at"] = datetime.now(timezone.utc).isoformat()

    def get_workflow(self, workflow_id: str) -> Optional[dict]:
        return self.active_workflows.get(workflow_id)


class MemoryRuntime:
    """Short-term and long-term memory storage and retrieval."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.short_term: list[MemoryEntry] = []
        self.long_term: list[MemoryEntry] = []
        self._lock = Lock()

    def store(self, entry: MemoryEntry):
        with self._lock:
            if entry.ttl and entry.ttl < 3600:
                self.short_term.append(entry)
                if len(self.short_term) > 1000:
                    self.short_term = self.short_term[-500:]
            else:
                self.long_term.append(entry)
                if len(self.long_term) > 10000:
                    self.long_term = self.long_term[-5000:]

    def recall(self, query: str, max_results: int = 10, memory_type: str = "") -> list[MemoryEntry]:
        results = []
        entries = self.short_term + self.long_term
        for e in entries:
            if memory_type and e.type != memory_type:
                continue
            if query.lower() in e.content.lower():
                results.append(e)
            elif any(query.lower() in t.lower() for t in e.tags):
                results.append(e)
        return sorted(results, key=lambda x: x.confidence, reverse=True)[:max_results]

    def forget(self, older_than_seconds: int = 86400):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
        with self._lock:
            self.short_term = [e for e in self.short_term if e.timestamp >= cutoff]

    def entry_count(self) -> int:
        return len(self.short_term) + len(self.long_term)


class KnowledgeRuntime:
    """Structured knowledge base with versioning and relationships."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.knowledge_base: dict[str, dict] = {}
        self._lock = Lock()

    def add_fact(self, domain: str, key: str, value: Any, source: str = "", confidence: float = 1.0):
        with self._lock:
            self.knowledge_base[f"{domain}:{key}"] = {
                "domain": domain, "key": key, "value": value,
                "source": source, "confidence": confidence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": self.knowledge_base.get(f"{domain}:{key}", {}).get("version", 0) + 1,
            }

    def get_fact(self, domain: str, key: str) -> Optional[Any]:
        entry = self.knowledge_base.get(f"{domain}:{key}")
        return entry["value"] if entry else None

    def query_domain(self, domain: str) -> list[dict]:
        return [v for k, v in self.knowledge_base.items() if k.startswith(f"{domain}:")]


class ExecutionRuntime:
    """Task queue, execution, and result tracking."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.queue: list[dict] = []
        self.completed: list[dict] = []
        self.failed: list[dict] = []
        self._lock = Lock()

    def enqueue(self, task: dict) -> str:
        tid = task.get("id", f"task-{uuid.uuid4().hex[:12]}")
        task["id"] = tid
        task["status"] = "queued"
        task["created_at"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.queue.append(task)
        return tid

    def dequeue(self) -> Optional[dict]:
        with self._lock:
            if not self.queue:
                return None
            return self.queue.pop(0)

    def complete(self, task_id: str, result: Any = None):
        with self._lock:
            self.queue[:] = [t for t in self.queue if t.get("id") != task_id]
            self.completed.append({"id": task_id, "result": result, "completed_at": datetime.now(timezone.utc).isoformat()})

    def fail(self, task_id: str, error: str):
        with self._lock:
            self.queue[:] = [t for t in self.queue if t.get("id") != task_id]
            self.failed.append({"id": task_id, "error": error, "failed_at": datetime.now(timezone.utc).isoformat()})

    def queued_count(self) -> int:
        return len(self.queue)

    def completed_count(self) -> int:
        return len(self.completed)

    def failed_count(self) -> int:
        return len(self.failed)


class PlanningRuntime:
    """Strategic and tactical planning for engineering activities."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.plans: dict[str, dict] = {}

    def create_plan(self, goal: str, steps: list[dict], context: dict = None) -> str:
        pid = f"plan-{uuid.uuid4().hex[:12]}"
        self.plans[pid] = {
            "id": pid, "goal": goal, "steps": steps,
            "context": context or {},
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "current_step": 0,
        }
        return pid

    def advance(self, plan_id: str) -> Optional[dict]:
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        idx = plan["current_step"]
        if idx >= len(plan["steps"]):
            plan["status"] = "completed"
            return None
        step = plan["steps"][idx]
        plan["current_step"] = idx + 1
        return step

    def get_plan(self, plan_id: str) -> Optional[dict]:
        return self.plans.get(plan_id)


class SchedulingRuntime:
    """Time-based and event-based task scheduling."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.tasks: dict[str, ScheduledTask] = {}
        self._lock = Lock()

    def schedule(self, name: str, interval_seconds: int, callback: str = "", max_retries: int = 3) -> str:
        tid = f"sched-{uuid.uuid4().hex[:12]}"
        task = ScheduledTask(
            id=tid, name=name, interval_seconds=interval_seconds,
            callback=callback, max_retries=max_retries,
            next_run=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.tasks[tid] = task
        return tid

    def get_due(self) -> list[ScheduledTask]:
        now = datetime.now(timezone.utc)
        due = []
        with self._lock:
            for task in self.tasks.values():
                if not task.enabled:
                    continue
                if task.next_run is None:
                    due.append(task)
                    continue
                try:
                    if now >= datetime.fromisoformat(task.next_run):
                        due.append(task)
                except (ValueError, TypeError):
                    due.append(task)
        return due

    def mark_run(self, task_id: str):
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                task.last_run = datetime.now(timezone.utc).isoformat()
                task.next_run = (datetime.now(timezone.utc) + timedelta(seconds=task.interval_seconds)).isoformat()

    def cancel(self, task_id: str):
        with self._lock:
            self.tasks.pop(task_id, None)


class MonitoringRuntime:
    """System health, alerting, and observability."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.alerts: list[dict] = []
        self.health_history: list[dict] = []
        self._lock = Lock()

    def record_health(self, metrics: dict):
        entry = {**metrics, "timestamp": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            self.health_history.append(entry)
            if len(self.health_history) > 1000:
                self.health_history = self.health_history[-1000:]

    def raise_alert(self, severity: str, source: str, message: str, details: dict = None):
        alert = {
            "id": f"alert-{uuid.uuid4().hex[:12]}",
            "severity": severity, "source": source, "message": message,
            "details": details or {}, "timestamp": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }
        with self._lock:
            self.alerts.append(alert)

    def get_alerts(self, severity: str = "", limit: int = 50) -> list[dict]:
        alerts = self.alerts
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        return alerts[-limit:]

    def acknowledge_alert(self, alert_id: str) -> bool:
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["acknowledged"] = True
                return True
        return False


class RecoveryRuntime:
    """Failure detection, rollback, and system recovery."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.recovery_plans: dict[str, dict] = {}

    def register_rollback(self, action_id: str, rollback_fn: str, context: dict = None):
        self.recovery_plans[action_id] = {
            "action_id": action_id,
            "rollback_fn": rollback_fn,
            "context": context or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def execute_rollback(self, action_id: str) -> bool:
        plan = self.recovery_plans.get(action_id)
        if not plan:
            return False
        plan["executed_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_recovery_status(self) -> list[dict]:
        return list(self.recovery_plans.values())


class LearningRuntime:
    """Continuous learning from system operations and outcomes."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.observations: list[dict] = []
        self.patterns: dict[str, dict] = {}

    def observe(self, event: str, outcome: str, context: dict = None):
        self.observations.append({
            "event": event, "outcome": outcome,
            "context": context or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.observations) > 5000:
            self.observations = self.observations[-5000:]

    def learn_pattern(self, pattern_id: str, pattern: dict):
        if pattern_id in self.patterns:
            self.patterns[pattern_id]["frequency"] += 1
            self.patterns[pattern_id]["last_seen"] = datetime.now(timezone.utc).isoformat()
        else:
            self.patterns[pattern_id] = {**pattern, "frequency": 1, "first_seen": datetime.now(timezone.utc).isoformat()}

    def get_insights(self) -> list[dict]:
        return sorted(self.patterns.values(), key=lambda x: -x.get("frequency", 0))[:20]
