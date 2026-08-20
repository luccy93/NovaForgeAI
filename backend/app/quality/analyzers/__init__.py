"""AI Software Quality Engine -- Analyzers Package (Volume 48)."""

from app.quality.analyzers.base import BaseAnalyzer, ReviewContext, AnalyzerResult
from app.quality.analyzers.correctness import CorrectnessAnalyzer
from app.quality.analyzers.performance import PerformanceAnalyzer
from app.quality.analyzers.reliability import ReliabilityAnalyzer
from app.quality.analyzers.architecture import ArchitectureAnalyzer
from app.quality.analyzers.api_compat import APICompatAnalyzer
from app.quality.analyzers.database import DatabaseAnalyzer
from app.quality.analyzers.dependency import DependencyAnalyzer
from app.quality.analyzers.documentation import DocumentationAnalyzer
from app.quality.analyzers.dead_code import DeadCodeAnalyzer
from app.quality.analyzers.test_quality import TestQualityAnalyzer
from app.quality.analyzers.ai_review import AIReviewAnalyzer
from app.quality.analyzers.code_smells import CodeSmellAnalyzer

ANALYZER_REGISTRY: dict[str, type[BaseAnalyzer]] = {
    "correctness": CorrectnessAnalyzer,
    "performance": PerformanceAnalyzer,
    "reliability": ReliabilityAnalyzer,
    "architecture": ArchitectureAnalyzer,
    "api_compat": APICompatAnalyzer,
    "database": DatabaseAnalyzer,
    "dependency": DependencyAnalyzer,
    "documentation": DocumentationAnalyzer,
    "dead_code": DeadCodeAnalyzer,
    "test_quality": TestQualityAnalyzer,
    "ai_review": AIReviewAnalyzer,
    "code_smells": CodeSmellAnalyzer,
    "maintainability": CodeSmellAnalyzer,
}


def get_analyzers(names: list[str]) -> list[BaseAnalyzer]:
    analyzers = []
    for name in names:
        cls = ANALYZER_REGISTRY.get(name)
        if cls:
            analyzers.append(cls())
    return analyzers
