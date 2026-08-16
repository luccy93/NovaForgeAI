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


class TaskStatus(Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    APPROVAL_REQUIRED = "approval_required"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    RECOVERING = "recovering"


@dataclass
class KernelTask:
    """Kernel task with full lifecycle management."""
    task_id: str
    tenant_id: str
    actor: str  # agent_id or user_id
    type: str  # agent, model, tool, workflow, event, memory
    priority: str = "normal"  # critical, high, normal, low, background
    status: TaskStatus = TaskStatus.QUEUED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deadline: Optional[str] = None
    parent_task_id: Optional[str] = None
    runtime_version: str = "1.0.0"
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Runtime context
    repository: Optional[str] = None
    workspace: Optional[str] = None
    memory_references: list[str] = field(default_factory=list)
    tool_permissions: list[str] = field(default_factory=list)
    model_configuration: Optional[str] = None
    policy_references: list[str] = field(default_factory=list)
    # Execution state
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    # Resource tracking
    cpu_seconds: float = 0.0
    memory_bytes: int = 0
    disk_bytes: int = 0
    network_bytes: int = 0
    token_count: int = 0
    model_request_count: int = 0
    tool_call_count: int = 0
    cost_cents: float = 0.0
    # Quota tracking
    quota_usage: dict[str, float] = field(default_factory=lambda: {
        "cpu_seconds": 0.0, "memory_bytes": 0, "disk_bytes": 0,
        "network_bytes": 0, "token_count": 0, "cost_cents": 0.0
    })
    # Checkpoint state
    checkpoint_id: Optional[str] = None
    checkpoint_data: dict[str, Any] = field(default_factory=dict)
    # Consensus/approval
    approval_required: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    # Lifecycle
    retired_at: Optional[str] = None


def update_resource_usage(self, task_id: str, resource_delta: dict[str, float]) -> bool:
    """Update resource usage for a task. Returns True if successful."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task:
            return False
        # Get current usage
        current = task.quota_usage
        # Apply delta
        for key, delta in resource_delta.items():
            if key in current:
                current[key] = max(0, current[key] + delta)
        task.quota_usage = current
        # Persist updated task
        with self._task_lock:
            self._tasks[task_id] = task
        return True

def get_resource_usage(self, task_id: str) -> Optional[dict[str, float]]:
    """Get resource usage for a task."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task:
            return None
        return task.quota_usage

def check_quotas(self, task_id: str, quota_limits: dict[str, float]) -> bool:
    """Check if task resource usage is within quota limits. Returns True if within limits."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task:
            return True  # No task = no quota violation
        usage = task.quota_usage
        for key, limit in quota_limits.items():
            if usage.get(key, 0) > limit:
                return False
        return True


# Checkpoint and recovery management
def create_checkpoint(self, task_id: str, data: dict[str, Any] = None) -> Optional[str]:
    """Create a checkpoint for a kernel task. Returns the checkpoint_id."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task:
            return None
        checkpoint_id = f"cp-{uuid.uuid4().hex[:12]}"
        task.checkpoint_id = checkpoint_id
        task.checkpoint_data = data or {}
        task.checkpoint_data["created_at"] = datetime.now(timezone.utc).isoformat()
        with self._task_lock:
            self._tasks[task_id] = task
        return checkpoint_id

def resume_from_checkpoint(self, task_id: str, checkpoint_id: str) -> bool:
    """Resume a kernel task from a checkpoint. Returns True if successful."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task or task.checkpoint_id != checkpoint_id:
            return False
        # Validate checkpoint data integrity
        if "completed_at" in task.checkpoint_data:
            # Task was already completed - don't resume
            return False
        # Restore task state from checkpoint
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        with self._task_lock:
            self._tasks[task_id] = task
        return True

def get_checkpoint(self, task_id: str) -> Optional[dict[str, Any]]:
    """Get checkpoint data for a kernel task."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task:
            return None
        return task.checkpoint_data

def check_deadline(self, task_id: str) -> bool:
    """Check if a task has exceeded its deadline. Returns True if deadline exceeded."""
    with self._task_lock:
        task = self._tasks.get(task_id)
        if not task or not task.deadline:
            return False
        deadline_dt = datetime.fromisoformat(task.deadline)
        if datetime.now(timezone.utc) > deadline_dt:
            task.status = TaskStatus.TIMED_OUT
            task.error = "Task exceeded deadline"
            task.completed_at = datetime.now(timezone.utc).isoformat()
            with self._task_lock:
                self._tasks[task_id] = task
            return True
        return False


class AIOperatingSystem:
    """AI Operating System Core — coordinates all runtimes for autonomous engineering operations."""

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

        # Kernel task tracking
        self._tasks: dict[str, KernelTask] = {}
        self._task_lock = Lock()

        self.status = RuntimeStatus.RUNNING

    def get_task(self, task_id: str) -> Optional[KernelTask]:
        with self._task_lock:
            return self._tasks.get(task_id)

    def create_task(self, task: KernelTask) -> str:
        """Create a new kernel task. Returns the task_id."""
        with self._task_lock:
            if task.task_id in self._tasks:
                raise ValueError(f"Task {task.task_id} already exists.")
            self._tasks[task.task_id] = task
        return task.task_id

    def get_metrics(self) -> RuntimeMetrics:
        with self._task_lock:
            tasks = list(self._tasks.values())
        return RuntimeMetrics(
            agents_active=self.agent_runtime.active_count(),
            agents_idle=self.agent_runtime.idle_count(),
            agents_error=self.agent_runtime.error_count(),
            tasks_queued=sum(1 for t in tasks if t.status == TaskStatus.QUEUED),
            tasks_completed=sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            tasks_failed=sum(1 for t in tasks if t.status in (TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMED_OUT)),
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
        # Stop all kernel tasks
        with self._task_lock:
            for task in self._tasks.values():
                if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    task.status = TaskStatus.CANCELLED
            self._tasks.clear()


class AgentRuntime:
    """Manages agent lifecycle, assignment, and coordination."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.agents: dict[str, Agent] = {}
        self._tasks: dict[str, KernelTask] = {}
        self._task_lock = Lock()
        self._lock = Lock()

    def register_agent(self, name: str, role: str, capabilities: list[str] = None, 
                       max_autonomy: str = "medium") -> Agent:
        """Register a new agent with capabilities and autonomy level."""
        aid = f"agent-{uuid.uuid4().hex[:12]}"
        agent = Agent(
            id=aid, name=name, role=role,
            capabilities=capabilities or [],
            max_autonomy=max_autonomy,
            created_at=datetime.now(timezone.utc).isoformat(),
            last_active=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.agents[aid] = agent
        return agent

    def assign_task(self, agent_id: str, task_id: str) -> bool:
        """Assign a task to an agent. Returns True if successful."""
        with self._lock:
            agent = self.agents.get(agent_id)
            if not agent or agent.status != AgentStatus.IDLE:
                return False
            # Check capability compatibility
            task = self.os.get_task(task_id)
            if task:
                # Verify agent has required capabilities
                required_caps = set(task.capabilities or [])
                agent_caps = set(agent.capabilities or [])
                if required_caps and not required_caps.issubset(agent_caps):
                    return False
                agent.status = AgentStatus.BUSY
                agent.current_task = task_id
            else:
                agent.status = AgentStatus.BUSY
                agent.current_task = task_id
            agent.last_active = datetime.now(timezone.utc).isoformat()
        return True

    def complete_task(self, agent_id: str, task_id: str, success: bool = True):
        """Complete a task assigned to an agent."""
        with self._lock:
            agent = self.agents.get(agent_id)
            task = self.os.get_task(task_id) if hasattr(self.os, 'get_task') else None
            if not agent:
                return
            agent.status = AgentStatus.IDLE
            agent.current_task = None
            agent.task_count += 1
            if not success:
                agent.success_rate = (agent.success_rate * (agent.task_count - 1)) / max(agent.task_count, 1)
            agent.last_active = datetime.now(timezone.utc).isoformat()
            # Update task status
            if task:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc).isoformat()
                with self._task_lock:
                    if task.task_id in self._tasks:
                        self._tasks[task.task_id] = task

    def find_available(self, capability: str = "") -> Optional[Agent]:
        """Find an available agent with optional capability filter."""
        for agent in self.agents.values():
            if agent.status == AgentStatus.IDLE:
                if not capability or capability in agent.capabilities:
                    return agent
        return None

    def find_best(self, task_requirements: list[str]) -> Optional[Agent]:
        """Find the best agent for given task requirements."""
        best = None
        best_score = -1
        with self._lock:
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

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID."""
        with self._lock:
            return self.agents.get(agent_id)

    def register_task(self, task: KernelTask) -> None:
        """Register a kernel task for tracking."""
        with self._task_lock:
            self._tasks[task.task_id] = task

    def unregister_task(self, task_id: str) -> None:
        """Unregister a kernel task."""
        with self._task_lock:
            self._tasks.pop(task_id, None)


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
    """Task queue, execution, and result tracking integrated with kernel tasks."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.queue: list[KernelTask] = []
        self.completed: list[KernelTask] = []
        self.failed: list[KernelTask] = []
        self._lock = Lock()

    def enqueue(self, task: KernelTask) -> str:
        """Enqueue a kernel task. Returns the task_id."""
        with self._lock:
            task_id = task.task_id
            task.status = TaskStatus.QUEUED
            task.created_at = datetime.now(timezone.utc).isoformat()
            self.queue.append(task)
        return task_id

    def dequeue(self) -> Optional[KernelTask]:
        """Dequeue the next task. Returns None if queue is empty."""
        with self._lock:
            if not self.queue:
                return None
            return self.queue.pop(0)

    def complete(self, task_id: str, result: Any = None):
        """Mark a task as completed."""
        with self._lock:
            self.queue[:] = [t for t in self.queue if t.task_id != task_id]
            # Find and update the task
            for t in self.completed:
                if t.task_id == task_id:
                    t.status = TaskStatus.COMPLETED
                    t.completed_at = datetime.now(timezone.utc).isoformat()
                    t.duration_ms = (datetime.now(timezone.utc) - 
                                     datetime.fromisoformat(t.created_at)).total_seconds() * 1000
                    return
            # If not found in completed list, add it
            self.completed.append(KernelTask(
                task_id=task_id, status=TaskStatus.COMPLETED,
                created_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            ))

    def fail(self, task_id: str, error: str):
        """Mark a task as failed."""
        with self._lock:
            self.queue[:] = [t for t in self.queue if t.task_id != task_id]
            # Find and update the task
            for t in self.failed:
                if t.task_id == task_id:
                    t.status = TaskStatus.FAILED
                    t.error = error
                    t.completed_at = datetime.now(timezone.utc).isoformat()
                    return
            # If not found in failed list, add it
            self.failed.append(KernelTask(
                task_id=task_id, status=TaskStatus.FAILED,
                error=error, created_at=datetime.now(timezone.utc).isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            ))

    def queued_count(self) -> int:
        return len(self.queue)

    def completed_count(self) -> int:
        return len(self.completed)

    def failed_count(self) -> int:
        return len(self.failed)

    def get_task(self, task_id: str) -> Optional[KernelTask]:
        """Get a task by ID from the execution runtime."""
        with self._lock:
            for t in self.queue + self.completed + self.failed:
                if t.task_id == task_id:
                    return t
        return None


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
    """Time-based and event-based task scheduling with priority and deadline support."""

    def __init__(self, os: AIOperatingSystem):
        self.os = os
        self.status = RuntimeStatus.RUNNING
        self.tasks: dict[str, KernelTask] = {}
        self._lock = Lock()

    def schedule(self, name: str, interval_seconds: int, priority: str = "normal", 
                 callback: str = "", max_retries: int = 3, deadline: Optional[str] = None) -> str:
        """Schedule a kernel task with priority and optional deadline."""
        tid = f"sched-{uuid.uuid4().hex[:12]}"
        task = KernelTask(
            id=tid, name=name, priority=priority, interval_seconds=interval_seconds,
            callback=callback, max_retries=max_retries,
            deadline=deadline,
            next_run=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self.tasks[tid] = task
        return tid

    def get_due(self) -> list[KernelTask]:
        """Get due tasks sorted by priority (critical > high > normal > low > background)."""
        now = datetime.now(timezone.utc)
        due = []
        with self._lock:
            for task in self.tasks.values():
                if task.next_run is None:
                    due.append(task)
                    continue
                try:
                    if now >= datetime.fromisoformat(task.next_run):
                        due.append(task)
                except (ValueError, TypeError):
                    due.append(task)
        # Sort by priority (critical=5, high=4, normal=3, low=2, background=1)
        priority_order = {"critical": 5, "high": 4, "normal": 3, "low": 2, "background": 1}
        due.sort(key=lambda t: priority_order.get(t.priority, 0), reverse=True)
        return due

    def mark_run(self, task_id: str):
        """Mark a task as run and advance its next run time."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                task.last_run = datetime.now(timezone.utc).isoformat()
                if task.interval_seconds and task.interval_seconds > 0:
                    task.next_run = (datetime.now(timezone.utc) + 
                                     timedelta(seconds=task.interval_seconds)).isoformat()

    def cancel(self, task_id: str):
        """Cancel a scheduled task."""
        with self._lock:
            self.tasks.pop(task_id, None)

    def set_deadline(self, task_id: str, deadline: str):
        """Set a deadline for a scheduled task."""
        with self._lock:
            task = self.tasks.get(task_id)
            if task:
                task.deadline = deadline


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
