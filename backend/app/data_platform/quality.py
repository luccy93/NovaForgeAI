"""Quality service — versioned rules, async jobs, results."""

import uuid
import re
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataQualityRule, DataQualityResult

RULE_TYPES = {"required", "range", "regex", "uniqueness", "referential"}


async def create_rule(db: AsyncSession, tenant: str, dataset_id: str, payload: dict) -> DataQualityRule:
    rtype = (payload.get("rule_type") or "").lower()
    if rtype not in RULE_TYPES:
        raise ValueError(f"invalid rule_type {rtype}")
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    try:
        did = uuid.UUID(dataset_id)
    except Exception:
        raise ValueError("invalid dataset_id")
    # Check dataset exists and tenant
    from app.data_platform.models import DataDataset
    q = select(DataDataset).where(DataDataset.id == did, DataDataset.tenant == tenant)
    res = await db.execute(q)
    if not res.scalar_one_or_none():
        raise ValueError("dataset not found")
    version = payload.get("version", "1.0")
    # Check existing version
    q2 = select(DataQualityRule).where(DataQualityRule.dataset_id == did, DataQualityRule.name == name, DataQualityRule.version == version)
    res2 = await db.execute(q2)
    if res2.scalar_one_or_none():
        raise ValueError("rule version already exists")
    rule = DataQualityRule(
        dataset_id=did,
        tenant=tenant,
        name=name,
        rule_type=rtype,
        params=payload.get("params", {}),
        version=version,
        enabled=payload.get("enabled", True),
    )
    db.add(rule)
    await db.flush()
    return rule


async def list_rules(db: AsyncSession, tenant: str, dataset_id: str | None = None, limit: int = 50) -> list[DataQualityRule]:
    q = select(DataQualityRule).where(DataQualityRule.tenant == tenant)
    if dataset_id:
        try:
            did = uuid.UUID(dataset_id)
            q = q.where(DataQualityRule.dataset_id == did)
        except Exception:
            pass
    q = q.order_by(DataQualityRule.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def run_quality_job(db: AsyncSession, tenant: str, dataset_id: str, records: list[dict]) -> list[DataQualityResult]:
    # Get enabled rules
    try:
        did = uuid.UUID(dataset_id)
    except Exception:
        raise ValueError("invalid dataset_id")
    rules = await list_rules(db, tenant, dataset_id)
    results = []
    for rule in rules:
        if not rule.enabled:
            continue
        passed, failed, sample = _evaluate_rule(rule, records)
        res = DataQualityResult(
            dataset_id=did,
            tenant=tenant,
            rule_id=rule.id,
            rule_version=rule.version,
            passed=passed,
            failed=failed,
            sample_metadata={"sample": sample, "total": len(records)},
            timestamp=datetime.now(timezone.utc),
        )
        db.add(res)
        results.append(res)
    await db.flush()
    return results


def _evaluate_rule(rule: DataQualityRule, records: list[dict]) -> tuple[int, int, dict | None]:
    passed = 0
    failed = 0
    sample = None
    rtype = rule.rule_type
    params = rule.params or {}
    for rec in records:
        ok = True
        if rtype == "required":
            field = params.get("field")
            if not field or rec.get(field) is None or rec.get(field) == "":
                ok = False
        elif rtype == "range":
            field = params.get("field")
            min_v = params.get("min")
            max_v = params.get("max")
            val = rec.get(field)
            try:
                if val is None or (min_v is not None and float(val) < float(min_v)) or (max_v is not None and float(val) > float(max_v)):
                    ok = False
            except Exception:
                ok = False
        elif rtype == "regex":
            field = params.get("field")
            pattern = params.get("pattern")
            val = str(rec.get(field, ""))
            if pattern and not re.match(pattern, val):
                ok = False
        elif rtype == "uniqueness":
            # Handled outside per batch: check duplicates
            pass
        elif rtype == "referential":
            # Simplified: check foreign field exists
            field = params.get("field")
            if field and not rec.get(field):
                ok = False
        if ok:
            passed += 1
        else:
            failed += 1
            if sample is None:
                # Mask sensitive: only store field names, not raw values if sensitive
                sample = {k: "***" if "email" in k or "ssn" in k else v for k, v in rec.items()}
    # For uniqueness, need to check duplicates across records
    if rtype == "uniqueness":
        field = params.get("field")
        if field:
            seen = set()
            dup = 0
            for rec in records:
                val = rec.get(field)
                if val in seen:
                    dup += 1
                else:
                    seen.add(val)
            failed = dup
            passed = len(records) - dup
    return passed, failed, sample


async def get_results(db: AsyncSession, tenant: str, dataset_id: str, limit: int = 50) -> list[DataQualityResult]:
    try:
        did = uuid.UUID(dataset_id)
    except Exception:
        raise ValueError("invalid dataset_id")
    q = select(DataQualityResult).where(DataQualityResult.tenant == tenant, DataQualityResult.dataset_id == did).order_by(DataQualityResult.timestamp.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def profile_dataset(db: AsyncSession, tenant: str, dataset_id: str, records: list[dict]) -> dict:
    if not records:
        return {"row_count": 0, "null_rate": {}, "distinct_count": {}, "min_max": {}, "distribution": {}}
    row_count = len(records)
    # Collect all fields
    fields = set()
    for r in records:
        fields.update(r.keys())
    null_rate = {}
    distinct = {}
    min_max = {}
    for f in fields:
        nulls = sum(1 for r in records if r.get(f) is None)
        null_rate[f] = round(nulls / row_count, 3) if row_count else 0
        vals = [r.get(f) for r in records if r.get(f) is not None]
        distinct[f] = len(set(map(str, vals)))
        # min/max where appropriate (numeric)
        try:
            nums = [float(v) for v in vals if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace(".", "", 1).isdigit())]
            if nums:
                min_max[f] = {"min": min(nums), "max": max(nums)}
        except Exception:
            pass
    # Apply privacy: mask sensitive distribution
    return {"row_count": row_count, "null_rate": null_rate, "distinct_count": distinct, "min_max": min_max}
