"""NovaForge Knowledge Graph Platform -- Indexing Service (Volume 51).

Graph ingestion service. Consumes structured payloads emitted by other
platform volumes (repository indexing, deployments, incidents, security
scans, marketplace, analytics, identity, code intelligence, RAG) and
materializes them into the unified organizational knowledge graph as
entities and relationships.

All operations are in-memory and delegated to the injected ``entity_service``
and ``relationship_service`` stores, with optional evidence capture through
``evidence_service``.

Expected collaborator interfaces (duck-typed)::

    entity_service.create_entity(tenant, data) -> dict
    entity_service.get_entity(tenant, entity_id) -> dict | None
    entity_service.find_entities(tenant, entity_type="", external_id="",
                                 name="", status="", limit=0) -> list[dict]
    entity_service.update_entity(tenant, entity_id, updates) -> dict | None
    entity_service.delete_entity(tenant, entity_id) -> bool

    relationship_service.create_relationship(tenant, data) -> dict
    relationship_service.list_relationships(tenant, source_entity_id="",
        target_entity_id="", relationship_type="", limit=0) -> list[dict]

    evidence_service.add_evidence(tenant, target_type, target_id,
                                  evidence) -> dict
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.knowledge_graph.constants import (
    DEFAULT_TENANT,
    MAXResultLimit,
    EvidenceSource,
    IngestionSource,
    RelationshipType,
    SyncStatus,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.strip().lower())
    return "-".join(part for part in cleaned.split("-") if part)[:120]


class GraphIndexingService:
    """Builds and maintains the knowledge graph from upstream volume data."""

    SOURCE_REPOSITORY = IngestionSource.REPOSITORY_INDEXING.value
    SOURCE_DEPLOYMENT = IngestionSource.DEPLOYMENT_EVENTS.value
    SOURCE_INCIDENT = IngestionSource.INCIDENT_EVENTS.value
    SOURCE_SECURITY = IngestionSource.SECURITY_EVENTS.value
    SOURCE_MARKETPLACE = IngestionSource.MARKETPLACE_EVENTS.value
    SOURCE_ANALYTICS = IngestionSource.ANALYTICS_EVENTS.value
    SOURCE_IDENTITY = IngestionSource.IDENTITY_EVENTS.value
    SOURCE_CODE_INTELLIGENCE = EvidenceSource.CODE_ANALYSIS.value
    SOURCE_RAG = IngestionSource.RAG_INGESTION.value
    SOURCE_MANUAL = IngestionSource.MANUAL_ASSIGNMENT.value

    def __init__(self, entity_service, relationship_service, evidence_service=None):
        self.entity_service = entity_service
        self.relationship_service = relationship_service
        self.evidence_service = evidence_service
        self._sync_jobs: dict[str, dict[str, Any]] = {}
        self._entity_index: dict[tuple[str, str, str], str] = {}
        self._relationship_index: dict[tuple[str, str, str], str] = {}
        self._source_payloads: dict[tuple[str, str], dict[str, Any]] = {}

    # ── Repository indexing ───────────────────────────────────────────

    def ingest_from_repository_index(self, tenant: str, repository_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_REPOSITORY)
        self._source_payloads[(tenant, self.SOURCE_REPOSITORY)] = dict(repository_data or {})
        try:
            data = repository_data or {}
            repo = self._create_entity_from_data(
                tenant, "repository", data, self.SOURCE_REPOSITORY, job=job)
            repo_id = repo["entity_id"]

            file_ids: dict[str, str] = {}
            for item in self._as_items(data.get("files")):
                fdata = self._as_data(item, fallback_name_key="path")
                fdata.setdefault("repository", data.get("name", ""))
                file_res = self._create_entity_from_data(
                    tenant, "file", fdata, self.SOURCE_REPOSITORY, job=job)
                file_ids[file_res["entity"]["name"]] = file_res["entity_id"]
                self._link(
                    tenant, repo_id, file_res["entity_id"],
                    RelationshipType.CONTAINS.value, EvidenceSource.GIT.value,
                    job=job)

            for item in self._as_items(data.get("branches")):
                bdata = self._as_data(item, fallback_name_key="branch")
                bdata.setdefault("repository", data.get("name", ""))
                branch = self._create_entity_from_data(
                    tenant, "branch", bdata, self.SOURCE_REPOSITORY, job=job)
                self._link(
                    tenant, repo_id, branch["entity_id"],
                    RelationshipType.CONTAINS.value, EvidenceSource.GIT.value,
                    job=job)

            for item in self._as_items(data.get("symbols")):
                sdata = self._as_data(item, fallback_name_key="symbol")
                parent_id = repo_id
                parent_file = sdata.get("file") or sdata.get("file_path") or ""
                if parent_file and parent_file in file_ids:
                    parent_id = file_ids[parent_file]
                symbol = self._create_entity_from_data(
                    tenant, "symbol", sdata, self.SOURCE_REPOSITORY, job=job)
                self._link(
                    tenant, parent_id, symbol["entity_id"],
                    RelationshipType.CONTAINS.value, EvidenceSource.CODE_ANALYSIS.value
                    if parent_id != repo_id else EvidenceSource.GIT.value,
                    job=job)

            team_ref = data.get("team") or data.get("owner")
            if team_ref:
                team = self._resolve_ref(tenant, team_ref, "team", self.SOURCE_REPOSITORY, job)
                self._link(
                    tenant, team["entity_id"], repo_id,
                    RelationshipType.OWNS.value, EvidenceSource.OWNERSHIP_METADATA.value,
                    data={"metadata": {"ownership_type": "TEAM_OWNER"}}, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Deployment events ─────────────────────────────────────────────

    def ingest_from_deployment(self, tenant: str, deployment_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_DEPLOYMENT)
        self._source_payloads[(tenant, self.SOURCE_DEPLOYMENT)] = dict(deployment_data or {})
        try:
            data = deployment_data or {}
            deploy = self._create_entity_from_data(
                tenant, "deployment", data, self.SOURCE_DEPLOYMENT, job=job)
            deploy_id = deploy["entity_id"]

            service_ref = data.get("service") or data.get("service_name")
            if service_ref:
                service = self._resolve_ref(tenant, service_ref, "service",
                                            self.SOURCE_DEPLOYMENT, job)
                self._link(tenant, service["entity_id"], deploy_id,
                           RelationshipType.DEPLOYS.value,
                           EvidenceSource.DEPLOYMENT_METADATA.value, job=job)

            env_ref = data.get("environment") or data.get("env")
            if env_ref:
                env = self._resolve_ref(tenant, env_ref, "environment",
                                        self.SOURCE_DEPLOYMENT, job)
                self._link(tenant, deploy_id, env["entity_id"],
                           RelationshipType.RUNS_ON.value,
                           EvidenceSource.DEPLOYMENT_METADATA.value, job=job)

            repo_ref = data.get("repository") or data.get("repo")
            if repo_ref:
                repo = self._resolve_ref(tenant, repo_ref, "repository",
                                         self.SOURCE_DEPLOYMENT, job)
                self._link(tenant, deploy_id, repo["entity_id"],
                           RelationshipType.RELATED_TO.value,
                           EvidenceSource.DEPLOYMENT_METADATA.value, job=job)

            for item in self._as_items(data.get("commits")):
                cdata = self._as_data(item, fallback_name_key="sha")
                commit = self._create_entity_from_data(
                    tenant, "commit", cdata, self.SOURCE_DEPLOYMENT, job=job)
                self._link(tenant, deploy_id, commit["entity_id"],
                           RelationshipType.CONTAINS.value,
                           EvidenceSource.DEPLOYMENT_METADATA.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Incident events ───────────────────────────────────────────────

    def ingest_from_incident(self, tenant: str, incident_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_INCIDENT)
        self._source_payloads[(tenant, self.SOURCE_INCIDENT)] = dict(incident_data or {})
        try:
            data = incident_data or {}
            incident = self._create_entity_from_data(
                tenant, "incident", data, self.SOURCE_INCIDENT, job=job)
            incident_id = incident["entity_id"]

            for item in self._as_items(data.get("services")):
                sdata = self._as_data(item, fallback_name_key="service")
                service = self._resolve_ref(tenant, sdata, "service",
                                            self.SOURCE_INCIDENT, job)
                self._link(tenant, incident_id, service["entity_id"],
                           RelationshipType.AFFECTS.value,
                           EvidenceSource.INCIDENT_DATA.value, job=job)

            deploy_ref = data.get("deployment")
            if deploy_ref:
                deploy = self._resolve_ref(tenant, deploy_ref, "deployment",
                                           self.SOURCE_INCIDENT, job)
                self._link(tenant, incident_id, deploy["entity_id"],
                           RelationshipType.CAUSED_BY.value,
                           EvidenceSource.INCIDENT_DATA.value, job=job)

            for item in self._as_items(data.get("commits")):
                cdata = self._as_data(item, fallback_name_key="sha")
                commit = self._resolve_ref(tenant, cdata, "commit",
                                           self.SOURCE_INCIDENT, job)
                self._link(tenant, incident_id, commit["entity_id"],
                           RelationshipType.CAUSED_BY.value,
                           EvidenceSource.INCIDENT_DATA.value, job=job)

            for item in self._as_items(data.get("findings")):
                fdata = self._as_data(item, fallback_name_key="finding")
                finding = self._resolve_ref(tenant, fdata, "security_finding",
                                            self.SOURCE_INCIDENT, job)
                self._link(tenant, incident_id, finding["entity_id"],
                           RelationshipType.CAUSED_BY.value,
                           EvidenceSource.INCIDENT_DATA.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Security findings ─────────────────────────────────────────────

    def ingest_from_security_finding(self, tenant: str, finding_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_SECURITY)
        self._source_payloads[(tenant, self.SOURCE_SECURITY)] = dict(finding_data or {})
        try:
            data = finding_data or {}
            finding = self._create_entity_from_data(
                tenant, "security_finding", data, self.SOURCE_SECURITY, job=job)
            finding_id = finding["entity_id"]

            for item in self._as_items(data.get("files")):
                fdata = self._as_data(item, fallback_name_key="path")
                target = self._resolve_ref(tenant, fdata, "file",
                                           self.SOURCE_SECURITY, job)
                self._link(tenant, finding_id, target["entity_id"],
                           RelationshipType.AFFECTS.value,
                           EvidenceSource.SECURITY_SCAN.value, job=job)

            for item in self._as_items(data.get("dependencies")):
                ddata = self._as_data(item, fallback_name_key="purl")
                target = self._resolve_ref(tenant, ddata, "dependency",
                                           self.SOURCE_SECURITY, job)
                self._link(tenant, finding_id, target["entity_id"],
                           RelationshipType.AFFECTS.value,
                           EvidenceSource.SECURITY_SCAN.value, job=job)

            for item in self._as_items(data.get("artifacts")):
                adata = self._as_data(item, fallback_name_key="artifact")
                target = self._resolve_ref(tenant, adata, "artifact",
                                           self.SOURCE_SECURITY, job)
                self._link(tenant, finding_id, target["entity_id"],
                           RelationshipType.AFFECTS.value,
                           EvidenceSource.SECURITY_SCAN.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Marketplace ───────────────────────────────────────────────────

    def ingest_from_marketplace(self, tenant: str, package_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_MARKETPLACE)
        self._source_payloads[(tenant, self.SOURCE_MARKETPLACE)] = dict(package_data or {})
        try:
            data = package_data or {}
            package = self._create_entity_from_data(
                tenant, "marketplace_package", data, self.SOURCE_MARKETPLACE, job=job)
            package_id = package["entity_id"]

            publisher_ref = data.get("publisher")
            if publisher_ref:
                pdata = self._as_data(publisher_ref, fallback_name_key="publisher")
                pdata.setdefault("entity_type", pdata.get("entity_type", "organization"))
                publisher = self._create_entity_from_data(
                    tenant, pdata.get("entity_type", "organization"),
                    pdata, self.SOURCE_MARKETPLACE, job=job)
                self._link(tenant, publisher["entity_id"], package_id,
                           RelationshipType.OWNS.value,
                           EvidenceSource.API_METADATA.value, job=job)

            for item in self._as_items(data.get("dependencies")):
                ddata = self._as_data(item, fallback_name_key="dependency")
                dep = self._create_entity_from_data(
                    tenant, "package", ddata, self.SOURCE_MARKETPLACE, job=job)
                self._link(tenant, package_id, dep["entity_id"],
                           RelationshipType.DEPENDS_ON.value,
                           EvidenceSource.API_METADATA.value,
                           data={"metadata": {
                               "version_constraint": ddata.get("version", "")}},
                           job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Analytics ─────────────────────────────────────────────────────

    def ingest_from_analytics(self, tenant: str, metric_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_ANALYTICS)
        self._source_payloads[(tenant, self.SOURCE_ANALYTICS)] = dict(metric_data or {})
        try:
            data = metric_data or {}
            entity_type = data.get("metric_type") or "metric"
            metric = self._create_entity_from_data(
                tenant, entity_type, data, self.SOURCE_ANALYTICS, job=job)
            metric_id = metric["entity_id"]

            service_ref = data.get("service") or data.get("service_name")
            if service_ref:
                service = self._resolve_ref(tenant, service_ref, "service",
                                            self.SOURCE_ANALYTICS, job)
                self._link(tenant, service["entity_id"], metric_id,
                           RelationshipType.PRODUCES.value,
                           EvidenceSource.ANALYTICS_DATA.value, job=job)

            project_ref = data.get("project")
            if project_ref:
                project = self._resolve_ref(tenant, project_ref, "project",
                                            self.SOURCE_ANALYTICS, job)
                self._link(tenant, project["entity_id"], metric_id,
                           RelationshipType.PRODUCES.value,
                           EvidenceSource.ANALYTICS_DATA.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Identity ──────────────────────────────────────────────────────

    def ingest_from_identity(self, tenant: str, user_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_IDENTITY)
        self._source_payloads[(tenant, self.SOURCE_IDENTITY)] = dict(user_data or {})
        try:
            data = user_data or {}
            user = self._create_entity_from_data(
                tenant, "user", data, self.SOURCE_IDENTITY, job=job)
            user_id = user["entity_id"]

            for item in self._as_items(data.get("teams")):
                tdata = self._as_data(item, fallback_name_key="team")
                team = self._create_entity_from_data(
                    tenant, "team", tdata, self.SOURCE_IDENTITY, job=job)
                self._link(tenant, user_id, team["entity_id"],
                           RelationshipType.MEMBER_OF.value,
                           EvidenceSource.API_METADATA.value, job=job)

                for proj in self._as_items(tdata.get("projects")):
                    project = self._resolve_ref(tenant, proj, "project",
                                                self.SOURCE_IDENTITY, job)
                    self._link(tenant, team["entity_id"], project["entity_id"],
                               RelationshipType.OWNS.value,
                               EvidenceSource.OWNERSHIP_METADATA.value,
                               data={"metadata": {"ownership_type": "TEAM_OWNER"}},
                               job=job)

                for repo in self._as_items(tdata.get("repositories")):
                    repository = self._resolve_ref(tenant, repo, "repository",
                                                   self.SOURCE_IDENTITY, job)
                    self._link(tenant, team["entity_id"], repository["entity_id"],
                               RelationshipType.OWNS.value,
                               EvidenceSource.OWNERSHIP_METADATA.value,
                               data={"metadata": {"ownership_type": "TEAM_OWNER"}},
                               job=job)

            manager_ref = data.get("manager")
            if manager_ref:
                manager = self._resolve_ref(tenant, manager_ref, "user",
                                            self.SOURCE_IDENTITY, job)
                self._link(tenant, user_id, manager["entity_id"],
                           RelationshipType.RELATED_TO.value,
                           EvidenceSource.API_METADATA.value,
                           data={"metadata": {"relation": "reports_to"}}, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Code intelligence ─────────────────────────────────────────────

    def ingest_from_code_intelligence(self, tenant: str, code_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_CODE_INTELLIGENCE)
        self._source_payloads[(tenant, self.SOURCE_CODE_INTELLIGENCE)] = dict(code_data or {})
        try:
            data = code_data or {}
            repo_id = ""
            repo_ref = data.get("repository") or data.get("repo")
            if repo_ref:
                repo = self._resolve_ref(tenant, repo_ref, "repository",
                                         self.SOURCE_CODE_INTELLIGENCE, job)
                repo_id = repo["entity_id"]

            file_ids: dict[str, str] = {}
            symbol_ids: dict[str, str] = {}
            for item in self._as_items(data.get("files")):
                fdata = self._as_data(item, fallback_name_key="path")
                path = fdata.get("name", "")
                fdata.setdefault("repository", data.get("repository", ""))
                file_res = self._create_entity_from_data(
                    tenant, "file", fdata, self.SOURCE_CODE_INTELLIGENCE, job=job)
                file_ids[path] = file_res["entity_id"]
                if repo_id:
                    self._link(tenant, repo_id, file_res["entity_id"],
                               RelationshipType.CONTAINS.value,
                               EvidenceSource.CODE_ANALYSIS.value, job=job)

                for sym in self._as_items(fdata.get("symbols")):
                    sdata = self._as_data(sym, fallback_name_key="symbol")
                    qual_name = f"{path}::{sdata.get('name', '')}"
                    sdata.setdefault("external_id", qual_name)
                    sdata.setdefault("file", path)
                    sym_res = self._create_entity_from_data(
                        tenant, "symbol", sdata, self.SOURCE_CODE_INTELLIGENCE, job=job)
                    symbol_ids[qual_name] = sym_res["entity_id"]
                    self._link(tenant, file_res["entity_id"], sym_res["entity_id"],
                               RelationshipType.CONTAINS.value,
                               EvidenceSource.CODE_ANALYSIS.value, job=job)

            for item in self._as_items(data.get("imports")):
                idata = self._as_data(item, fallback_name_key="import")
                src_path = idata.get("file") or idata.get("source", "")
                tgt_path = idata.get("target") or idata.get("module", "")
                src_id = file_ids.get(src_path)
                tgt = self._resolve_ref(tenant, tgt_path, "file",
                                        self.SOURCE_CODE_INTELLIGENCE, job)
                if src_id:
                    self._link(tenant, src_id, tgt["entity_id"],
                               RelationshipType.IMPORTS.value,
                               EvidenceSource.CODE_ANALYSIS.value, job=job)

            for item in self._as_items(data.get("calls")):
                cdata = self._as_data(item, fallback_name_key="call")
                caller_key = cdata.get("caller", "")
                callee_key = cdata.get("callee", "")
                caller_id = symbol_ids.get(caller_key)
                if not caller_id:
                    caller = self._resolve_ref(tenant, caller_key, "symbol",
                                               self.SOURCE_CODE_INTELLIGENCE, job)
                    caller_id = caller["entity_id"]
                callee = self._resolve_ref(tenant, callee_key, "symbol",
                                           self.SOURCE_CODE_INTELLIGENCE, job)
                self._link(tenant, caller_id, callee["entity_id"],
                           RelationshipType.CALLS.value,
                           EvidenceSource.CODE_ANALYSIS.value, job=job)

            for item in self._as_items(data.get("depends_on")):
                ddata = self._as_data(item, fallback_name_key="dependency")
                src_path = ddata.get("file", "")
                src_id = file_ids.get(src_path)
                if not src_id:
                    continue
                target = self._resolve_ref(tenant, ddata.get("target") or ddata.get("name"),
                                           "package", self.SOURCE_CODE_INTELLIGENCE, job)
                self._link(tenant, src_id, target["entity_id"],
                           RelationshipType.DEPENDS_ON.value,
                           EvidenceSource.CODE_ANALYSIS.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── RAG documents ─────────────────────────────────────────────────

    def ingest_from_rag(self, tenant: str, rag_data: dict) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_RAG)
        self._source_payloads[(tenant, self.SOURCE_RAG)] = dict(rag_data or {})
        try:
            data = rag_data or {}
            doc = self._create_entity_from_data(
                tenant, "document", data, self.SOURCE_RAG, job=job)
            doc_id = doc["entity_id"]

            for ref, etype in (
                (data.get("project"), "project"),
                (data.get("repository"), "repository"),
                (data.get("service"), "service"),
            ):
                if not ref:
                    continue
                target = self._resolve_ref(tenant, ref, etype, self.SOURCE_RAG, job)
                self._link(tenant, doc_id, target["entity_id"],
                           RelationshipType.DOCUMENTS.value,
                           EvidenceSource.DOCUMENT_REFERENCE.value, job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Manual ingestion ──────────────────────────────────────────────

    def ingest_manual(self, tenant: str, entities: list[dict],
                      relationships: list[dict]) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, self.SOURCE_MANUAL)
        try:
            for ent in entities or []:
                if not isinstance(ent, dict):
                    job["errors"].append(f"invalid entity payload: {ent!r}")
                    continue
                self._create_entity_from_data(
                    tenant, ent.get("entity_type", "custom"), ent,
                    ent.get("source", self.SOURCE_MANUAL), job=job)

            for rel in relationships or []:
                if not isinstance(rel, dict):
                    job["errors"].append(f"invalid relationship payload: {rel!r}")
                    continue
                source = rel.get("source_entity_id") or rel.get("source")
                target = rel.get("target_entity_id") or rel.get("target")
                src = self._resolve_ref(tenant, source,
                                        rel.get("source_type", "custom"),
                                        self.SOURCE_MANUAL, job)
                tgt = self._resolve_ref(tenant, target,
                                        rel.get("target_type", "custom"),
                                        self.SOURCE_MANUAL, job)
                self._link(
                    tenant, src["entity_id"], tgt["entity_id"],
                    rel.get("relationship_type", RelationshipType.RELATED_TO.value),
                    rel.get("evidence_source", EvidenceSource.ADMINISTRATOR_ASSIGNMENT.value),
                    data={"confidence": rel.get("confidence", "confirmed"),
                          "metadata": rel.get("metadata", {})},
                    job=job)
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    # ── Rebuild / incremental ─────────────────────────────────────────

    def full_rebuild(self, tenant: str = "") -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, "full_rebuild")
        dispatch = {
            self.SOURCE_REPOSITORY: self.ingest_from_repository_index,
            self.SOURCE_DEPLOYMENT: self.ingest_from_deployment,
            self.SOURCE_INCIDENT: self.ingest_from_incident,
            self.SOURCE_SECURITY: self.ingest_from_security_finding,
            self.SOURCE_MARKETPLACE: self.ingest_from_marketplace,
            self.SOURCE_ANALYTICS: self.ingest_from_analytics,
            self.SOURCE_IDENTITY: self.ingest_from_identity,
            self.SOURCE_CODE_INTELLIGENCE: self.ingest_from_code_intelligence,
            self.SOURCE_RAG: self.ingest_from_rag,
        }
        results: list[dict] = []
        try:
            for (payload_tenant, source), payload in list(self._source_payloads.items()):
                if tenant and payload_tenant != tenant:
                    continue
                handler = dispatch.get(source)
                if handler is None:
                    continue
                summary = handler(payload_tenant, payload)
                results.append({
                    "tenant": payload_tenant,
                    "source": source,
                    "job_id": summary.get("job_id"),
                    "entities_created": summary.get("entities_created", 0),
                    "relationships_created": summary.get("relationships_created", 0),
                    "errors": summary.get("errors", []),
                })
            job["entities_created"] = sum(r["entities_created"] for r in results)
            job["relationships_created"] = sum(r["relationships_created"] for r in results)
            for r in results:
                job["errors"].extend(r["errors"])
            job["details"] = {"sources_replayed": len(results)}
        except Exception as exc:
            job["errors"].append(str(exc))
        summary = self._finish_job(job)
        summary["sources"] = results
        return summary

    def incremental_update(self, tenant: str, source: str, changes: list[dict]) -> dict:
        tenant = tenant or DEFAULT_TENANT
        job = self._start_job(tenant, source or self.SOURCE_MANUAL)
        try:
            for change in changes or []:
                if not isinstance(change, dict):
                    job["errors"].append(f"invalid change payload: {change!r}")
                    continue
                try:
                    self._apply_change(tenant, source, change, job)
                except Exception as exc:
                    job["errors"].append(
                        f"change {change.get('op', '?')} failed: {exc}")
        except Exception as exc:
            job["errors"].append(str(exc))
        return self._finish_job(job)

    def get_sync_status(self, tenant: str = "") -> dict:
        tenant = tenant or DEFAULT_TENANT
        jobs = [
            j for j in self._sync_jobs.values()
            if not tenant or j["tenant"] == tenant
        ]
        jobs.sort(key=lambda j: j.get("started_at", ""), reverse=True)
        counts: dict[str, int] = {}
        for j in jobs:
            counts[j["status"]] = counts.get(j["status"], 0) + 1
        completed_times = [j["completed_at"] for j in jobs if j.get("completed_at")]
        return {
            "tenant": tenant,
            "total_jobs": len(jobs),
            "completed": counts.get(SyncStatus.COMPLETED.value, 0),
            "failed": counts.get(SyncStatus.FAILED.value, 0),
            "pending": counts.get(SyncStatus.PENDING.value, 0)
            + counts.get(SyncStatus.IN_PROGRESS.value, 0),
            "partial": counts.get(SyncStatus.PARTIAL.value, 0),
            "last_sync_at": max(completed_times) if completed_times else "",
            "jobs": jobs[:25],
            "generated_at": _now_iso(),
        }

    # ── Entity / relationship helpers ─────────────────────────────────

    def _create_entity_from_data(self, tenant: str, entity_type: str, data: dict,
                                 source: str, job: dict | None = None) -> dict:
        tenant = tenant or DEFAULT_TENANT
        data = dict(data or {})
        name = str(
            data.get("name")
            or data.get("display_name")
            or data.get("title")
            or data.get("path")
            or data.get("key")
            or ""
        ).strip()
        external_id = str(data.get("external_id") or data.get("id") or data.get("key") or "").strip()
        if not name and not external_id:
            digest = hashlib.sha1(
                json.dumps(data, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()[:16]
            name = f"{entity_type}-{digest}"
        if not external_id:
            external_id = f"{source}:{_slug(name)}"

        index_key = (tenant, str(entity_type), external_id)
        existing_id = self._entity_index.get(index_key)
        if existing_id:
            existing = self.entity_service.get_entity(tenant, existing_id)
            if existing:
                merged_meta = dict(
                    existing.get("metadata_extra")
                    or existing.get("metadata_json")
                    or {}
                )
                merged_meta.update(self._build_metadata(data, source))
                updated = self.entity_service.update_entity(tenant, existing_id, {
                    "display_name": data.get("display_name", ""),
                    "description": data.get("description", ""),
                    "metadata_extra": merged_meta,
                })
                if job is not None:
                    job["entities_updated"] += 1
                self._attach_evidence(tenant, "entity", existing_id, source, data)
                entity = updated or existing
                return {"entity_id": existing_id, "entity": entity, "created": False}

        payload = {
            "tenant": tenant,
            "entity_type": str(entity_type),
            "external_id": external_id,
            "provider": str(data.get("provider", "")),
            "name": name or external_id,
            "display_name": str(data.get("display_name") or name or external_id),
            "description": str(data.get("description", "")),
            "metadata_extra": self._build_metadata(data, source),
            "aliases": list(data.get("aliases", [])),
        }
        entity = self.entity_service.create_entity(tenant, payload)
        entity_id = str(entity.get("id") or entity.get("entity_id") or "")
        self._entity_index[index_key] = entity_id
        alt_key = (tenant, "", external_id)
        self._entity_index.setdefault(alt_key, entity_id)
        if job is not None:
            job["entities_created"] += 1
            job["entity_ids"].append(entity_id)
        self._attach_evidence(tenant, "entity", entity_id, source, data)
        return {"entity_id": entity_id, "entity": entity, "created": True}

    def _create_relationship_from_data(self, tenant: str, source_id: str,
                                       target_id: str, rel_type: str,
                                       evidence_source: str,
                                       data: dict | None = None) -> dict:
        tenant = tenant or DEFAULT_TENANT
        data = dict(data or {})
        if not source_id or not target_id or source_id == target_id:
            return {"relationship": None, "created": False, "duplicate": False}

        index_key = (tenant, str(source_id), str(target_id), str(rel_type))
        existing_rel_id = self._relationship_index.get(index_key)
        if existing_rel_id:
            return {"relationship": {"id": existing_rel_id},
                    "created": False, "duplicate": True}

        now = _now_iso()
        evidence_entry = {
            "source": evidence_source,
            "observed_at": now,
        }
        if data.get("reference"):
            evidence_entry["reference"] = str(data["reference"])
        payload = {
            "tenant": tenant,
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "relationship_type": str(rel_type),
            "confidence": str(data.get("confidence", "confirmed")),
            "evidence": [evidence_entry],
            "metadata_extra": dict(data.get("metadata") or {}),
            "observed_at": now,
        }
        rel = self.relationship_service.create_relationship(tenant, payload)
        rel_id = str(rel.get("id") or rel.get("relationship_id") or "")
        self._relationship_index[index_key] = rel_id
        if data.get("job") is not None:
            data["job"]["relationships_created"] += 1
            data["job"]["relationship_ids"].append(rel_id)
        self._attach_evidence(tenant, "relationship", rel_id, evidence_source, data)
        return {"relationship": rel, "created": True, "duplicate": False}

    # ── Internal plumbing ─────────────────────────────────────────────

    def _link(self, tenant: str, source_id: str, target_id: str, rel_type: str,
              evidence_source: str, data: dict | None = None,
              job: dict | None = None) -> dict | None:
        payload = dict(data or {})
        payload["job"] = job
        result = self._create_relationship_from_data(
            tenant, source_id, target_id, rel_type, evidence_source, payload)
        rel = result.get("relationship")
        if rel and result.get("created") and job is not None:
            pass
        return rel

    def _resolve_ref(self, tenant: str, ref: Any, default_type: str,
                     source: str, job: dict | None = None) -> dict:
        if isinstance(ref, dict):
            ref = dict(ref)
            ref.setdefault("entity_type", ref.get("entity_type", default_type))
            return self._create_entity_from_data(
                tenant, ref.get("entity_type", default_type), ref, source, job=job)
        ref_str = str(ref or "").strip()
        if not ref_str:
            raise ValueError("empty entity reference")
        existing = self._find_entity_by_ref(tenant, ref_str, default_type)
        if existing:
            return {"entity_id": str(existing.get("id") or ""),
                    "entity": existing, "created": False}
        return self._create_entity_from_data(
            tenant, default_type,
            {"name": ref_str, "external_id": f"{source}:{_slug(ref_str)}"},
            source, job=job)

    def _find_entity_by_ref(self, tenant: str, ref: str,
                            entity_type: str = "") -> dict | None:
        for key in ((tenant, entity_type, ref), (tenant, "", ref)):
            entity_id = self._entity_index.get(key)
            if entity_id:
                found = self.entity_service.get_entity(tenant, entity_id)
                if found:
                    return found
        matches = self.entity_service.find_entities(tenant, external_id=ref)
        if matches:
            return matches[0]
        matches = self.entity_service.find_entities(tenant, name=ref,
                                                    entity_type=entity_type)
        if matches:
            return matches[0]
        return None

    def _apply_change(self, tenant: str, source: str, change: dict,
                      job: dict) -> None:
        op = str(change.get("op") or change.get("operation") or "create").lower()
        is_relationship = bool(
            change.get("relationship_type")
            or change.get("source_entity_id")
            or change.get("target_entity_id")
        )
        if is_relationship:
            self._apply_relationship_change(tenant, source, change, op, job)
            return
        entity_type = change.get("entity_type", "custom")
        if op == "create":
            self._create_entity_from_data(
                tenant, entity_type, change.get("data", {}), source, job=job)
        elif op == "update":
            entity_id = self._lookup_change_target(tenant, change)
            if not entity_id:
                raise LookupError("target entity not found")
            updates = change.get("changes") or change.get("data") or {}
            payload = {k: v for k, v in updates.items()
                       if k in ("name", "display_name", "description",
                                "metadata_extra", "status", "aliases")}
            self.entity_service.update_entity(tenant, entity_id, payload)
            job["entities_updated"] += 1
        elif op == "delete":
            entity_id = self._lookup_change_target(tenant, change)
            if not entity_id:
                raise LookupError("target entity not found")
            deleted = False
            try:
                deleted = bool(self.entity_service.delete_entity(tenant, entity_id))
            except Exception:
                deleted = False
            if not deleted:
                self.entity_service.update_entity(tenant, entity_id, {
                    "status": "deleted",
                })
            job["entities_deleted"] += 1
        else:
            raise ValueError(f"unsupported operation: {op}")

    def _apply_relationship_change(self, tenant: str, source: str,
                                   change: dict, op: str, job: dict) -> None:
        if op == "create":
            src = self._resolve_ref(tenant, change.get("source_entity_id")
                                    or change.get("source"),
                                    change.get("source_type", "custom"), source, job)
            tgt = self._resolve_ref(tenant, change.get("target_entity_id")
                                    or change.get("target"),
                                    change.get("target_type", "custom"), source, job)
            self._link(
                tenant, src["entity_id"], tgt["entity_id"],
                change.get("relationship_type",
                           RelationshipType.RELATED_TO.value),
                change.get("evidence_source",
                           EvidenceSource.EVENT_BUS.value),
                data={"metadata": change.get("metadata", {})}, job=job)
        elif op == "delete":
            rel_id = str(change.get("relationship_id", ""))
            if rel_id:
                self.relationship_service.delete_relationship(tenant, rel_id)
                job["relationships_deleted"] += 1
        elif op == "update":
            rel_id = str(change.get("relationship_id", ""))
            updates = change.get("changes") or {}
            self.relationship_service.update_relationship(tenant, rel_id, updates)
            job["relationships_updated"] += 1
        else:
            raise ValueError(f"unsupported relationship operation: {op}")

    def _lookup_change_target(self, tenant: str, change: dict) -> str:
        entity_id = str(change.get("entity_id", ""))
        if entity_id:
            return entity_id
        data = change.get("data") or {}
        ref = str(change.get("external_id") or data.get("external_id")
                  or change.get("name") or data.get("name") or "")
        if not ref:
            return ""
        found = self._find_entity_by_ref(
            tenant, ref, str(change.get("entity_type", data.get("entity_type", ""))))
        return str(found.get("id") or "") if found else ""

    @staticmethod
    def _build_metadata(data: dict, source: str) -> dict:
        meta = dict(data.get("metadata") or data.get("metadata_extra") or {})
        meta.setdefault("source", source)
        meta["ingested_at"] = _now_iso()
        for passthrough in ("status", "version", "severity", "language",
                            "environment", "branch", "sha"):
            if data.get(passthrough) is not None:
                meta.setdefault(passthrough, data[passthrough])
        return meta

    @staticmethod
    def _as_items(value: Any) -> list:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    @staticmethod
    def _as_data(item: Any, fallback_name_key: str = "name") -> dict:
        if isinstance(item, dict):
            data = dict(item)
            if not data.get("name"):
                for key in (fallback_name_key, "path", "id", "title"):
                    if data.get(key):
                        data["name"] = data[key]
                        break
            return data
        return {"name": str(item)}

    def _attach_evidence(self, tenant: str, target_type: str, target_id: str,
                         source: str, data: dict) -> None:
        if self.evidence_service is None or not target_id:
            return
        evidence = {
            "source": source,
            "observed_at": _now_iso(),
            "reference": str(data.get("evidence_reference")
                             or data.get("reference") or ""),
        }
        try:
            self.evidence_service.add_evidence(
                tenant, target_type, target_id, evidence)
        except Exception:
            pass

    def _start_job(self, tenant: str, source: str) -> dict:
        job = {
            "job_id": f"sync-{uuid.uuid4().hex[:12]}",
            "tenant": tenant,
            "source": source,
            "status": SyncStatus.IN_PROGRESS.value,
            "entities_created": 0,
            "entities_updated": 0,
            "entities_deleted": 0,
            "relationships_created": 0,
            "relationships_updated": 0,
            "relationships_deleted": 0,
            "entity_ids": [],
            "relationship_ids": [],
            "errors": [],
            "started_at": _now_iso(),
            "completed_at": "",
            "duration_ms": 0.0,
        }
        self._sync_jobs[job["job_id"]] = job
        return job

    def _finish_job(self, job: dict) -> dict:
        job["completed_at"] = _now_iso()
        started = self._parse_ts(job["started_at"])
        if started is not None:
            job["duration_ms"] = round(
                (time.time() - started.timestamp()) * 1000.0, 3)
        if job["errors"]:
            job["status"] = SyncStatus.PARTIAL.value
        else:
            job["status"] = SyncStatus.COMPLETED.value
        return {
            "ok": not job["errors"],
            "job_id": job["job_id"],
            "tenant": job["tenant"],
            "source": job["source"],
            "status": job["status"],
            "entities_created": job["entities_created"],
            "entities_updated": job["entities_updated"],
            "entities_deleted": job["entities_deleted"],
            "relationships_created": job["relationships_created"],
            "relationships_updated": job["relationships_updated"],
            "relationships_deleted": job["relationships_deleted"],
            "entity_ids": list(job["entity_ids"]),
            "relationship_ids": list(job["relationship_ids"]),
            "errors": list(job["errors"]),
            "duration_ms": job["duration_ms"],
            "completed_at": job["completed_at"],
        }

    @staticmethod
    def _parse_ts(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (ValueError, TypeError):
            return None


__all__ = ["GraphIndexingService"]
