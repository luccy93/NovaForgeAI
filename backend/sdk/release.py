"""NovaForge SDK — Release Management & Progressive Delivery (Volume 56).

Provides :class:`ReleaseMixin` (sync) and :class:`AsyncReleaseMixin` (async)
that add methods for release lifecycle, gates, progressive rollout,
verification and centralized feature flags. They compose with
``NovaForgeClient`` / ``AsyncNovaForgeClient`` and use real
``_build_url("/releases...")`` calls.

Usage:
    from backend.sdk import NovaForgeClient
    from backend.sdk.release import ReleaseMixin

    class MyClient(ReleaseMixin, NovaForgeClient):
        pass

Expects the host class to provide ``self.get()``, ``self.post()``,
``self.put()`` and ``self._build_url()`` — all of which NovaForgeClient
already has (via BaseClient).
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Sync mixin
# ---------------------------------------------------------------------------


class ReleaseMixin:
    """Sync SDK methods for Release Management & Progressive Delivery.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()`` and ``self._build_url()``.
    """

    # ─── Release lifecycle ─────────────────────────────────────────────

    def release_create(self, data: dict[str, Any]) -> dict:
        """Create a new release. ``data`` should contain project, service, version, artifact_id etc."""
        return self.post(self._build_url("/releases"), data=data)

    def create_release(self, data: dict[str, Any]) -> dict:
        """Alias for release_create."""
        return self.release_create(data)

    def release_validate(self, release_id: str) -> dict:
        """Validate a release (artifact immutability, SBOM, security, gates)."""
        return self.post(self._build_url(f"/releases/{release_id}/validate"))

    def release_approve(self, release_id: str, approver_role: str = "reviewer", **kwargs) -> dict:
        """Approve a release. kwargs may include decision, reason, signature, version."""
        payload: dict[str, Any] = {"approver_role": approver_role}
        payload.update(kwargs)
        return self.post(self._build_url(f"/releases/{release_id}/approvals"), data=payload)

    def release_deploy(self, release_id: str) -> dict:
        """Trigger deployment orchestration for a release."""
        return self.post(self._build_url(f"/releases/{release_id}/deploy"))

    def release_status(self, release_id: str) -> dict:
        """Get release status with steps, gate results, verifications and lock info."""
        return self.get(self._build_url(f"/releases/{release_id}/status"))

    def release_promote(self, release_id: str, target_env: str) -> dict:
        """Promote release to target environment."""
        return self.post(self._build_url(f"/releases/{release_id}/promote"), data={"target_env": target_env})

    def release_pause(self, release_id: str, reason: Optional[str] = None) -> dict:
        """Pause an in-progress release/rollout."""
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        return self.post(self._build_url(f"/releases/{release_id}/pause"), data=payload)

    def release_rollback(self, release_id: str, reason: Optional[str] = None, target_version: Optional[str] = None) -> dict:
        """Rollback a release. Auditable via DeliveryRollback."""
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if target_version is not None:
            payload["target_version"] = target_version
        return self.post(self._build_url(f"/releases/{release_id}/rollback"), data=payload)

    def release_verify(self, release_id: str, verification_type: str = "smoke") -> dict:
        """Create and run a verification (smoke|health|targeted|synthetic)."""
        return self.post(self._build_url(f"/releases/{release_id}/verify"), data={"verification_type": verification_type})

    def release_history(self, release_id: str) -> dict:
        """Get release history and change graph."""
        return self.get(self._build_url(f"/releases/{release_id}/history"))

    # ─── Release convenience aliases matching spec summary ──────────────

    def validate(self, release_id: str) -> dict:
        return self.release_validate(release_id)

    def approve(self, release_id: str, approver_role: str = "reviewer", **kwargs) -> dict:
        return self.release_approve(release_id, approver_role, **kwargs)

    def deploy(self, release_id: str) -> dict:
        return self.release_deploy(release_id)

    def promote(self, release_id: str, target_env: str) -> dict:
        return self.release_promote(release_id, target_env)

    def pause(self, release_id: str, reason: Optional[str] = None) -> dict:
        return self.release_pause(release_id, reason)

    def rollback(self, release_id: str, reason: Optional[str] = None, target_version: Optional[str] = None) -> dict:
        return self.release_rollback(release_id, reason, target_version)

    def verify(self, release_id: str, verification_type: str = "smoke") -> dict:
        return self.release_verify(release_id, verification_type)

    # ─── Feature flags ──────────────────────────────────────────────────

    def flag_create(self, data: dict[str, Any]) -> dict:
        """Create a centralized feature flag."""
        return self.post(self._build_url("/feature-flags"), data=data)

    def flag_get(self, key: str) -> dict:
        """Get a feature flag by key."""
        return self.get(self._build_url(f"/feature-flags/{key}"))

    def flag_evaluate(self, key: str, context: Optional[dict[str, Any]] = None) -> dict:
        """Evaluate a flag for given context (deterministic via consistent hashing)."""
        return self.post(self._build_url(f"/feature-flags/{key}/evaluate"), data={"context": context or {}})

    def flag_rollout(self, key: str, percentage: int) -> dict:
        """Set percentage rollout for a flag (0-100) via consistent hashing."""
        return self.post(self._build_url(f"/feature-flags/{key}/rules"), data={"rule_type": "percentage", "value": key, "percentage": int(percentage), "rank": 0})

    def flag_archive(self, key: str) -> dict:
        """Archive a flag (explicit state change, not silent delete)."""
        return self.post(self._build_url(f"/feature-flags/{key}/archive"))

    # alias for explicit set/rollout archive/evaluate naming
    def flag_set(self, key: str, data: dict[str, Any]) -> dict:
        return self.put(self._build_url(f"/feature-flags/{key}"), data=data)


# ---------------------------------------------------------------------------
# Async mixin
# ---------------------------------------------------------------------------


class AsyncReleaseMixin:
    """Async SDK methods for Release Management & Progressive Delivery.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()`` and ``self._build_url()``.
    """

    # ─── Release lifecycle ─────────────────────────────────────────────

    async def release_create(self, data: dict[str, Any]) -> dict:
        return await self.post(self._build_url("/releases"), data=data)

    async def create_release(self, data: dict[str, Any]) -> dict:
        return await self.release_create(data)

    async def release_validate(self, release_id: str) -> dict:
        return await self.post(self._build_url(f"/releases/{release_id}/validate"))

    async def release_approve(self, release_id: str, approver_role: str = "reviewer", **kwargs) -> dict:
        payload: dict[str, Any] = {"approver_role": approver_role}
        payload.update(kwargs)
        return await self.post(self._build_url(f"/releases/{release_id}/approvals"), data=payload)

    async def release_deploy(self, release_id: str) -> dict:
        return await self.post(self._build_url(f"/releases/{release_id}/deploy"))

    async def release_status(self, release_id: str) -> dict:
        return await self.get(self._build_url(f"/releases/{release_id}/status"))

    async def release_promote(self, release_id: str, target_env: str) -> dict:
        return await self.post(self._build_url(f"/releases/{release_id}/promote"), data={"target_env": target_env})

    async def release_pause(self, release_id: str, reason: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        return await self.post(self._build_url(f"/releases/{release_id}/pause"), data=payload)

    async def release_rollback(self, release_id: str, reason: Optional[str] = None, target_version: Optional[str] = None) -> dict:
        payload: dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        if target_version is not None:
            payload["target_version"] = target_version
        return await self.post(self._build_url(f"/releases/{release_id}/rollback"), data=payload)

    async def release_verify(self, release_id: str, verification_type: str = "smoke") -> dict:
        return await self.post(self._build_url(f"/releases/{release_id}/verify"), data={"verification_type": verification_type})

    async def release_history(self, release_id: str) -> dict:
        return await self.get(self._build_url(f"/releases/{release_id}/history"))

    async def validate(self, release_id: str) -> dict:
        return await self.release_validate(release_id)

    async def approve(self, release_id: str, approver_role: str = "reviewer", **kwargs) -> dict:
        return await self.release_approve(release_id, approver_role, **kwargs)

    async def deploy(self, release_id: str) -> dict:
        return await self.release_deploy(release_id)

    async def promote(self, release_id: str, target_env: str) -> dict:
        return await self.release_promote(release_id, target_env)

    async def pause(self, release_id: str, reason: Optional[str] = None) -> dict:
        return await self.release_pause(release_id, reason)

    async def rollback(self, release_id: str, reason: Optional[str] = None, target_version: Optional[str] = None) -> dict:
        return await self.release_rollback(release_id, reason, target_version)

    async def verify(self, release_id: str, verification_type: str = "smoke") -> dict:
        return await self.release_verify(release_id, verification_type)

    # ─── Feature flags ──────────────────────────────────────────────────

    async def flag_create(self, data: dict[str, Any]) -> dict:
        return await self.post(self._build_url("/feature-flags"), data=data)

    async def flag_get(self, key: str) -> dict:
        return await self.get(self._build_url(f"/feature-flags/{key}"))

    async def flag_evaluate(self, key: str, context: Optional[dict[str, Any]] = None) -> dict:
        return await self.post(self._build_url(f"/feature-flags/{key}/evaluate"), data={"context": context or {}})

    async def flag_rollout(self, key: str, percentage: int) -> dict:
        return await self.post(self._build_url(f"/feature-flags/{key}/rules"), data={"rule_type": "percentage", "value": key, "percentage": int(percentage), "rank": 0})

    async def flag_archive(self, key: str) -> dict:
        return await self.post(self._build_url(f"/feature-flags/{key}/archive"))

    async def flag_set(self, key: str, data: dict[str, Any]) -> dict:
        return await self.put(self._build_url(f"/feature-flags/{key}"), data=data)
