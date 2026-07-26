"""10x Enhanced service layer for Volume 24 — Release Engineering."""
import logging, asyncio
from typing import Optional
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import release_manager, deployment_manager, environment_manager, pipeline_manager
from . import artifact_manager, approval_manager, rollback_manager, migration_manager
from . import version_manager, quality_gate_engine, branch_manager, pr_automation
from . import build_system, change_management, feature_flags, changelog_engine
from . import deployment_intelligence, compliance_gates, observability, reporting, enterprise_features

logger = logging.getLogger(__name__)


class ReleaseService(AsyncService):
    def __init__(self):
        super().__init__("release_engineering", JsonFileStorage("data/release_engineering/service.json"))
        self.release_mgr = release_manager.ReleaseManager("data/release_engineering/releases")
        self.deploy_mgr = deployment_manager.DeploymentManager("data/release_engineering/deployments")
        self.env_mgr = environment_manager.EnvironmentManager("data/release_engineering/environments")
        self.pipe_mgr = pipeline_manager.PipelineManager("data/release_engineering/pipelines")
        self.artifact_mgr = artifact_manager.ArtifactManager("data/release_engineering/artifacts")
        self.approval_mgr = approval_manager.ApprovalManager("data/release_engineering/approvals")
        self.rollback_mgr = rollback_manager.RollbackManager("data/release_engineering/rollbacks")
        self.migration_mgr = migration_manager.MigrationManager("data/release_engineering/migrations")
        self.version_mgr = version_manager.VersionManager("data/release_engineering/versions")
        self.gate_engine = quality_gate_engine.QualityGateEngine("data/release_engineering/gates")
        self.branch_mgr = branch_manager.BranchManager("data/release_engineering/branches")
        self.pr_auto = pr_automation.PRAutomation("data/release_engineering/prs")
        self.build_sys = build_system.BuildSystem("data/release_engineering/builds")
        self.change_mgr = change_management.ChangeManagement("data/release_engineering/changes")
        self.flags = feature_flags.FeatureFlags("data/release_engineering/flags")
        self.changelog = changelog_engine.ChangelogEngine("data/release_engineering/changelogs")
        self.deploy_intel = deployment_intelligence.DeploymentIntelligence("data/release_engineering/intel")
        self.compliance = compliance_gates.ComplianceGates("data/release_engineering/compliance")
        self.obs = observability.Observability("data/release_engineering/obs")
        self.reporting = reporting.Reporting("data/release_engineering/reports")
        self.enterprise = enterprise_features.EnterpriseFeatures("data/release_engineering/enterprise")

    async def create_release(self, org_id: str, name: str, version: str, channel: str = "stable", author_id: str = "", description: str = ""):
        Validator.non_empty(org_id, "org_id"); Validator.non_empty(name, "name"); Validator.non_empty(version, "version")
        async with self._lock(f"release_{org_id}"):
            rel = self.release_mgr.create_release(org_id, name, version, channel, author_id, description)
            self.telemetry.increment("releases_created")
            return rel

    async def deploy(self, org_id: str, release_id: str, environment: str, strategy: str = "rolling"):
        Validator.non_empty(org_id, "org_id"); Validator.non_empty(release_id, "release_id")
        dep = self.deploy_mgr.create(org_id, release_id, environment, deployment_manager.DeploymentStrategy(strategy))
        self.telemetry.increment("deployments_created")
        return dep

    async def get_pipeline_status(self, org_id: str) -> dict:
        pipes = self.pipe_mgr.list_by_org(org_id) if hasattr(self.pipe_mgr, 'list_by_org') else []
        return {"pipelines": len(pipes), "status": "operational"}

    async def health_check(self) -> dict:
        return self.health()


svc = ReleaseService()
registry.register(svc)
