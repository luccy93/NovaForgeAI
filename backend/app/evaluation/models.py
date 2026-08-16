"""Evaluation domain models (Volume 34).

Pure dataclasses used across the evaluation platform: datasets, versions,
examples, runs, results, judge scores, human reviews and regression gates.
All objects serialize via DataObject.to_dict() so they can be stored in the
unified JsonFileStorage backends without extra mapping code.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.base import DataObject


@dataclass
class DatasetExample(DataObject):
    """One labelled example inside an evaluation dataset version."""

    id: str
    input: str
    context: list[str] = field(default_factory=list)
    expected_output: str = ""
    reference_answer: str = ""
    expected_files: list[str] = field(default_factory=list)
    expected_code: str = ""
    expected_citations: list[str] = field(default_factory=list)
    expected_actions: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    difficulty: str = "medium"
    tags: list[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class DatasetVersion(DataObject):
    """Immutable snapshot of a dataset's examples."""

    id: str
    dataset_id: str
    version: int
    examples: list[dict] = field(default_factory=list)
    notes: str = ""
    status: str = "draft"  # draft | published | archived
    parent_version: Optional[int] = None
    created_at: str = ""
    created_by: str = ""
    checksum: str = ""


@dataclass
class EvalDataset(DataObject):
    """A versioned, lineage-tracked evaluation dataset."""

    id: str
    name: str
    description: str = ""
    task_type: str = "qa"  # qa | code_generation | code_repair | code_review
                          # | security | testing | documentation | architecture
                          # | repository_understanding | rag | agent | multimodal
                          # | tool_use | workflow
    modality: str = "text"
    owner: str = ""
    organization_id: str = ""
    workspace: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    status: str = "active"  # active | archived
    latest_version: int = 0
    version_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class EvalResult(DataObject):
    """Scores for a single dataset example."""

    example_id: str
    scores: dict = field(default_factory=dict)
    correct: bool = True
    passed: bool = True
    latency_ms: float = 0.0
    tokens: dict = field(default_factory=dict)
    cost: float = 0.0
    error: str = ""
    trace: dict = field(default_factory=dict)
    judge_scores: list[dict] = field(default_factory=list)


@dataclass
class EvalRun(DataObject):
    """A complete benchmark run (offline or online)."""

    id: str
    dataset_id: str
    dataset_version: int
    model: str
    provider: str = ""
    prompt_version: str = ""
    agent_version: str = ""
    rag_version: str = ""
    configuration: dict = field(default_factory=dict)
    target_type: str = "model"  # model | prompt | agent | rag | workflow | multimodal | automation
    organization_id: str = ""
    status: str = "running"  # running | completed | failed | cancelled
    results: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    cost: float = 0.0
    latency_ms: float = 0.0
    errors: list[dict] = field(default_factory=list)
    traces: list[dict] = field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""
    created_by: str = ""


@dataclass
class JudgeScore(DataObject):
    """A single LLM judge decision for one criterion."""

    criterion: str
    score: float
    rationale: str = ""
    judge_model: str = ""
    confidence: float = 1.0


@dataclass
class HumanReview(DataObject):
    """One human reviewer's assessment of an output."""

    id: str
    run_id: str
    example_id: str
    reviewer: str = ""
    scores: dict = field(default_factory=dict)
    preference: str = ""  # a | b | tie
    comment: str = ""
    blind: bool = True
    created_at: str = ""


@dataclass
class PairwiseResult(DataObject):
    """Result of comparing two candidates (models/prompts/agents/RAG)."""

    id: str
    a_label: str
    b_label: str
    a_win: int = 0
    b_win: int = 0
    ties: int = 0
    preferences: list[dict] = field(default_factory=list)
    win_rate_a: float = 0.0
    win_rate_b: float = 0.0
    tie_rate: float = 0.0
    confidence: float = 0.0
    created_at: str = ""


@dataclass
class GateDecision(DataObject):
    """Regression gate verdict used by the CI/CD quality gate."""

    id: str
    baseline_run_id: str = ""
    candidate_run_id: str = ""
    verdict: str = "pass"  # pass | fail | block
    deltas: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    created_at: str = ""
