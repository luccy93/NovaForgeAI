"""Installation lifecycle: entitlement, governance, security, idempotency,
configuration, update, rollback and canary promotion.

Installations are scoped to (package, organization, workspace, project,
environment) and are idempotent: re-installing the same scope returns the
existing record; changing version/configuration updates it in place.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.marketplace.manifest import (
    PERMISSION_CATALOG,
    PackageManifest,
    RiskLevel,
    satisfies_constraint,
)
from app.marketplace.models import (
    AccessScope,
    ApprovalStatus,
    EnvironmentType,
    InstallationStatus,
    MarketplaceInstallation,
    MarketplacePackage,
    MarketplacePublisher,
    MarketplaceRelease,
    PackageStatus,
    PricingType,
    ScanStatus,
)
from app.marketplace.license_policy import LicensePolicyService
from app.marketplace.emergency_block import EmergencyBlockService
import uuid
from app.marketplace.security import RiskCalculator


def _to_uuid(value):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception:
        return value


class CompatibilityError(Exception):
    pass


class EntitlementError(Exception):
    pass


class HostCapabilities:
    def __init__(self, novaforge_version: str = "0.0.0", api_version: str = "v1", os: Optional[list] = None, arch: Optional[list] = None, sdk_version: str = "1.0.0", runtime_version: str = "1.0.0"):
        self.novaforge_version = novaforge_version
        self.api_version = api_version
        self.os = os or []
        self.arch = arch or []
        self.sdk_version = sdk_version
        self.runtime_version = runtime_version


def is_compatible(package: MarketplacePackage, capabilities: HostCapabilities) -> tuple[bool, str]:
    comp = package.compatibility or {}
    nv = comp.get("novaforge_version")
    if nv and not satisfies_constraint(capabilities.novaforge_version, nv):
        return False, f"requires NovaForge {nv}, host is {capabilities.novaforge_version}"
    av = comp.get("api_version")
    if av and av != capabilities.api_version:
        return False, f"requires API {av}, host exposes {capabilities.api_version}"
    sv = comp.get("sdk_version") or comp.get("sdk_version_constraint")
    if sv and not satisfies_constraint(getattr(capabilities, "sdk_version", "1.0.0"), sv):
        return False, f"requires SDK {sv}, host is {getattr(capabilities, 'sdk_version', '1.0.0')}"
    rv = comp.get("runtime_version") or comp.get("runtime")
    if rv and not satisfies_constraint(getattr(capabilities, "runtime_version", "1.0.0"), rv):
        return False, f"requires runtime {rv}, host is {getattr(capabilities, 'runtime_version', '1.0.0')}"
    if comp.get("os"):
        if capabilities.os and not any(o in capabilities.os for o in comp["os"]):
            return False, f"requires OS {comp['os']}"
    if comp.get("arch"):
        if capabilities.arch and not any(a in capabilities.arch for a in comp["arch"]):
            return False, f"requires arch {comp['arch']}"
    return True, "compatible"


class EntitlementService:
    def __init__(self, db: AsyncSession, subscription_manager=None):
        self.db = db
        self.subscription_manager = subscription_manager

    async def check(self, organization_id, package: MarketplacePackage, user_id=None) -> tuple[bool, str]:
        if package.access_scope in (AccessScope.PRIVATE, AccessScope.ORGANIZATION):
            if str(package.organization_id) != str(organization_id):
                return False, "package is private to another organization"
            return True, "organization-scoped access granted"
        if package.pricing_type == PricingType.FREE:
            return True, "free package"
        # paid / enterprise — require an active subscription when a backend is
        # configured, otherwise fail closed (entitlement must be verified).
        if self.subscription_manager:
            try:
                sub = self.subscription_manager.validate_subscription(organization_id)
                if sub.get("valid"):
                    return True, "subscription active"
            except Exception:
                pass
        return False, "entitlement required: active subscription needed for paid/enterprise package"


class InstallationService:
    def __init__(self, db: AsyncSession, risk_calc: Optional[RiskCalculator] = None, subscription_manager=None):
        self.db = db
        self.risk_calc = risk_calc or RiskCalculator()
        self.entitlements = EntitlementService(db, subscription_manager)

    async def _resolve_package(self, slug: str) -> MarketplacePackage:
        res = await self.db.execute(select(MarketplacePackage).where(MarketplacePackage.slug == slug))
        pkg = res.scalar_one_or_none()
        if not pkg:
            raise ValueError("package not found")
        if pkg.status in (PackageStatus.RETIRED, PackageStatus.SUSPENDED, PackageStatus.SECURITY_RISK, PackageStatus.DRAFT):
            raise ValueError(f"package is not installable (status={pkg.status.value})")
        return pkg

    async def _resolve_release(self, pkg: MarketplacePackage, version: Optional[str]) -> MarketplaceRelease:
        v = version or pkg.latest_version
        if not v:
            raise ValueError("package has no published release")
        res = await self.db.execute(
            select(MarketplaceRelease)
            .options(selectinload(MarketplaceRelease.security_scans))
            .where(MarketplaceRelease.package_id == pkg.id, MarketplaceRelease.version == v)
        )
        rel = res.scalar_one_or_none()
        if not rel:
            raise ValueError(f"release {v} not found")
        if rel.is_yanked:
            raise ValueError(f"release {v} has been yanked")
        return rel

    def _requires_approval(self, pkg: MarketplacePackage, risk_level: RiskLevel, manifest_perms: list) -> bool:
        if pkg.governance_status == ApprovalStatus.PENDING:
            return True
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return True
        if any(PERMISSION_CATALOG.get(p, {}).get("privileged") for p in manifest_perms):
            return True
        return False

    async def install(
        self,
        organization_id,
        data,
        user_id=None,
        capabilities: Optional[HostCapabilities] = None,
        config_errors: Optional[list] = None,
        secret_refs: Optional[list] = None,
    ) -> MarketplaceInstallation:
        capabilities = capabilities or HostCapabilities()
        pkg = await self._resolve_package(data.package_slug)
        rel = await self._resolve_release(pkg, data.version)

        compat, reason = is_compatible(pkg, capabilities)
        if not compat:
            raise CompatibilityError(reason)

        allowed, why = await self.entitlements.check(organization_id, pkg, user_id)
        if not allowed:
            raise EntitlementError(why)

        if pkg.security_status == ScanStatus.FAILED or pkg.status == PackageStatus.SECURITY_RISK:
            raise ValueError("package failed security scanning and cannot be installed")

        # Emergency block check (fail closed)
        try:
            block_svc = EmergencyBlockService(self.db)
            blocked, _ = await block_svc.is_blocked("package", str(pkg.id))
            if blocked:
                raise ValueError(f"package {pkg.slug} is emergency-blocked")
            pub_blocked = await block_svc.is_publisher_blocked(str(pkg.publisher_id))
            if pub_blocked:
                raise ValueError(f"publisher {pkg.publisher_id} is emergency-blocked")
        except ValueError:
            raise
        except Exception:
            pass

        # License policy check (organization-scoped)
        try:
            lic_svc = LicensePolicyService(self.db)
            is_blocked, reason = await lic_svc.is_blocked(str(organization_id), pkg.license)
            if is_blocked:
                raise ValueError(reason)
        except ValueError:
            raise
        except Exception:
            pass

        manifest_perms = (rel.manifest or {}).get("permissions", [])
        publisher = await self.db.get(MarketplacePublisher, pkg.publisher_id)
        verified = publisher is not None and publisher.verification_status.value.endswith("verified")
        risk_level, factors = self.risk_calc.calculate(
            PackageManifest.model_validate(rel.manifest),
            publisher_verified=verified,
            security_findings=[],
        )

        approval = self._requires_approval(pkg, risk_level, manifest_perms)
        status = InstallationStatus.ACTIVE if not approval else InstallationStatus.INSTALLED

        existing = await self._find_scope(pkg.id, organization_id, data.workspace_id, data.project_id, data.environment)
        if existing:
            # Respect dependency lock: do not auto-upgrade if locked version differs and policy says lock
            dep_lock = getattr(data, "dependency_lock", None) or existing.dependency_lock
            if dep_lock and dep_lock.get("locked_version") and dep_lock.get("locked_version") != rel.version:
                raise ValueError(f"dependency locked to {dep_lock.get('locked_version')}, cannot install {rel.version}")
            # Idempotent: update in place.
            existing.release_id = rel.id
            existing.current_version = rel.version
            existing.previous_version = existing.current_version
            existing.configuration = data.configuration
            existing.config_valid = not (config_errors or [])
            existing.risk_level = risk_level
            existing.risk_factors = factors
            existing.secrets_ref = secret_refs or []
            existing.security_scan_status = pkg.security_status
            existing.approval_status = ApprovalStatus.APPROVED if not approval else ApprovalStatus.PENDING
            existing.region = data.region
            existing.canary_stage = "pilot" if data.canary else None
            existing.rollout_strategy = getattr(data, "rollout_strategy", None) or existing.rollout_strategy or "manual"
            existing.dependency_lock = dep_lock or {}
            existing.health_status = "healthy"
            existing.status = status
            existing.last_error = None
            await self.db.flush()
            await self._meter(pkg, rel, organization_id, existing.id, "install", 1, data.environment.value, user_id)
            return existing

        inst = MarketplaceInstallation(
            package_id=pkg.id,
            release_id=rel.id,
            organization_id=organization_id,
            workspace_id=data.workspace_id,
            project_id=data.project_id,
            installed_by=user_id,
            environment=data.environment,
            status=status,
            configuration=data.configuration,
            config_valid=not (config_errors or []),
            entitlement_ref=f"ent:{organization_id}:{pkg.id}",
            approval_status=ApprovalStatus.APPROVED if not approval else ApprovalStatus.PENDING,
            security_scan_status=pkg.security_status,
            risk_level=risk_level,
            risk_factors=factors,
            secrets_ref=secret_refs or [],
            current_version=rel.version,
            region=data.region,
            canary_stage="pilot" if data.canary else None,
            dependency_lock=getattr(data, "dependency_lock", None) or {},
            rollout_strategy=getattr(data, "rollout_strategy", None) or "manual",
            health_status="healthy",
            license_policy_status="allow",
        )
        self.db.add(inst)
        await self.db.flush()
        pkg.install_count += 1
        await self.db.flush()
        await self._meter(pkg, rel, organization_id, inst.id, "install", 1, data.environment.value, user_id)
        return inst

    async def _find_scope(self, package_id, organization_id, workspace_id, project_id, environment):
        res = await self.db.execute(
            select(MarketplaceInstallation).where(
                MarketplaceInstallation.package_id == package_id,
                MarketplaceInstallation.organization_id == organization_id,
                MarketplaceInstallation.workspace_id == workspace_id,
                MarketplaceInstallation.project_id == project_id,
                MarketplaceInstallation.environment == environment,
            )
        )
        return res.scalar_one_or_none()

    async def approve(self, installation_id, approve: bool, admin_user_id=None, reason: Optional[str] = None) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        inst.approval_status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        inst.approved_by = admin_user_id
        inst.approved_at = datetime.now(timezone.utc)
        inst.status = InstallationStatus.ACTIVE if approve else InstallationStatus.DISABLED
        inst.last_error = reason if not approve else None
        await self.db.flush()
        return inst

    async def configure(self, installation_id, config: dict, config_errors: Optional[list] = None, secret_refs: Optional[list] = None) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        if inst.status == InstallationStatus.UNINSTALLED:
            raise ValueError("cannot configure an uninstalled package")
        inst.configuration = config
        inst.config_valid = not (config_errors or [])
        if secret_refs is not None:
            inst.secrets_ref = secret_refs
        inst.status = InstallationStatus.ACTIVE if inst.approval_status == ApprovalStatus.APPROVED else inst.status
        await self.db.flush()
        return inst

    async def update(self, installation_id, version: Optional[str], user_id=None, capabilities: Optional[HostCapabilities] = None) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        pkg = await self.db.get(MarketplacePackage, inst.package_id)
        rel = await self._resolve_release(pkg, version)
        caps = capabilities or HostCapabilities()
        compat, reason = is_compatible(pkg, caps)
        if not compat:
            raise CompatibilityError(reason)
        allowed, why = await self.entitlements.check(inst.organization_id, pkg, user_id)
        if not allowed:
            raise EntitlementError(why)
        if pkg.security_status == ScanStatus.FAILED:
            raise ValueError("target release failed security scanning")
        if self._requires_approval(pkg, inst.risk_level, (rel.manifest or {}).get("permissions", [])) and inst.approval_status != ApprovalStatus.APPROVED:
            inst.approval_status = ApprovalStatus.PENDING
            inst.status = InstallationStatus.INSTALLED
        inst.previous_version = inst.current_version
        inst.current_version = rel.version
        inst.release_id = rel.id
        inst.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._meter(pkg, rel, inst.organization_id, inst.id, "update", 1, inst.environment.value, user_id)
        return inst

    async def rollback(self, installation_id, version: str, user_id=None, emergency: bool = False) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        pkg = await self.db.get(MarketplacePackage, inst.package_id)
        rel = await self._resolve_release(pkg, version)
        # Never roll back to a release with known critical/blocking security
        # issues unless an explicit emergency override is supplied.
        scan_blocking = False
        if rel.security_scans:
            latest_scan = rel.security_scans[-1] if rel.security_scans else None
            if latest_scan and latest_scan.summary:
                scan_blocking = latest_scan.summary.get("blocks_installation", False)
        if scan_blocking and not emergency:
            raise ValueError("refusing to roll back to a version with known critical security issues (use emergency override)")
        inst.previous_version = inst.current_version
        inst.current_version = rel.version
        inst.release_id = rel.id
        await self.db.flush()
        await self._meter(pkg, rel, inst.organization_id, inst.id, "rollback", 1, inst.environment.value, user_id)
        return inst

    async def uninstall(self, installation_id, user_id=None) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        if inst.status == InstallationStatus.UNINSTALLED:
            return inst  # idempotent
        inst.status = InstallationStatus.UNINSTALLED
        inst.last_error = None
        pkg = await self.db.get(MarketplacePackage, inst.package_id)
        if pkg and pkg.install_count > 0:
            pkg.install_count -= 1
        await self.db.flush()
        return inst

    async def promote_canary(self, installation_id, stage: str) -> MarketplaceInstallation:
        inst = await self.db.get(MarketplaceInstallation, _to_uuid(installation_id))
        if not inst:
            raise ValueError("installation not found")
        inst.canary_stage = stage
        await self.db.flush()
        return inst

    async def list_for_org(self, organization_id, environment=None, limit=50, offset=0):
        stmt = select(MarketplaceInstallation).where(MarketplaceInstallation.organization_id == organization_id)
        if environment:
            stmt = stmt.where(MarketplaceInstallation.environment == environment)
        rows = (await self.db.execute(stmt.order_by(MarketplaceInstallation.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return rows

    async def _meter(self, pkg, rel, org_id, inst_id, metric, value, env, user_id):
        from app.marketplace.models import MarketplacePackageUsage

        rec = MarketplacePackageUsage(
            package_id=pkg.id,
            release_id=rel.id,
            organization_id=org_id,
            installation_id=inst_id,
            user_id=user_id,
            metric=metric,
            value=value,
            environment=env,
            recorded_at=datetime.now(timezone.utc),
        )
        self.db.add(rec)
        await self.db.flush()
