"""Workflow DAG construction and validation (Volume 33).

Represents the step graph of a workflow as a DAG. Dependencies are declared
via `depends_on`; steps without dependencies follow declaration order.
Validation detects cycles, unknown step types, missing dependencies and
self-references before any execution.
"""
from typing import Optional

from .workflow import WorkflowSpec, WorkflowStep, STEP_TYPES


class DagError(Exception):
    pass


def adjacency(spec: WorkflowSpec) -> dict[str, list[str]]:
    """step_id -> list of step_ids it depends on."""
    adj: dict[str, list[str]] = {}
    for step in spec.flat_steps():
        deps = [d for d in step.depends_on if d]
        adj[step.id] = dedupe(deps)
    return adj


def dedupe(items: list[str]) -> list[str]:
    out = []
    for i in items:
        if i not in out:
            out.append(i)
    return out


def validate_dag(spec: WorkflowSpec) -> list[str]:
    """Returns a list of validation errors ([] when the DAG is valid)."""
    errors: list[str] = []
    steps = spec.flat_steps()
    ids = [s.id for s in steps]
    if len(set(ids)) != len(ids):
        errors.append("duplicate step ids")
    for step in steps:
        if step.type not in STEP_TYPES:
            errors.append(f"step '{step.id}': unknown type '{step.type}'")
        if step.id in step.depends_on:
            errors.append(f"step '{step.id}': self dependency")
        for dep in step.depends_on:
            if dep not in ids:
                errors.append(f"step '{step.id}': unknown dependency '{dep}'")
        if step.type in ("subworkflow",) and not step.subworkflow_id:
            errors.append(f"step '{step.id}': subworkflow_id required")
        if step.type == "tool" and not step.action:
            errors.append(f"step '{step.id}': tool step requires 'action'")
    if errors:
        return errors
    adj = adjacency(spec)
    try:
        topological_order(adj)
    except DagError as exc:
        errors.append(str(exc))
    return errors


def topological_order(adj: dict[str, list[str]]) -> list[str]:
    """Kahn's algorithm; raises DagError on cycles. adj maps a node to its
    dependencies, so a node is ready once ALL its dependencies are done."""
    dependents: dict[str, list[str]] = {node: [] for node in adj}
    for node in adj:
        for dep in adj[node]:
            if dep not in dependents:
                raise DagError(f"unknown dependency '{dep}'")
            dependents[dep].append(node)
    remaining = {node: len(adj[node]) for node in adj}
    ready = [n for n, count in remaining.items() if count == 0]
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for dependent in dependents[node]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)
    if len(order) != len(adj):
        raise DagError("workflow contains a cycle")
    return order


def execution_order(spec: WorkflowSpec) -> list[WorkflowStep]:
    """Steps in a valid execution order (dependencies first)."""
    adj = adjacency(spec)
    order_ids = topological_order(adj)
    by_id = {s.id: s for s in spec.flat_steps()}
    return [by_id[sid] for sid in order_ids if sid in by_id]


def ready_steps(spec: WorkflowSpec, completed: set[str]) -> list[WorkflowStep]:
    """Currently executable steps: dependencies satisfied and not completed."""
    adj = adjacency(spec)
    by_id = {s.id: s for s in spec.flat_steps()}
    ready = []
    for sid, deps in adj.items():
        if sid in completed:
            continue
        if all(d in completed for d in deps):
            ready.append(by_id[sid])
    return ready


def describe(spec: WorkflowSpec) -> dict:
    """Structural description used by the simulator / dry-run."""
    adj = adjacency(spec)
    try:
        order = topological_order(adj)
        acyclic = True
    except DagError:
        order = []
        acyclic = False
    return {"workflow_id": spec.workflow_id, "steps": len(spec.flat_steps()),
            "dependencies": adj, "execution_order": order, "acyclic": acyclic,
            "trigger": spec.trigger, "version": spec.version,
            "status": spec.status, "risk_levels": _risk_summary(spec)}


def _risk_summary(spec: WorkflowSpec) -> dict:
    summary = {"low": 0, "medium": 0, "high": 0}
    for step in spec.flat_steps():
        key = step.risk if step.risk in summary else "medium"
        summary[key] += 1
    return summary


def compile_step_mapping(spec: WorkflowSpec) -> dict[str, WorkflowStep]:
    return {s.id: s for s in spec.flat_steps()}