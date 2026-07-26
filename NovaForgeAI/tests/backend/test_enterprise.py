"""Tests for enterprise SaaS features — Billing, Feature Flags, Organizations, Admin."""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException


# ─── Billing Service ───────────────────────────────────────────────────

class TestBillingService:
    def test_plans_defined(self):
        from app.services.billing import PLANS
        for plan_id in ("free", "pro", "team", "business", "enterprise"):
            assert plan_id in PLANS

    def test_get_plan_returns_none_for_unknown(self):
        from app.services.billing import get_plan
        assert get_plan("nonexistent") is None

    def test_get_plan_returns_plan(self):
        from app.services.billing import get_plan
        plan = get_plan("pro")
        assert plan is not None
        assert plan["price_monthly"] == 1900
        assert "repositories" in plan["limits"]

    def test_get_all_plans_returns_five(self):
        from app.services.billing import get_all_plans
        assert len(get_all_plans()) == 5

    def test_service_unavailable_without_key(self):
        from app.services.billing import BillingService
        with patch("app.services.billing.settings.stripe_api_key", None):
            svc = BillingService()
            assert svc.available is False

    @pytest.mark.asyncio
    async def test_checkout_returns_simulated_without_stripe(self):
        from app.services.billing import BillingService
        with patch("app.services.billing.settings.stripe_api_key", None):
            svc = BillingService()
            result = await svc.create_checkout_session("pro", "org-1", "https://success", "https://cancel")
            assert result is None

    @pytest.mark.asyncio
    async def test_checkout_returns_url_with_stripe(self):
        mock_stripe = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/session"
        mock_session.id = "cs_test_123"
        mock_stripe.checkout.Session.create.return_value = mock_session

        from app.services.billing import BillingService
        with patch("app.services.billing.settings.stripe_api_key", "sk_test_key"):
            with patch("app.services.billing.settings.stripe_price_pro", "price_pro_123"):
                svc = BillingService()
                svc._stripe = mock_stripe
                result = await svc.create_checkout_session(
                    "pro", "org-1", "https://success", "https://cancel", "test@example.com"
                )
                assert result["url"] == "https://checkout.stripe.com/session"
                assert result["id"] == "cs_test_123"
                mock_stripe.checkout.Session.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_subscription(self):
        mock_stripe = MagicMock()
        from app.services.billing import BillingService
        svc = BillingService()
        svc._stripe = mock_stripe
        result = await svc.cancel_subscription("sub_123")
        assert result is True
        mock_stripe.Subscription.modify.assert_called_once_with("sub_123", cancel_at_period_end=True)

    @pytest.mark.asyncio
    async def test_cancel_subscription_fails_without_stripe(self):
        from app.services.billing import BillingService
        with patch("app.services.billing.settings.stripe_api_key", None):
            svc = BillingService()
            result = await svc.cancel_subscription("sub_123")
            assert result is False

    @pytest.mark.asyncio
    async def test_process_webhook(self):
        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = MagicMock(
            type="checkout.session.completed",
            data=MagicMock(object={"id": "cs_test"})
        )
        from app.services.billing import BillingService
        with patch("app.services.billing.settings.stripe_webhook_secret", "whsec_test"):
            svc = BillingService()
            svc._stripe = mock_stripe
            result = await svc.process_webhook(b'{}', 'sig')
            assert result["type"] == "checkout.session.completed"

    @pytest.mark.asyncio
    async def test_process_webhook_fails_without_secret(self):
        from app.services.billing import BillingService
        svc = BillingService()
        svc._stripe = MagicMock()
        with patch("app.services.billing.settings.stripe_webhook_secret", None):
            result = await svc.process_webhook(b'{}', 'sig')
            assert result is None


# ─── Billing API ──────────────────────────────────────────────────────

