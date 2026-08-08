"""Compliance service — GDPR, data retention, right to erasure, consent management."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession


class ComplianceService:
    """Enterprise compliance — SOC2, GDPR, CCPA, ISO 27001 alignment."""

    RETENTION_DAYS = {
        "audit_logs": 365 * 3,
        "analytics_events": 365 * 2,
        "agent_runs": 365 * 1,
        "usage_records": 365 * 2,
        "messages": 365 * 2,
        "sessions": 365 * 1,
        "notifications": 365 * 1,
        "security_reports": 365 * 3,
    }

    @staticmethod
    async def export_user_data(user_id: str, db: AsyncSession) -> dict:
        data = {}
        tables = {
            "users": "SELECT * FROM users WHERE id = :uid",
            "user_sessions": "SELECT * FROM user_sessions WHERE user_id = :uid",
            "api_keys": "SELECT * FROM api_keys WHERE user_id = :uid",
            "conversations": "SELECT * FROM conversations WHERE user_id = :uid",
            "messages": "SELECT m.* FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.user_id = :uid",
            "notifications": "SELECT * FROM notifications WHERE user_id = :uid",
            "agent_runs": "SELECT * FROM agent_runs WHERE user_id = :uid",
        }
        for name, query in tables.items():
            try:
                result = await db.execute(text(query).params(uid=user_id))
                rows = result.mappings().all()
                data[name] = [dict(row) for row in rows]
            except Exception:
                data[name] = []
        return data

    @staticmethod
    async def delete_user_data(user_id: str, db: AsyncSession) -> dict:
        deleted = {}
        tables = [
            "user_sessions", "api_keys", "notifications",
            "messages", "conversations", "agent_runs",
        ]
        for table in tables:
            try:
                result = await db.execute(
                    text(f"DELETE FROM {table} WHERE user_id = :uid").params(uid=user_id)
                )
                deleted[table] = result.rowcount
            except Exception:
                deleted[table] = 0
        return deleted

    @staticmethod
    async def anonymize_user(user_id: str, db: AsyncSession) -> None:
        anon_email = f"deleted-{user_id[:8]}@novaforge.ai"
        await db.execute(
            text("""
                UPDATE users SET
                    email = :anon_email,
                    username = :anon_username,
                    hashed_password = '',
                    full_name = '[deleted]',
                    avatar_url = NULL,
                    bio = NULL,
                    profile = '{"deleted": true}'::jsonb,
                    is_active = false
                WHERE id = :uid
            """).params(anon_email=anon_email, anon_username=f"user_{user_id[:8]}", uid=user_id)
        )

    @staticmethod
    async def get_retention_policy() -> dict:
        return dict(ComplianceService.RETENTION_DAYS)

    @staticmethod
    async def get_compliance_report(org_id: str, db: AsyncSession) -> dict:
        report = {"organization_id": org_id, "checks": []}

        checks = [
            ("audit_logs_present", "SELECT COUNT(*) FROM audit_logs WHERE organization_id = :oid"),
            ("mfa_enabled_users", """
                SELECT COUNT(*) FROM users u
                JOIN user_organizations uo ON uo.user_id = u.id
                WHERE uo.organization_id = :oid AND (u.profile->>'mfa_enabled')::boolean IS TRUE
            """),
            ("active_api_keys", "SELECT COUNT(*) FROM api_keys WHERE is_active = TRUE"),
            ("total_users", """
                SELECT COUNT(*) FROM user_organizations WHERE organization_id = :oid
            """),
        ]

        for name, query in checks:
            try:
                result = await db.execute(text(query).params(oid=org_id))
                count = result.scalar() or 0
                report["checks"].append({"name": name, "count": count, "status": "pass" if count > 0 else "fail"})
            except Exception as e:
                report["checks"].append({"name": name, "error": str(e), "status": "error"})

        return report


compliance_service = ComplianceService()
