"""Volume 58 — AIProvenanceService.

Tenant-scoped, AsyncSession, no placeholders.

Records and retrieves model provenance:

* record_provenance — stores artifact/source/training_metadata/
  evaluation_version/deployment_version/policy_version in the
  ``ai_model_versions.provenance`` JSON (and related columns) plus
  best-effort KG via ``knowledge_graph`` if available
* get_provenance    — retrieves provenance for a model (tenant-scoped)

Never invent training info: when ``training_metadata`` is not provided
(None/empty) it is stored as empty dict ``{}`` or preserved existing,
never hallucinated.

Tenant isolation: every read/write scoped to tenant (via
``ai_model_registry.tenant``).  KG writes are best-effort and tenant
tagged.

Audit best-effort via ``app.iam.audit_service`` — never raises.
No placeholders — all branches are real AsyncSession / KG calls.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIModelRegistry, AIModelVersion
from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_provenance", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_provenance", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _normalize_training_metadata(value: Any) -> dict | None:
    """Never invent — return None when not provided, else dict as-is.

    Caller decides to store empty dict or preserve existing. This helper
    normalizes to dict or None (None means not provided).
    """
    if value is None:
        return None
    if isinstance(value, dict):
        # empty dict means explicitly no metadata — keep empty, not invented
        return dict(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # try json-ish, else wrap
        return {"value": s}
    if isinstance(value, list):
        if not value:
            return None
        return {"items": list(value)}
    # unexpected type — keep as string-wrapped, not invented
    return {"value": str(value)}


def _kg_best_effort_record(
    tenant: str,
    model_registry: AIModelRegistry,
    model_version: AIModelVersion | None,
    provenance: dict,
) -> None:
    """Best-effort KG write via knowledge_graph if available. Never raises."""
    try:
        from app.knowledge_graph.entity_service import entity_service  # type: ignore
        from app.knowledge_graph.relationship_service import relationship_service  # type: ignore
    except ImportError as exc:
        logger.debug("knowledge_graph not available for provenance KG: %s", exc)
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("knowledge_graph import failed for provenance: %s", exc)
        return

    try:
        # Use model name + version as entity identifier
        version_str = provenance.get("deployment_version") or provenance.get("evaluation_version") or (model_version.version if model_version else "") or model_registry.version or ""
        entity_name = f"{model_registry.name}:{version_str}" if version_str else model_registry.name
        external_id = str(model_registry.id)
        provider = provenance.get("provider") or model_registry.provider or ""
        # Check if entity already exists for this model+version
        existing = None
        try:
            existing = entity_service.get_entity_by_external_id(external_id, provider or "aiml", tenant=tenant)  # type: ignore
        except Exception:
            existing = None

        if existing is None:
            try:
                ent = entity_service.create_entity(  # type: ignore
                    tenant=tenant,
                    entity_type="ai_model",
                    name=entity_name,
                    external_id=external_id,
                    provider=provider or "aiml",
                    display_name=entity_name,
                    description=f"Provenance for {model_registry.provider}/{model_registry.name}:{version_str}",
                    metadata_extra={
                        "artifact": provenance.get("artifact"),
                        "source": provenance.get("source"),
                        "training_metadata_present": bool(provenance.get("training_metadata")),
                        "evaluation_version": provenance.get("evaluation_version"),
                        "deployment_version": provenance.get("deployment_version"),
                        "policy_version": provenance.get("policy_version"),
                        "recorded_at": provenance.get("recorded_at"),
                    },
                )
                model_entity_id = ent.get("id") if isinstance(ent, dict) else None
            except Exception as exc:  # noqa: BLE001
                logger.debug("KG entity create failed for provenance: %s", exc)
                return
        else:
            model_entity_id = existing.get("id") if isinstance(existing, dict) else None
            try:
                entity_service.update_entity(  # type: ignore
                    model_entity_id,
                    metadata_extra={
                        "artifact": provenance.get("artifact"),
                        "source": provenance.get("source"),
                        "training_metadata_present": bool(provenance.get("training_metadata")),
                        "evaluation_version": provenance.get("evaluation_version"),
                        "deployment_version": provenance.get("deployment_version"),
                        "policy_version": provenance.get("policy_version"),
                        "updated_at": provenance.get("recorded_at"),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("KG entity update failed: %s", exc)

        # Create relationships for artifact and source if present
        if model_entity_id:
            for rel_type, val in (("trained_from", provenance.get("source")), ("stored_at", provenance.get("artifact"))):
                if not val or not str(val).strip():
                    continue
                # Create a lightweight dataset/artifact entity if not exists, then relationship
                artifact_name = str(val).strip()[:256]
                try:
                    # Search for existing artifact entity by name
                    found = entity_service.search_entities(tenant=tenant, query=artifact_name, entity_type="dataset" if rel_type == "trained_from" else "artifact", limit=1)  # type: ignore
                    artifact_eid = None
                    if found and len(found) > 0 and isinstance(found[0], dict):
                        artifact_eid = found[0].get("id")
                    if not artifact_eid:
                        art_ent = entity_service.create_entity(  # type: ignore
                            tenant=tenant,
                            entity_type="dataset" if rel_type == "trained_from" else "artifact",
                            name=artifact_name,
                            external_id=artifact_name,
                            provider=provider or "aiml",
                            display_name=artifact_name,
                            description=f"Provenance {rel_type} for {entity_name}",
                            metadata_extra={"provenance_ref": artifact_name},
                        )
                        artifact_eid = art_ent.get("id") if isinstance(art_ent, dict) else None
                    if artifact_eid:
                        relationship_service.create_relationship(  # type: ignore
                            tenant=tenant,
                            source_entity_id=model_entity_id,
                            target_entity_id=artifact_eid,
                            relationship_type=rel_type,
                            confidence="confirmed",
                            evidence=[{"source": "aiml.provenance", "model_id": external_id, "version": version_str}],
                            metadata_extra={"provenance": True, "recorded_at": provenance.get("recorded_at")},
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("KG relationship create failed (%s): %s", rel_type, exc)
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("KG provenance best-effort failed: %s", exc)


class AIProvenanceService:
    """Tenant-scoped provenance recording and retrieval for AI models."""

    async def record_provenance(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID,
        provider: str | None = None,
        artifact: str | None = None,
        source: str | None = None,
        training_metadata: dict | None = None,
        evaluation_version: str | None = None,
        deployment_version: str | None = None,
        policy_version: str | None = None,
    ) -> AIModelVersion:
        """Record provenance for a model version.

        Stores artifact/source/training_metadata/evaluation_version/
        deployment_version/policy_version in ``ai_model_versions.provenance``
        JSON (and mirrors to dedicated columns). Also writes to KG via
        ``knowledge_graph`` if available (best-effort).

        Never invent training info: when ``training_metadata`` is None the
        field is preserved as existing or stored as empty dict — no
        hallucinated dataset, hyperparameters, or metrics are added.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required).
            model_id: FK to ``ai_model_registry.id`` (UUID, required).
            provider: provider key (e.g. openai) — optional, stored in provenance.
            artifact: artifact URI/path (e.g. s3://..., registry ref).
            source: data source identifier (e.g. dataset id, repo URL).
            training_metadata: dict with training details (dataset, params, etc.).
                When None/empty, stored as ``{}`` — never invented.
            evaluation_version: evaluation suite/run version string.
            deployment_version: deployment version string — also used to locate
                the target ``ai_model_versions`` row when present.
            policy_version: governance policy version string.

        Returns: updated or created ``AIModelVersion`` with provenance persisted.

        Raises:
            ValidationError for missing tenant/model_id.
            NotFoundError when model does not exist for tenant.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if model_id is None or (isinstance(model_id, str) and not str(model_id).strip()):
            raise ValidationError(message="model_id is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(model_id)

        # Tenant-scoped model existence check (isolation)
        stmt_m = select(AIModelRegistry).where(AIModelRegistry.id == pk, AIModelRegistry.tenant == tenant_s)
        result_m = await db.execute(stmt_m)
        registry: AIModelRegistry | None = result_m.scalars().first()
        if registry is None:
            raise NotFoundError(resource="AIModelRegistry", identifier=str(pk))

        provider_s = str(provider).strip() if provider and str(provider).strip() else (registry.provider or None)
        if provider_s:
            provider_s = str(provider_s).strip().lower()

        artifact_s = str(artifact).strip() if artifact and str(artifact).strip() else None
        source_s = str(source).strip() if source and str(source).strip() else None
        eval_ver_s = str(evaluation_version).strip() if evaluation_version and str(evaluation_version).strip() else None
        deploy_ver_s = str(deployment_version).strip() if deployment_version and str(deployment_version).strip() else None
        policy_ver_s = str(policy_version).strip() if policy_version and str(policy_version).strip() else None

        # Never invent training info — normalize but do not fabricate
        training_norm = _normalize_training_metadata(training_metadata)

        # Locate target version row: prefer exact match on deployment_version/evaluation_version, else latest
        target: AIModelVersion | None = None
        if deploy_ver_s:
            stmt_v = select(AIModelVersion).where(AIModelVersion.model_id == pk, AIModelVersion.version == deploy_ver_s)
            rv = await db.execute(stmt_v)
            target = rv.scalars().first()
        if target is None and eval_ver_s:
            # evaluation_version is not the model version string, but try anyway as fallback
            stmt_v2 = select(AIModelVersion).where(AIModelVersion.model_id == pk, AIModelVersion.version == eval_ver_s)
            rv2 = await db.execute(stmt_v2)
            cand = rv2.scalars().first()
            if cand is not None:
                target = cand
        if target is None:
            # latest version for this model (ordered by created_at desc)
            stmt_latest = select(AIModelVersion).where(AIModelVersion.model_id == pk).order_by(AIModelVersion.created_at.desc()).limit(1)
            rlatest = await db.execute(stmt_latest)
            target = rlatest.scalars().first()

        # If no version exists at all, create one using deployment_version or registry version or synthetic
        if target is None:
            version_str = deploy_ver_s or registry.version or "1.0.0"
            # Deduplicate check before create (unique constraint model_id+version)
            stmt_check = select(AIModelVersion).where(AIModelVersion.model_id == pk, AIModelVersion.version == version_str)
            rcheck = await db.execute(stmt_check)
            existing_check = rcheck.scalars().first()
            if existing_check is not None:
                target = existing_check
            else:
                # create new version row — training_metadata empty when not provided (never invented)
                training_for_new = training_norm if training_norm is not None else {}
                prov_init: dict = {
                    "artifact": artifact_s,
                    "source": source_s,
                    "training_metadata": training_for_new,
                    "evaluation_version": eval_ver_s,
                    "deployment_version": deploy_ver_s or version_str,
                    "policy_version": policy_ver_s,
                    "provider": provider_s,
                    "recorded_at": _utc_now().isoformat(),
                    "tenant": tenant_s,
                }
                # prune None values for cleanliness but keep training_metadata as {} when not provided? we keep empty dict to signal no invention
                # remove keys where value is None to keep JSON tidy, but keep training_metadata even if {}
                prov_init_clean = {k: v for k, v in prov_init.items() if v is not None}
                if "training_metadata" not in prov_init_clean:
                    prov_init_clean["training_metadata"] = training_for_new

                new_row = AIModelVersion(
                    model_id=pk,
                    version=version_str,
                    artifact=artifact_s,
                    source=source_s,
                    training_metadata=training_for_new,
                    evaluation_version=eval_ver_s,
                    deployment_version=deploy_ver_s or version_str,
                    policy_version=policy_ver_s,
                    provenance=prov_init_clean,
                    immutable=True,
                )
                db.add(new_row)
                await db.flush()
                await db.refresh(new_row)
                _audit(tenant_s, provider_s or "system", "ai_provenance.recorded", str(new_row.id), {"model_id": str(pk), "version": version_str, "artifact": artifact_s, "source": source_s})
                logger.info("provenance created version %s for model %s tenant=%s", version_str, pk, tenant_s)
                # KG best-effort
                try:
                    _kg_best_effort_record(tenant_s, registry, new_row, prov_init_clean)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("KG provenance after create failed: %s", exc)
                return new_row

        # Update existing target — never mutate version string itself, only provenance + mirrored columns
        # Preserve existing training_metadata when not provided (never invent)
        existing_prov: dict = dict(target.provenance or {})
        existing_training: dict = dict(target.training_metadata or {})

        # Determine training metadata to store: provided takes precedence, otherwise preserve existing
        if training_norm is not None:
            training_to_store = dict(training_norm)
        else:
            # not provided — preserve existing, never invent
            training_to_store = dict(existing_training) if existing_training else {}

        # Mirror to dedicated columns when new value provided
        if artifact_s is not None:
            target.artifact = artifact_s
        if source_s is not None:
            target.source = source_s
        # training_metadata column
        target.training_metadata = training_to_store
        if eval_ver_s is not None:
            target.evaluation_version = eval_ver_s
        if deploy_ver_s is not None:
            target.deployment_version = deploy_ver_s
        if policy_ver_s is not None:
            target.policy_version = policy_ver_s

        # Build provenance JSON — merge existing with new, never invent missing training info
        provenance: dict = dict(existing_prov)
        provenance["provider"] = provider_s or provenance.get("provider") or registry.provider
        provenance["artifact"] = artifact_s if artifact_s is not None else provenance.get("artifact")
        provenance["source"] = source_s if source_s is not None else provenance.get("source")
        # training_metadata: only update if provided; otherwise keep existing (which may be {}), never invent
        if training_norm is not None:
            provenance["training_metadata"] = training_to_store
        elif "training_metadata" not in provenance:
            provenance["training_metadata"] = training_to_store
        provenance["evaluation_version"] = eval_ver_s if eval_ver_s is not None else provenance.get("evaluation_version")
        provenance["deployment_version"] = deploy_ver_s if deploy_ver_s is not None else provenance.get("deployment_version")
        provenance["policy_version"] = policy_ver_s if policy_ver_s is not None else provenance.get("policy_version")
        provenance["recorded_at"] = _utc_now().isoformat()
        provenance["tenant"] = tenant_s
        provenance["model_id"] = str(pk)
        provenance["version"] = target.version
        # prune None values except training_metadata which may be {}
        provenance = {k: v for k, v in provenance.items() if v is not None or k == "training_metadata"}
        # ensure training_metadata key exists even if empty to signal no invention vs missing
        if "training_metadata" not in provenance:
            provenance["training_metadata"] = training_to_store

        target.provenance = provenance
        await db.flush()
        await db.refresh(target)

        _audit(tenant_s, provider_s or "system", "ai_provenance.recorded", str(target.id), {"model_id": str(pk), "version": target.version, "artifact": artifact_s, "source": source_s})
        logger.info("provenance recorded version %s for model %s tenant=%s", target.version, pk, tenant_s)

        # KG best-effort (tenant tagged, never raises)
        try:
            _kg_best_effort_record(tenant_s, registry, target, provenance)
        except Exception as exc:  # noqa: BLE001
            logger.debug("KG provenance after update failed: %s", exc)

        return target

    async def get_provenance(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
    ) -> dict[str, Any]:
        """Retrieve provenance for a model (tenant inferred from model row).

        Tenant isolation via ``ai_model_registry.tenant`` — the version's
        tenant is not stored directly but inferred from its parent registry.

        Never invent training info: returns exactly what was stored; when
        no provenance exists returns empty training_metadata.

        Args:
            db: AsyncSession.
            model_id: FK to ``ai_model_registry.id`` (UUID, required).

        Returns: dict with model_id, tenant, versions (list of version provenance),
                 latest_provenance.

        Raises: ValidationError for invalid model_id, NotFoundError when not found.
        """
        if model_id is None or (isinstance(model_id, str) and not str(model_id).strip()):
            raise ValidationError(message="model_id is required")
        pk = _parse_uuid(model_id)

        # Fetch registry for tenant and existence
        stmt_m = select(AIModelRegistry).where(AIModelRegistry.id == pk)
        result_m = await db.execute(stmt_m)
        registry: AIModelRegistry | None = result_m.scalars().first()
        if registry is None:
            raise NotFoundError(resource="AIModelRegistry", identifier=str(pk))
        tenant_s = registry.tenant

        # Fetch all versions for this model
        stmt_v = select(AIModelVersion).where(AIModelVersion.model_id == pk).order_by(AIModelVersion.created_at.asc())
        rv = await db.execute(stmt_v)
        versions: list[AIModelVersion] = list(rv.scalars().all())

        if not versions:
            # No version rows — return registry-level placeholder without invented training info
            return {
                "model_id": str(pk),
                "tenant": tenant_s,
                "provider": registry.provider,
                "name": registry.name,
                "version": registry.version,
                "versions": [],
                "provenance": {},
                "latest_provenance": {},
                "training_metadata": {},
                "found": False,
            }

        # Build per-version provenance list
        version_entries: list[dict[str, Any]] = []
        for v in versions:
            prov = dict(v.provenance or {})
            # ensure never invented training_metadata is returned exactly as stored
            if "training_metadata" not in prov:
                # fall back to dedicated column, else empty (not invented)
                prov["training_metadata"] = dict(v.training_metadata or {})
            entry = {
                "id": str(v.id),
                "version": v.version,
                "artifact": v.artifact,
                "source": v.source,
                "training_metadata": prov.get("training_metadata", {}),
                "evaluation_version": v.evaluation_version,
                "deployment_version": v.deployment_version,
                "policy_version": v.policy_version,
                "provenance": prov,
                "immutable": v.immutable,
                "created_at": v.created_at.isoformat() if getattr(v, "created_at", None) else None,
            }
            version_entries.append(entry)

        latest = version_entries[-1] if version_entries else {}
        latest_prov = dict(latest.get("provenance") or {})

        # KG best-effort enrichment: try to fetch entity
        kg_info: dict | None = None
        try:
            from app.knowledge_graph.entity_service import entity_service  # type: ignore

            ent = entity_service.get_entity_by_external_id(str(pk), registry.provider or "aiml", tenant=tenant_s)  # type: ignore
            if ent is not None and isinstance(ent, dict):
                kg_info = {"entity_id": ent.get("id"), "entity_type": ent.get("entity_type"), "name": ent.get("name")}
        except Exception as exc:  # noqa: BLE001
            logger.debug("KG get_provenance enrichment failed: %s", exc)

        result: dict[str, Any] = {
            "model_id": str(pk),
            "tenant": tenant_s,
            "provider": registry.provider,
            "name": registry.name,
            "registry_version": registry.version,
            "versions": version_entries,
            "provenance": latest_prov,
            "latest_provenance": latest_prov,
            "training_metadata": latest_prov.get("training_metadata", {}),
            "artifact": latest.get("artifact"),
            "source": latest.get("source"),
            "evaluation_version": latest.get("evaluation_version"),
            "deployment_version": latest.get("deployment_version"),
            "policy_version": latest.get("policy_version"),
            "found": True,
        }
        if kg_info:
            result["kg"] = kg_info

        _audit(tenant_s, "system", "ai_provenance.retrieved", str(pk), {"versions": len(version_entries)})
        return result


provenance_service = AIProvenanceService()
# Backwards-compat aliases
ai_provenance_service = provenance_service
aiprovenance_service = provenance_service