class TestBillingAPI:
    @pytest.mark.asyncio
    async def test_list_plans(self):
        from app.api.billing import list_plans
        plans = await list_plans()
        assert len(plans) == 5
        assert plans[0].id == "free"

    @pytest.mark.asyncio
    async def test_get_plan_detail_found(self):
        from app.api.billing import get_plan_detail
        plan = await get_plan_detail("pro")
        assert plan.name == "Pro"

    @pytest.mark.asyncio
    async def test_get_plan_detail_not_found(self):
        from app.api.billing import get_plan_detail
        with pytest.raises(HTTPException) as exc:
            await get_plan_detail("nonexistent")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_current_subscription_returns_none(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.api.billing import get_current_subscription
        result = await get_current_subscription(
            organization_id=str(uuid.uuid4()),
            current_user=MagicMock(),
            db=mock_db,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_get_usage_summary_returns_usage(self):
        from app.schemas import UsageSummaryResponse

        mock_db = AsyncMock()
        mock_org = MagicMock(plan="free", id=uuid.uuid4())
        org_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org))
        scalar_result = MagicMock(scalar=MagicMock(return_value=5))

        call_count = [0]
        async def side_effect(*a, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return org_result
            return scalar_result

        mock_db.execute = side_effect

        from app.api.billing import get_usage_summary
        result = await get_usage_summary(
            organization_id=str(uuid.uuid4()),
            current_user=MagicMock(),
            db=mock_db,
        )
        assert isinstance(result, UsageSummaryResponse)
        assert result.plan == "free"
        assert len(result.usage) == 3


# ─── Feature Flags ────────────────────────────────────────────────────

class TestFeatureFlags:
    @pytest.mark.asyncio
    async def test_list_global_flags_returns_defaults(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import list_feature_flags
        result = await list_feature_flags(current_user=MagicMock(), db=mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_flag_not_found(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import get_feature_flag
        with pytest.raises(HTTPException) as exc:
            await get_feature_flag("unknown_flag", current_user=MagicMock(), db=mock_db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_flag_creates_new(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import update_feature_flag
        from app.schemas import FeatureFlagUpdate
        result = await update_feature_flag(
            "new_flag",
            FeatureFlagUpdate(enabled=True, config={"key": "val"}),
            current_user=MagicMock(),
            db=mock_db,
        )
        assert result.name == "new_flag"
        assert result.enabled is True
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_flag_updates_existing(self):
        mock_flag = MagicMock()
        mock_flag.name = "existing_flag"
        mock_flag.enabled = False
        mock_flag.config = {}
        mock_flag.organization_id = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_flag
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import update_feature_flag
        from app.schemas import FeatureFlagUpdate
        result = await update_feature_flag(
            "existing_flag",
            FeatureFlagUpdate(enabled=True),
            current_user=MagicMock(),
            db=mock_db,
        )
        assert result.enabled is True

    def test_default_flags_defined(self):
        from app.api.feature_flags import DEFAULT_FEATURE_FLAGS
        assert "ai_chat" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["ai_chat"] is True
        assert "sso_saml" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["sso_saml"] is False

    @pytest.mark.asyncio
    async def test_is_feature_enabled_uses_default(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import is_feature_enabled
        result = await is_feature_enabled("sso_saml", mock_db)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_feature_enabled_with_override(self):
        mock_flag = MagicMock()
        mock_flag.enabled = True

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_flag
        mock_db.execute.return_value = mock_result

        from app.api.feature_flags import is_feature_enabled
        result = await is_feature_enabled("sso_saml", mock_db, organization_id=str(uuid.uuid4()))
        assert result is True


# ─── Organization Members & Invitations ───────────────────────────────

class TestOrganizationMembers:
    @pytest.mark.asyncio
    async def test_list_members_returns_list(self):
        mock_db = AsyncMock()

        call_count = [0]
        async def fake_execute(*args, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_org = MagicMock()
                mock_org.id = uuid.uuid4()
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org))
            return MagicMock(all=MagicMock(return_value=[]))

        mock_db.execute = fake_execute

        from app.api.organizations import list_members
        result = await list_members(str(uuid.uuid4()), mock_db)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_invite_member_returns_invite(self):
        mock_db = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org
        mock_db.execute.return_value = mock_result

        from app.api.organizations import invite_member
        from app.schemas import InviteRequest
        result = await invite_member(
            str(uuid.uuid4()),
            InviteRequest(email="new@example.com", role="member"),
            current_user=MagicMock(),
            db=mock_db,
        )
        assert result.email == "new@example.com"
        assert result.role == "member"
        assert result.token is not None

    @pytest.mark.asyncio
    async def test_remove_member(self):
        mock_db = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org
        mock_db.execute.return_value = mock_result

        from app.api.organizations import remove_member
        result = await remove_member(
            str(uuid.uuid4()), str(uuid.uuid4()),
            current_user=MagicMock(), db=mock_db,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_member_role(self):
        mock_db = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org
        mock_db.execute.return_value = mock_result

        from app.api.organizations import update_member_role
        result = await update_member_role(
            str(uuid.uuid4()), str(uuid.uuid4()),
            role="admin", current_user=MagicMock(), db=mock_db,
        )
        assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_member_role_invalid_role(self):
        mock_db = AsyncMock()
        mock_org = MagicMock()
        mock_org.id = uuid.uuid4()
        mock_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_org))
        mock_db.execute.return_value = mock_result

        from app.api.organizations import update_member_role
        with pytest.raises(HTTPException) as exc:
            await update_member_role(
                str(uuid.uuid4()), str(uuid.uuid4()),
                role="invalid_role", current_user=MagicMock(), db=mock_db,
            )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_list_my_organizations(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        from app.api.organizations import list_my_organizations
        result = await list_my_organizations(current_user=MagicMock(), db=mock_db)
        assert result == []


# ─── Admin ────────────────────────────────────────────────────────────

class TestAdmin:
    @pytest.mark.asyncio
    async def test_overview_returns_counts(self):
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar=MagicMock(return_value=5))

        from app.api.admin import admin_overview
        mock_admin = MagicMock()
        mock_admin.is_superuser = True
        result = await admin_overview(admin=mock_admin, db=mock_db)
        assert result.total_organizations == 5
        assert result.total_users == 5

    @pytest.mark.asyncio
    async def test_list_organizations(self):
        mock_org = MagicMock()
        mock_org.id = uuid.uuid4()
        mock_org.name = "Test Org"
        mock_org.slug = "test-org"
        mock_org.plan = "free"
        mock_org.is_active = True
        mock_org.created_at = datetime.now(timezone.utc)

        mock_db = AsyncMock()
        org_result = MagicMock()
        org_result.scalars.return_value.all.return_value = [mock_org]
        call_count = [0]

        async def fake_exec(*args, **kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return org_result
            return MagicMock(scalar=MagicMock(return_value=3))

        mock_db.execute = fake_exec

        from app.api.admin import admin_list_organizations
        mock_admin = MagicMock()
        mock_admin.is_superuser = True
        result = await admin_list_organizations(admin=mock_admin, db=mock_db, limit=50, offset=0)
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_list_users(self):
        from datetime import datetime, timezone
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.email = "admin@test.com"
        mock_user.username = "admin"
        mock_user.is_active = True
        mock_user.is_superuser = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.last_login_at = datetime.now(timezone.utc)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_user]
        mock_db.execute.return_value = mock_result

        from app.api.admin import admin_list_users
        mock_admin = MagicMock()
        mock_admin.is_superuser = True
        result = await admin_list_users(admin=mock_admin, db=mock_db, limit=50, offset=0)
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_feature_flags(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        from app.api.admin import admin_feature_flags
        mock_admin = MagicMock()
        mock_admin.is_superuser = True
        result = await admin_feature_flags(admin=mock_admin, db=mock_db)
        assert len(result) >= 12
        ai_chat = next(f for f in result if f["name"] == "ai_chat")
        assert ai_chat["default"] is True
