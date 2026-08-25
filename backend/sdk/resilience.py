"""Resilience SDK mixin — Volume 60."""

from typing import Any, Optional


class ResilienceMixin:
    def resilience_create_profile(self, data: dict) -> dict:
        return self.post(self._build_url("/resilience/profiles"), data=data)

    def resilience_list_profiles(self) -> dict:
        return self.get(self._build_url("/resilience/profiles"))

    def resilience_create_backup_policy(self, data: dict) -> dict:
        return self.post(self._build_url("/resilience/backup-policies"), data=data)

    def resilience_backup(self, scope_type: str, scope_target: Optional[str] = None, backup_type: str = "full", **kwargs: Any) -> dict:
        payload = {"scope_type": scope_type, "scope_target": scope_target, "backup_type": backup_type, **kwargs}
        return self.post(self._build_url("/resilience/backups"), data=payload)

    def resilience_backups(self, scope_type: Optional[str] = None) -> dict:
        params = {"scope_type": scope_type} if scope_type else {}
        return self.get(self._build_url("/resilience/backups"), params=params)

    def resilience_get_backup(self, backup_id: str) -> dict:
        return self.get(self._build_url(f"/resilience/backups/{backup_id}"))

    def resilience_verify(self, backup_id: str, verification_type: str = "checksum", expected_checksum: Optional[str] = None) -> dict:
        return self.post(self._build_url(f"/resilience/backups/{backup_id}/verify"),
                         data={"verification_type": verification_type, "expected_checksum": expected_checksum})

    def resilience_restore(self, backup_id: str, mode: str = "full", isolated_test: bool = False,
                           target_environment: str = "production", **kwargs: Any) -> dict:
        payload = {"backup_id": backup_id, "mode": mode, "isolated_test": isolated_test,
                   "target_environment": target_environment, **kwargs}
        return self.post(self._build_url("/resilience/restore"), data=payload)

    def resilience_restore_run(self, job_id: str) -> dict:
        return self.post(self._build_url(f"/resilience/restore/{job_id}/run"), data={})

    def resilience_restore_verify(self, job_id: str, checks: dict) -> dict:
        return self.post(self._build_url(f"/resilience/restore/{job_id}/verify"), data={"checks": checks})

    def resilience_create_plan(self, name: str, service: str, steps: list, environment: str = "production") -> dict:
        return self.post(self._build_url("/resilience/recovery-plans"),
                         data={"name": name, "service": service, "steps": steps, "environment": environment})

    def resilience_plan_execute(self, plan_id: str) -> dict:
        return self.post(self._build_url(f"/resilience/recovery-plans/{plan_id}/execute"), data={})

    def resilience_declare_disaster(self, disaster_type: str, reason: str, severity: str = "HIGH") -> dict:
        return self.post(self._build_url("/resilience/disasters"),
                         data={"disaster_type": disaster_type, "reason": reason, "severity": severity})

    def resilience_failover(self, failover_type: str, source_target: Optional[str] = None,
                            destination_target: Optional[str] = None, restricted_data_regions: Optional[list] = None) -> dict:
        return self.post(self._build_url("/resilience/failovers"), data={
            "failover_type": failover_type, "source_target": source_target,
            "destination_target": destination_target, "restricted_data_regions": restricted_data_regions,
        })

    def resilience_failover_promote(self, record_id: str, health_verified: bool) -> dict:
        return self.post(self._build_url(f"/resilience/failovers/{record_id}/promote"), data={"health_verified": health_verified})

    def resilience_status(self) -> dict:
        return self.get(self._build_url("/resilience/dashboard"))

    def resilience_rto_rpo(self, service: str, environment: str = "production") -> dict:
        return self.get(self._build_url(f"/resilience/rto-rpo/{service}"), params={"environment": environment})

    # ── Volume 60 Commit 2 ───────────────────────────────────────────────

    def resilience_readiness(self) -> dict:
        return self.get(self._build_url("/resilience/readiness"))

    def resilience_score(self) -> dict:
        return self.get(self._build_url("/resilience/resilience-score"))

    def resilience_recommendations(self) -> dict:
        return self.get(self._build_url("/resilience/recovery-recommendations"))

    def resilience_reconcile(self, job_id: str, pre: dict, restored: dict, expected: dict) -> dict:
        payload = {
            "pre": pre, "pre_state": pre,
            "restored": restored, "restored_state": restored,
            "expected": expected, "expected_state": expected,
        }
        return self.post(self._build_url(f"/resilience/reconcile/{job_id}"), data=payload)

    def resilience_chaos_create(self, data: dict) -> dict:
        return self.post(self._build_url("/resilience/chaos-tests"), data=data)

    def resilience_chaos_run(self, test_id: str) -> dict:
        return self.post(self._build_url(f"/resilience/chaos-tests/{test_id}/run"), data={})

    def resilience_chaos_complete(self, test_id: str, success: bool) -> dict:
        return self.post(self._build_url(f"/resilience/chaos-tests/{test_id}/complete"), data={"success": success, "passed": success})

    def resilience_drill_schedule(self, data: dict) -> dict:
        return self.post(self._build_url("/resilience/recovery-drills"), data=data)

    def resilience_drill_run(self, drill_id: str) -> dict:
        return self.post(self._build_url(f"/resilience/recovery-drills/{drill_id}/run"), data={})

    def resilience_game_day(self, drill_id: str, data: dict) -> dict:
        return self.post(self._build_url(f"/resilience/recovery-drills/{drill_id}/game-day"), data=data)

    def resilience_backup_protection(self, scope: str, reason: str) -> dict:
        return self.post(self._build_url("/resilience/backup-protection"), data={"scope": scope, "reason": reason})

    def resilience_drift(self) -> dict:
        return self.get(self._build_url("/resilience/drift"))

    def resilience_chaos_inject(self, target: str, failure_type: str) -> dict:
        return self.post(self._build_url("/resilience/chaos/failure-injection"), data={"test_id": target, "target": failure_type, "failure_type": failure_type})


