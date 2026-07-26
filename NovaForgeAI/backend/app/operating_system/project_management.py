"""Project Management — automated task creation, prioritization, effort estimation, sprint planning, velocity tracking, milestones."""

import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TaskStatus(Enum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class Priority(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    status: TaskStatus = TaskStatus.BACKLOG
    story_points: float = 0.0
    estimated_hours: float = 0.0
    actual_hours: float = 0.0
    assignee: str = ""
    sprint_id: Optional[str] = None
    milestone_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Sprint:
    id: str
    name: str
    goal: str = ""
    start_date: str = ""
    end_date: str = ""
    status: str = "planned"  # planned, active, completed
    tasks: list[str] = field(default_factory=list)
    velocity_planned: float = 0.0
    velocity_actual: float = 0.0
    created_at: str = ""


@dataclass
class Milestone:
    id: str
    name: str
    description: str = ""
    target_date: str = ""
    status: str = "planned"
    tasks: list[str] = field(default_factory=list)
    completion_pct: float = 0.0


@dataclass
class ProjectReport:
    project_id: str
    project_name: str
    timestamp: str
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    backlog_tasks: int = 0
    blocked_tasks: int = 0
    total_story_points: float = 0.0
    completed_story_points: float = 0.0
    velocity: float = 0.0
    burndown: list[dict] = field(default_factory=list)
    sprint_summary: dict[str, Any] = field(default_factory=dict)
    milestone_progress: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class ProjectManagement:
    """Automated project management — tasks, sprints, milestones, velocity, burndown, reports."""

    def __init__(self, project_id: str = "", project_name: str = ""):
        self.project_id = project_id or f"proj-{uuid.uuid4().hex[:12]}"
        self.project_name = project_name or "Default Project"
        self.tasks: dict[str, Task] = {}
        self.sprints: dict[str, Sprint] = {}
        self.milestones: dict[str, Milestone] = {}
        self._velocity_history: list[float] = []

    def create_task(self, title: str, description: str = "", priority: Priority = Priority.MEDIUM,
                    story_points: float = 0.0, estimated_hours: float = 0.0, tags: list[str] = None,
                    dependencies: list[str] = None) -> Task:
        tid = f"task-{uuid.uuid4().hex[:12]}"
        task = Task(
            id=tid, title=title, description=description,
            priority=priority, story_points=story_points,
            estimated_hours=estimated_hours, tags=tags or [],
            dependencies=dependencies or [],
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.tasks[tid] = task
        return task

    def update_status(self, task_id: str, status: TaskStatus):
        task = self.tasks.get(task_id)
        if not task:
            return
        task.status = status
        task.updated_at = datetime.now(timezone.utc).isoformat()
        if status == TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc).isoformat()

    def create_sprint(self, name: str, goal: str = "", duration_days: int = 14,
                      start_date: Optional[str] = None) -> Sprint:
        sid = f"sprint-{uuid.uuid4().hex[:12]}"
        start = start_date or datetime.now(timezone.utc).isoformat()[:10]
        end = (datetime.fromisoformat(start) + timedelta(days=duration_days)).isoformat()[:10]
        sprint = Sprint(id=sid, name=name, goal=goal, start_date=start, end_date=end)
        self.sprints[sid] = sprint
        return sprint

    def assign_to_sprint(self, task_id: str, sprint_id: str) -> bool:
        task = self.tasks.get(task_id)
        sprint = self.sprints.get(sprint_id)
        if not task or not sprint:
            return False
        task.sprint_id = sprint_id
        task.status = TaskStatus.READY
        if task_id not in sprint.tasks:
            sprint.tasks.append(task_id)
            sprint.velocity_planned += task.story_points
        return True

    def create_milestone(self, name: str, description: str = "", target_date: str = "") -> Milestone:
        mid = f"milestone-{uuid.uuid4().hex[:12]}"
        milestone = Milestone(id=mid, name=name, description=description, target_date=target_date)
        self.milestones[mid] = milestone
        return milestone

    def assign_to_milestone(self, task_id: str, milestone_id: str) -> bool:
        task = self.tasks.get(task_id)
        milestone = self.milestones.get(milestone_id)
        if not task or not milestone:
            return False
        task.milestone_id = milestone_id
        if task_id not in milestone.tasks:
            milestone.tasks.append(task_id)
        return True

    def estimate_effort(self, task: Task) -> float:
        base = 1.0
        priority_mult = {Priority.CRITICAL: 2.0, Priority.HIGH: 1.5, Priority.MEDIUM: 1.0, Priority.LOW: 0.5}
        effort = base * priority_mult.get(task.priority, 1.0)
        if task.tags:
            effort += len(task.tags) * 0.25
        if task.dependencies:
            effort += len(task.dependencies) * 0.5
        return round(effort * task.story_points if task.story_points else effort, 1)

    def prioritize_tasks(self, max_tasks: int = 10) -> list[Task]:
        scored = []
        for task in self.tasks.values():
            if task.status in (TaskStatus.DONE, TaskStatus.CANCELLED):
                continue
            priority_score = task.priority.value * 10
            blocked_penalty = 5 if task.status == TaskStatus.BLOCKED else 0
            dependency_bonus = len(task.dependencies) * 2
            age_bonus = 0
            if task.created_at:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(task.created_at)).days
                age_bonus = min(5, age)
            score = priority_score - blocked_penalty + dependency_bonus + age_bonus
            scored.append((score, task))

        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:max_tasks]]

    def generate_sprint_plan(self, sprint_id: str, capacity_hours: float = 80.0) -> list[Task]:
        sprint = self.sprints.get(sprint_id)
        if not sprint:
            return []

        planned = []
        remaining_hours = capacity_hours

        for task in self.prioritize_tasks():
            if task.sprint_id or task.status == TaskStatus.DONE:
                continue
            effort = self.estimate_effort(task)
            if effort <= remaining_hours:
                self.assign_to_sprint(task.id, sprint_id)
                planned.append(task)
                remaining_hours -= effort
            if remaining_hours < 1:
                break

        return planned

    def calculate_velocity(self, sprint_id: str) -> float:
        sprint = self.sprints.get(sprint_id)
        if not sprint:
            return 0.0
        completed_points = sum(
            self.tasks[tid].story_points for tid in sprint.tasks
            if tid in self.tasks and self.tasks[tid].status == TaskStatus.DONE
        )
        sprint.velocity_actual = completed_points
        self._velocity_history.append(completed_points)
        return completed_points

    def get_burndown(self, sprint_id: str) -> list[dict]:
        sprint = self.sprints.get(sprint_id)
        if not sprint:
            return []

        total_points = sprint.velocity_planned
        if not sprint.start_date or not sprint.end_date:
            return []

        try:
            start = datetime.fromisoformat(sprint.start_date)
            end = datetime.fromisoformat(sprint.end_date)
        except (ValueError, TypeError):
            return []

        total_days = max((end - start).days, 1)
        burndown = []
        remaining = total_points

        for day in range(total_days + 1):
            current_date = start + timedelta(days=day)
            ideal = total_points * (1 - day / total_days)
            done_count = sum(
                1 for tid in sprint.tasks
                if tid in self.tasks and self.tasks[tid].status == TaskStatus.DONE
                and self.tasks[tid].completed_at
                and datetime.fromisoformat(self.tasks[tid].completed_at).date() <= current_date.date()
            )
            remaining = total_points - done_count
            burndown.append({
                "date": current_date.isoformat()[:10],
                "day": day,
                "ideal": round(ideal, 1),
                "actual": round(remaining, 1),
            })

        return burndown

    def track_progress(self, milestone_id: str) -> dict:
        milestone = self.milestones.get(milestone_id)
        if not milestone:
            return {"error": "Milestone not found"}

        total = len(milestone.tasks)
        if total == 0:
            completion = 0.0
        else:
            done = sum(1 for tid in milestone.tasks if tid in self.tasks and self.tasks[tid].status == TaskStatus.DONE)
            completion = (done / total) * 100

        milestone.completion_pct = round(completion, 1)
        return {
            "milestone_id": milestone_id,
            "name": milestone.name,
            "total_tasks": total,
            "completed": sum(1 for tid in milestone.tasks if tid in self.tasks and self.tasks[tid].status == TaskStatus.DONE),
            "in_progress": sum(1 for tid in milestone.tasks if tid in self.tasks and self.tasks[tid].status == TaskStatus.IN_PROGRESS),
            "completion_pct": milestone.completion_pct,
        }

    def generate_report(self) -> ProjectReport:
        tasks_list = list(self.tasks.values())
        report = ProjectReport(
            project_id=self.project_id,
            project_name=self.project_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_tasks=len(tasks_list),
            completed_tasks=sum(1 for t in tasks_list if t.status == TaskStatus.DONE),
            in_progress_tasks=sum(1 for t in tasks_list if t.status == TaskStatus.IN_PROGRESS),
            backlog_tasks=sum(1 for t in tasks_list if t.status == TaskStatus.BACKLOG),
            blocked_tasks=sum(1 for t in tasks_list if t.status == TaskStatus.BLOCKED),
            total_story_points=sum(t.story_points for t in tasks_list),
            completed_story_points=sum(t.story_points for t in tasks_list if t.status == TaskStatus.DONE),
        )

        if self._velocity_history:
            report.velocity = round(sum(self._velocity_history[-5:]) / max(len(self._velocity_history[-5:]), 1), 1)

        active_sprints = [s for s in self.sprints.values() if s.status == "active"]
        if active_sprints:
            s = active_sprints[0]
            report.sprint_summary = {
                "name": s.name,
                "start": s.start_date,
                "end": s.end_date,
                "planned_points": s.velocity_planned,
                "actual_points": s.velocity_actual,
                "burndown": self.get_burndown(s.id),
            }

        report.milestone_progress = [
            self.track_progress(m.id) for m in self.milestones.values()
        ]

        if report.blocked_tasks > 0:
            report.recommendations.append(f"Unblock {report.blocked_tasks} blocked tasks")
        if report.backlog_tasks > 20:
            report.recommendations.append(f"Prioritize backlog of {report.backlog_tasks} tasks")
        if report.velocity == 0 and report.total_tasks > 0:
            report.recommendations.append("Track sprint velocity to improve estimation accuracy")

        return report
