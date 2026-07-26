"""10x Enhanced service layer for Volume 30 — Enterprise Platform."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import organization_management, user_management, role_management
from . import billing_engine, subscription_manager, enterprise_audit
from . import multi_tenant, sso_engine, api_gateway, rate_limiter
from . import enterprise_search, workflow_engine, integration_hub
from . import enterprise_analytics, global_operations, backup_recovery
from . import custom_branding, enterprise_security, reporting, observability
from . import professional_services_automation, global_dashboard

logger = logging.getLogger(__name__)


class EnterprisePlatformService(AsyncService):
    def __init__(self):
        super().__init__("enterprise_platform", JsonFileStorage("data/enterprise/service.json"))
        self.orgs = organization_management.OrganizationManagement("data/enterprise/orgs")
        self.users = user_management.UserManagement("data/enterprise/users")
        self.roles = role_management.RoleManagement("data/enterprise/roles")
        self.billing = billing_engine.BillingEngine("data/enterprise/billing")
        self.subscriptions = subscription_manager.SubscriptionManager("data/enterprise/subscriptions")
        self.audit = enterprise_audit.EnterpriseAudit("data/enterprise/audit")
        self.tenant = multi_tenant.MultiTenant("data/enterprise/tenants")
        self.sso = sso_engine.SSOEngine("data/enterprise/sso")
        self.gateway = api_gateway.APIGateway("data/enterprise/gateway")
        self.rate_limiter = rate_limiter.RateLimiter("data/enterprise/rate_limits")
        self.search = enterprise_search.EnterpriseSearch("data/enterprise/search")
        self.workflows = workflow_engine.WorkflowEngine("data/enterprise/workflows")
        self.hub = integration_hub.IntegrationHub("data/enterprise/integrations")
        self.analytics = enterprise_analytics.EnterpriseAnalytics("data/enterprise/analytics")
        self.global_ops = global_operations.GlobalOperations("data/enterprise/global_ops")
        self.backup = backup_recovery.BackupRecovery("data/enterprise/backup")
        self.branding = custom_branding.CustomBranding("data/enterprise/branding")
        self.ent_sec = enterprise_security.EnterpriseSecurity("data/enterprise/security")
        self.reporting = reporting.EnterpriseReporting("data/enterprise/reports")
        self.prof_services = professional_services_automation.ProfessionalServicesAutomation("data/enterprise/prof_services")
        self.global_dashboard = global_dashboard.GlobalDashboard("data/enterprise/dashboards")
        self.obs = observability.EnterpriseObservability("data/enterprise/observability")

    async def create_organization(self, name: str, domain: str, plan: str = "free", owner_id: str = ""):
        Validator.non_empty(name, "name"); Validator.non_empty(domain, "domain")
        org = self.orgs.create(name, domain, plan, owner_id)
        tenant = self.tenant.provision(org.id, domain)
        self.subscriptions.create(org.id, plan)
        self.telemetry.increment("organizations_created")
        return {"org": org, "tenant": tenant}

    async def authenticate(self, org_id: str, email: str, provider: str = "internal", token: str = ""):
        if provider == "sso":
            return {"user": self.sso.authenticate(org_id, token)}
        return {"user": self.users.authenticate(org_id, email)}

    async def get_global_dashboard(self, org_id: str):
        return self.global_dashboard.get(org_id)

    async def health_check(self) -> dict:
        return self.health()


svc = EnterprisePlatformService()
registry.register(svc)
