"""Entity CRUD service for the Knowledge Graph."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityService:
    """In-memory entity store keyed by UUID string."""

    def __init__(self) -> None:
        self._entities: dict[str, dict] = {}

    # ── CRUD ────────────────────────────────────────────────────────
    def create_entity(
        self,
        tenant: str,
        entity_type: str,
        name: str,
        external_id: str = "",
        provider: str = "",
        display_name: str = "",
        description: str = "",
        metadata_extra: dict | None = None,
        aliases: list[dict] | None = None,
    ) -> dict:
        entity_id = str(uuid.uuid4())
        now = _now()
        entity: dict = {
            "id": entity_id,
            "tenant": tenant,
            "entity_type": entity_type,
            "external_id": external_id,
            "provider": provider,
            "name": name,
            "display_name": display_name or name,
            "description": description,
            "metadata_json": metadata_extra or {},
            "status": "active",
            "aliases": aliases or [],
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        self._entities[entity_id] = entity
        return entity

    def get_entity(self, entity_id: str) -> dict | None:
        return self._entities.get(entity_id)

    def update_entity(self, entity_id: str, **kwargs: object) -> dict | None:
        entity = self._entities.get(entity_id)
        if not entity:
            return None
        for key in ("name", "display_name", "description", "metadata_extra", "status", "aliases"):
            if key in kwargs and kwargs[key] is not None:
                field = "metadata_json" if key == "metadata_extra" else key
                entity[field] = kwargs[key]
        entity["version"] = entity.get("version", 1) + 1
        entity["updated_at"] = _now()
        return entity

    def delete_entity(self, entity_id: str) -> bool:
        entity = self._entities.get(entity_id)
        if not entity:
            return False
        entity["status"] = "deleted"
        entity["updated_at"] = _now()
        return True

    # ── Query ───────────────────────────────────────────────────────
    def list_entities(
        self,
        tenant: str = "",
        entity_type: str = "",
        provider: str = "",
        status: str = "",
        name_contains: str = "",
        external_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        results: list[dict] = []
        for e in self._entities.values():
            if tenant and e["tenant"] != tenant:
                continue
            if entity_type and e["entity_type"] != entity_type:
                continue
            if provider and e["provider"] != provider:
                continue
            if status and e["status"] != status:
                continue
            if external_id and e["external_id"] != external_id:
                continue
            if name_contains and name_contains.lower() not in e["name"].lower():
                continue
            results.append(e)
        results.sort(key=lambda x: x.get("name", ""))
        return results[offset : offset + limit]

    def search_entities(
        self,
        tenant: str,
        query: str,
        entity_type: str = "",
        provider: str = "",
        limit: int = 50,
    ) -> list[dict]:
        q = query.lower()
        results: list[tuple[float, dict]] = []
        for e in self._entities.values():
            if tenant and e["tenant"] != tenant:
                continue
            if entity_type and e["entity_type"] != entity_type:
                continue
            if provider and e["provider"] != provider:
                continue
            score = 0.0
            if e.get("external_id", "").lower() == q:
                score = 1.0
            elif e["name"].lower() == q:
                score = 0.9
            elif q in e["name"].lower():
                score = 0.7
            elif q in e.get("display_name", "").lower():
                score = 0.6
            elif q in e.get("description", "").lower():
                score = 0.5
            else:
                for alias in e.get("aliases", []):
                    if q in alias.get("value", "").lower():
                        score = 0.8
                        break
            if score > 0:
                results.append((score, e))
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def get_entity_by_external_id(
        self, external_id: str, provider: str, tenant: str = "default"
    ) -> dict | None:
        for e in self._entities.values():
            if (
                e["external_id"] == external_id
                and e["provider"] == provider
                and (not tenant or e["tenant"] == tenant)
            ):
                return e
        return None

    def get_entity_by_alias(self, alias_value: str, tenant: str = "default") -> dict | None:
        for e in self._entities.values():
            if tenant and e["tenant"] != tenant:
                continue
            for alias in e.get("aliases", []):
                if alias.get("value", "").lower() == alias_value.lower():
                    return e
        return None

    # ── Aliases ─────────────────────────────────────────────────────
    def add_alias(self, entity_id: str, alias_type: str, alias_value: str, source: str = "") -> dict:
        entity = self._entities.get(entity_id)
        if not entity:
            return {"error": "entity not found"}
        alias = {"type": alias_type, "value": alias_value, "source": source, "created_at": _now()}
        entity.setdefault("aliases", []).append(alias)
        entity["updated_at"] = _now()
        return alias

    def remove_alias(self, entity_id: str, alias_type: str, alias_value: str) -> bool:
        entity = self._entities.get(entity_id)
        if not entity:
            return False
        before = len(entity.get("aliases", []))
        entity["aliases"] = [
            a
            for a in entity.get("aliases", [])
            if not (a.get("type") == alias_type and a.get("value") == alias_value)
        ]
        return len(entity["aliases"]) < before

    def list_aliases(self, entity_id: str) -> list[dict]:
        entity = self._entities.get(entity_id)
        return list(entity.get("aliases", [])) if entity else []

    # ── Bulk / Stats ────────────────────────────────────────────────
    def bulk_create_entities(self, tenant: str, entities: list[dict], source: str = "bulk") -> dict:
        created = 0
        skipped = 0
        errors: list[str] = []
        for data in entities:
            try:
                name = data.get("name", "")
                if not name:
                    skipped += 1
                    continue
                self.create_entity(
                    tenant=tenant,
                    entity_type=data.get("entity_type", "unknown"),
                    name=name,
                    external_id=data.get("external_id", ""),
                    provider=data.get("provider", ""),
                    display_name=data.get("display_name", ""),
                    description=data.get("description", ""),
                    metadata_extra=data.get("metadata_extra"),
                    aliases=data.get("aliases"),
                )
                created += 1
            except Exception as exc:
                errors.append(str(exc))
        return {"created": created, "skipped": skipped, "errors": errors}

    def get_entity_stats(self, tenant: str = "") -> dict:
        by_type: dict[str, int] = {}
        by_provider: dict[str, int] = {}
        by_status: dict[str, int] = {}
        total = 0
        for e in self._entities.values():
            if tenant and e["tenant"] != tenant:
                continue
            total += 1
            by_type[e["entity_type"]] = by_type.get(e["entity_type"], 0) + 1
            by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + 1
            by_status[e["status"]] = by_status.get(e["status"], 0) + 1
        return {"total": total, "by_type": by_type, "by_provider": by_provider, "by_status": by_status}

    # ── Merge ───────────────────────────────────────────────────────
    def merge_entities(self, source_id: str, target_id: str, keep_source: bool = False) -> dict:
        source = self._entities.get(source_id)
        target = self._entities.get(target_id)
        if not source or not target:
            return {"error": "entity not found"}
        for alias in source.get("aliases", []):
            if alias not in target.get("aliases", []):
                target.setdefault("aliases", []).append(alias)
        target["updated_at"] = _now()
        target["version"] = target.get("version", 1) + 1
        if not keep_source:
            source["status"] = "deleted"
            source["updated_at"] = _now()
        return {
            "merged_into": target_id,
            "source_deleted": not keep_source,
            "aliases_moved": len(source.get("aliases", [])),
        }


entity_service = EntityService()