class AsyncResilienceMixin:
    async def resilience_create_profile(self, data: dict) -> dict:
        return await self.post(self._build_url("/resilience/profiles"), data=data)

    async def resilience_backup(self, scope_type: str, scope_target: Optional[str] = None, backup_type: str = "full", **kwargs: Any) -> dict:
        payload = {"scope_type": scope_type, "scope_target": scope_target, "backup_type": backup_type, **kwargs}
        return await self.post(self._build_url("/resilience/backups"), data=payload)

    async def resilience_verify(self, backup_id: str, verification_type: str = "checksum", expected_checksum: Optional[str] = None) -> dict:
        return await self.post(self._build_url(f"/resilience/backups/{backup_id}/verify"),
                               data={"verification_type": verification_type, "expected_checksum": expected_checksum})

    async def resilience_restore(self, backup_id: str, mode: str = "full", isolated_test: bool = False, **kwargs: Any) -> dict:
        payload = {"backup_id": backup_id, "mode": mode, "isolated_test": isolated_test, **kwargs}
        return await self.post(self._build_url("/resilience/restore"), data=payload)

    async def resilience_declare_disaster(self, disaster_type: str, reason: str, severity: str = "HIGH") -> dict:
        return await self.post(self._build_url("/resilience/disasters"),
                               data={"disaster_type": disaster_type, "reason": reason, "severity": severity})

    async def resilience_failover(self, failover_type: str, source_target: Optional[str] = None,
                                  destination_target: Optional[str] = None, restricted_data_regions: Optional[list] = None) -> dict:
        return await self.post(self._build_url("/resilience/failovers"), data={
            "failover_type": failover_type, "source_target": source_target,
            "destination_target": destination_target, "restricted_data_regions": restricted_data_regions,
        })

    async def resilience_status(self) -> dict:
        return await self.get(self._build_url("/resilience/dashboard"))

    # ── Volume 60 Commit 2 ───────────────────────────────────────────────

    async def resilience_readiness(self) -> dict:
        return await self.get(self._build_url("/resilience/readiness"))

    async def resilience_score(self) -> dict:
        return await self.get(self._build_url("/resilience/resilience-score"))

    async def resilience_recommendations(self) -> dict:
        return await self.get(self._build_url("/resilience/recovery-recommendations"))

    async def resilience_reconcile(self, job_id: str, pre: dict, restored: dict, expected: dict) -> dict:
        payload = {
            "pre": pre, "pre_state": pre,
            "restored": restored, "restored_state": restored,
            "expected": expected, "expected_state": expected,
        }
        return await self.post(self._build_url(f"/resilience/reconcile/{job_id}"), data=payload)

    async def resilience_chaos_create(self, data: dict) -> dict:
        return await self.post(self._build_url("/resilience/chaos-tests"), data=data)

    async def resilience_chaos_run(self, test_id: str) -> dict:
        return await self.post(self._build_url(f"/resilience/chaos-tests/{test_id}/run"), data={})

    async def resilience_chaos_complete(self, test_id: str, success: bool) -> dict:
        return await self.post(self._build_url(f"/resilience/chaos-tests/{test_id}/complete"), data={"success": success, "passed": success})

    async def resilience_drill_schedule(self, data: dict) -> dict:
        return await self.post(self._build_url("/resilience/recovery-drills"), data=data)

    async def resilience_drill_run(self, drill_id: str) -> dict:
        return await self.post(self._build_url(f"/resilience/recovery-drills/{drill_id}/run"), data={})

    async def resilience_game_day(self, drill_id: str, data: dict) -> dict:
        return await self.post(self._build_url(f"/resilience/recovery-drills/{drill_id}/game-day"), data=data)

    async def resilience_backup_protection(self, scope: str, reason: str) -> dict:
        return await self.post(self._build_url("/resilience/backup-protection"), data={"scope": scope, "reason": reason})

    async def resilience_drift(self) -> dict:
        return await self.get(self._build_url("/resilience/drift"))

    async def resilience_chaos_inject(self, target: str, failure_type: str) -> dict:
        return await self.post(self._build_url("/resilience/chaos/failure-injection"), data={"test_id": target, "target": failure_type, "failure_type": failure_type})
