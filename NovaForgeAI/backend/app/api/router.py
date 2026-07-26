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
