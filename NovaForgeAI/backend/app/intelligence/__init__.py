"""NovaForge Intelligence Platform — autonomous AI software engineering intelligence services."""

from .repository_intelligence import (
    RepositoryIntelligence,
    RepositoryAnalysis,
    RepoHealthScore,
    TechDebtItem,
    SecurityRisk,
    DependencyRisk,
    DuplicateBlock,
)
from .code_quality import (
    CodeQualityService,
    CodeQualitySnapshot,
    ComplexityItem,
    MaintainabilityScore,
    QualityTrend,
    code_quality,
)
from .architecture_intelligence import (
    ArchitectureIntelligence,
    ArchitectureModel,
    ArchitectureNode,
    ArchitectureEdge,
)
from .compliance_intelligence import (
    ComplianceIntelligence,
    ComplianceReport,
    ComplianceFinding,
    compliance_intelligence,
)
from .knowledge_graph import (
    RepositoryKnowledgeGraph,
    KnowledgeNode,
    KnowledgeEdge,
    GraphSnapshot,
    NodeType,
    RelationshipType,
)
from .health_engine import (
    RepositoryHealthEngine,
    HealthScore,
    HealthSnapshot,
)
from .tech_debt_engine import (
    TechnicalDebtEngine,
    DebtItem,
    DebtReport,
    RemedyPlan,
)
from .dependency_intelligence import (
    DependencyIntelligence,
    DependencyNode,
    DependencyReport,
    SupplyChainRisk,
)
from .predictive_engineering import (
    PredictiveEngineering,
    Prediction,
    PredictionReport,
)
from .code_review import (
    AutonomousCodeReview,
    ReviewComment,
    ReviewReport,
)
from .refactoring_engine import (
    AutonomousRefactoring,
    RefactoringOperation,
    MigrationPlan,
)
from .performance_intelligence import (
    PerformanceIntelligence,
    PerformanceMetric,
    PerformanceReport,
    QueryProfile,
)
from .security_intelligence import (
    SecurityIntelligence,
    SecurityReport,
    SecretFinding,
    VulnerabilityFinding,
)
from .test_intelligence import (
    TestIntelligence,
    TestReport,
    TestCoverage,
    FlakyTest,
    MissingTest,
)
from .documentation_intelligence import (
    DocumentationIntelligence,
    DocumentationReport,
    DocGap,
    DocSection,
)
from .engineering_analytics import (
    EngineeringAnalytics,
    AnalyticsReport,
    DORAMetrics,
    ProductivityMetrics,
)
from .dashboard_engine import (
    DashboardEngine,
    Dashboard,
    DashboardSection,
    DashboardCard,
)
from .continuous_learning import (
    ContinuousLearning,
    LearnedPattern,
    LearningDomain,
)
from .autonomous_workflows import (
    AutonomousWorkflows,
    WorkflowResult,
    WorkflowSchedule,
    WorkflowFrequency,
)
from .recommendation_engine import (
    RecommendationEngine,
    Recommendation,
    RecommendationReport,
)

__all__ = [
    "RepositoryIntelligence",
    "RepositoryAnalysis",
    "RepoHealthScore",
    "TechDebtItem",
    "SecurityRisk",
    "DependencyRisk",
    "DuplicateBlock",
    "CodeQualityService",
    "CodeQualitySnapshot",
    "ComplexityItem",
    "MaintainabilityScore",
    "QualityTrend",
    "code_quality",
    "ArchitectureIntelligence",
    "ArchitectureModel",
    "ArchitectureNode",
    "ArchitectureEdge",
    "ComplianceIntelligence",
    "ComplianceReport",
    "ComplianceFinding",
    "compliance_intelligence",
    "RepositoryKnowledgeGraph",
    "KnowledgeNode",
    "KnowledgeEdge",
    "GraphSnapshot",
    "NodeType",
    "RelationshipType",
    "RepositoryHealthEngine",
    "HealthScore",
    "HealthSnapshot",
    "TechnicalDebtEngine",
    "DebtItem",
    "DebtReport",
    "RemedyPlan",
    "DependencyIntelligence",
    "DependencyNode",
    "DependencyReport",
    "SupplyChainRisk",
    "PredictiveEngineering",
    "Prediction",
    "PredictionReport",
    "AutonomousCodeReview",
    "ReviewComment",
    "ReviewReport",
    "AutonomousRefactoring",
    "RefactoringOperation",
    "MigrationPlan",
    "PerformanceIntelligence",
    "PerformanceMetric",
    "PerformanceReport",
    "QueryProfile",
    "SecurityIntelligence",
    "SecurityReport",
    "SecretFinding",
    "VulnerabilityFinding",
    "TestIntelligence",
    "TestReport",
    "TestCoverage",
    "FlakyTest",
    "MissingTest",
    "DocumentationIntelligence",
    "DocumentationReport",
    "DocGap",
    "DocSection",
    "EngineeringAnalytics",
    "AnalyticsReport",
    "DORAMetrics",
    "ProductivityMetrics",
    "DashboardEngine",
    "Dashboard",
    "DashboardSection",
    "DashboardCard",
    "ContinuousLearning",
    "LearnedPattern",
    "LearningDomain",
    "AutonomousWorkflows",
    "WorkflowResult",
    "WorkflowSchedule",
    "WorkflowFrequency",
    "RecommendationEngine",
    "Recommendation",
    "RecommendationReport",
]
