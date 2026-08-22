from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

from app.api.chat import router as chat_router
from app.api.repositories import router as repos_router
from app.api.agents import router as agents_router
from app.api.code import router as code_router
from app.api.auth import router as auth_router
from app.api.auth_v2 import router as auth_v2_router
from app.api.organizations import router as org_router
from app.api.billing import router as billing_router
from app.api.feature_flags import router as feature_flags_router
from app.api.admin import router as admin_router
from app.api.notifications import router as notifications_router
from app.api.agents_v2 import router as agents_v2_router
from app.api.webhooks import router as webhooks_router
from app.api.marketplace import router as marketplace_router
from app.api.platform import router as platform_router
from app.api.sre import router as sre_router
from app.api.ai_governance import router as ai_governance_router
from app.api.kernel import router as kernel_router
from app.api.evaluation import router as evaluation_router
from app.api.enterprise import router as enterprise_router
from app.api.sdk import router as sdk_router
from app.api.devtools import router as devtools_router
from app.api.github_integration import router as github_router
from app.api.code_intelligence_api import router as code_intelligence_router
from app.api.rag_api import router as rag_router
from app.api.automation import router as automation_router
from app.api.delivery import router as delivery_router
from app.api.security import router as security_router
from app.api.quality import router as quality_router
from app.api.incident import router as incident_router
from app.api.analytics import router as analytics_router
from app.api.knowledge_graph import router as knowledge_graph_router
from app.api.iam import router as iam_router

api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(repos_router, prefix="/repositories", tags=["Repositories"])
api_router.include_router(agents_router, prefix="/agents", tags=["Agents"])
api_router.include_router(agents_v2_router, prefix="/agents/v2", tags=["AI Agents v2"])
api_router.include_router(code_router, prefix="/code", tags=["Code Analysis"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(org_router, prefix="/organizations", tags=["Organizations"])
api_router.include_router(billing_router, prefix="/billing", tags=["Billing"])
api_router.include_router(feature_flags_router, prefix="/feature-flags", tags=["Feature Flags"])
api_router.include_router(admin_router, prefix="/admin", tags=["Admin"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(auth_v2_router, prefix="/auth", tags=["Authentication v2"])
api_router.include_router(webhooks_router, tags=["Webhooks"])
api_router.include_router(marketplace_router, tags=["Marketplace"])
api_router.include_router(platform_router, tags=["Platform"])
api_router.include_router(sre_router, prefix="/sre", tags=["SRE"])
api_router.include_router(ai_governance_router, prefix="/ai-governance", tags=["AI Governance"])
api_router.include_router(kernel_router, prefix="/kernel", tags=["Kernel"])
api_router.include_router(evaluation_router, prefix="/datasets", tags=["Datasets & Evaluations"])
api_router.include_router(enterprise_router, prefix="/enterprise", tags=["Enterprise Integrations"])
api_router.include_router(sdk_router)
api_router.include_router(devtools_router)
api_router.include_router(github_router)
api_router.include_router(code_intelligence_router, prefix="/code-intelligence", tags=["Code Intelligence"])
api_router.include_router(rag_router, tags=["Knowledge & RAG"])
api_router.include_router(automation_router, tags=["Autonomous Engineering"])
api_router.include_router(delivery_router, tags=["Software Delivery Platform"])
api_router.include_router(security_router, prefix="/security", tags=["DevSecOps Security Platform"])
api_router.include_router(quality_router, prefix="/quality", tags=["AI Quality Engine"])
api_router.include_router(incident_router, prefix="/incident", tags=["Incident Response Platform"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Unified Analytics Platform"])
api_router.include_router(knowledge_graph_router)
api_router.include_router(iam_router, prefix="/iam", tags=["Enterprise IAM"])
api_router.include_router(sre_router)
