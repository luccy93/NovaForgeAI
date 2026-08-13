"""Data Quality Engine - measurable checks and a deterministic weighted score per table."""
import json, os
from datetime import datetime, timezone
from typing import Optional
from collections import Counter


WEIGHTS = {
    "completeness": 0.15, "accuracy": 0.15, "consistency": 0.10, "validity": 0.10,
    "uniqueness": 0.05, "freshness": 0.10, "integrity": 0.10, "schema_compat": 0.10,
    "duplicates": 0.05, "missing_dimensions": 0.05, "invalid_relationships": 0.05,
}


class DataQualityEngine:
    """Runs deterministic quality checks and computes an overall weighted score."""

    def __init__(self, data_dir: str = ""):
        self.data_dir = data_dir
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)
        self.history: list[dict] = []

    def score_table(self, table: str, rows: list[dict],
                    columns: Optional[list[str]] = None,
                    required_columns: Optional[list[str]] = None,
                    key_column: Optional[str] = None,
                    reference_sets: Optional[dict[str, set]] = None,
                    max_age_hours: Optional[float] = None,
                    last_ingested_at: Optional[str] = None) -> dict:
        """Runs all configured checks and returns per-check scores plus overall score."""
        n = len(rows)
        cols = columns or []
        req = required_columns or cols
        checks = []

        completeness = self._completeness(rows, req)
        checks.append(self._check("completeness", completeness, n - round(completeness * n), n, table))

        accuracy = self._accuracy(rows, cols)
        checks.append(self._check("accuracy", accuracy, 0, n, table))

        consistency = self._consistency(rows, cols)
        checks.append(self._check("consistency", consistency, 0, n, table))

        validity = self._validity(rows, cols)
        checks.append(self._check("validity", validity, 0, n, table))

        uniqueness = self._uniqueness(rows, key_column)
        checks.append(self._check("uniqueness", uniqueness, 0, n, table))

        freshness = self._freshness(last_ingested_at, max_age_hours)
        checks.append(self._check("freshness", freshness, 0, n, table))

        integrity = self._integrity(rows, reference_sets or {})
        checks.append(self._check("integrity", integrity, round((1 - integrity) * n), n, table))

        schema_compat = self._schema_compat(rows, cols)
        checks.append(self._check("schema_compat", schema_compat, 0, n, table))

        dup = self._duplicates(rows)
        checks.append(self._check("duplicates", round(1 - dup / max(1, n), 4), dup, n, table))

        missing = self._missing_dimensions(rows, req)
        checks.append(self._check("missing_dimensions", round(1 - missing / max(1, n), 4), missing, n, table))

        invalid_rel = self._invalid_relationships(rows, reference_sets or {})
        checks.append(self._check("invalid_relationships", round(1 - invalid_rel / max(1, n), 4), invalid_rel, n, table))

        total_weight = sum(WEIGHTS.get(c["name"], 0.05) for c in checks)
        overall = round(sum(c["score"] * WEIGHTS.get(c["name"], 0.05) for c in checks) / max(0.01, total_weight), 4)

        record = {"table": table, "rows": n, "overall_score": overall, "checks": checks,
                  "run_at": datetime.now(timezone.utc).isoformat()}
        self.history.append(record)
        return record

    def _check(self, name: str, score: float, failures: int, samples: int, table: str) -> dict:
        return {"name": name, "score": round(score, 4), "failures": failures,
                "samples": samples, "table": table}

    def _completeness(self, rows: list[dict], req: list[str]) -> float:
        if not req:
            return 1.0
        complete = sum(1 for r in rows if all(r.get(c) not in (None, "") for c in req))
        return round(complete / max(1, len(rows)), 4)

    def _accuracy(self, rows: list[dict], cols: list[str]) -> float:
        if not cols:
            return 1.0
        ok = 0
        for r in rows:
            for c in cols:
                v = r.get(c)
                if v is None or isinstance(v, (int, float, str, bool)):
                    ok += 1
        return round(ok / max(1, len(rows) * len(cols)), 4)

    def _consistency(self, rows: list[dict], cols: list[str]) -> float:
        if not cols or not rows:
            return 1.0
        total, ok = 0, 0
        for r in rows:
            for c in cols:
                v = r.get(c)
                if v is None or isinstance(v, (int, float, bool)) or (isinstance(v, str) and v == v.strip()):
                    ok += 1
                total += 1
        return round(ok / max(1, total), 4)

    def _validity(self, rows: list[dict], cols: list[str]) -> float:
        return self._accuracy(rows, cols)

    def _uniqueness(self, rows: list[dict], key: Optional[str]) -> float:
        if not key or not rows:
            return 1.0
        keys = [r.get(key) for r in rows]
        return round(len(set(keys)) / max(1, len(keys)), 4)

    def _freshness(self, last_ingested_at, max_age_hours: Optional[int]) -> float:
        if not last_ingested_at or not max_age_hours:
            return 1.0
        try:
            last = datetime.fromisoformat(last_ingested_at)
        except (ValueError, TypeError):
            return 0.0
        age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        return round(max(0.0, 1.0 - age_h / max_age_h), 4)

    def _integrity(self, rows: list[dict], refs: dict[str, set]) -> float:
        if not refs:
            return 1.0
        ok = 0
        total = 0
        for r in rows:
            for col, allowed in refs.items():
                v = r.get(col)
                if v is None:
                    ok += 1
                elif v in allowed:
                    ok += 1
                total += 1
        return round(ok / max(1, total), 4)

    def _schema_compat(self, rows: list[dict], cols: list[str]) -> float:
        if not cols or not rows:
            return 1.0
        present = sum(1 for r in rows for c in cols if c in r)
        return round(present / max(1, len(rows) * len(cols)), 4)

    def _duplicates(self, rows: list[dict]) -> int:
        seen = set()
        dup = 0
        for r in rows:
            key = json.dumps(r, sort_keys=True, default=str)
            if key in seen:
                dup += 1
            else:
                seen.add(key)
        return dup

    def _missing_dimensions(self, rows: list[dict], req: list[str]) -> int:
        if not req:
            return 0
        return sum(1 for r in rows if any(r.get(c) in (None, "") for c in req))

    def _invalid_relationships(self, rows: list[dict], refs: dict[str, set]) -> int:
        count = 0
        for r in rows:
            for col, allowed in refs.items():
                v = r.get(col)
                if v is not None and v not in allowed:
                    count += 1
        return count

    def latest(self, table: str) -> Optional[dict]:
        for rec in reversed(self.history):
            if rec["table"] == table:
                return rec
        return None

    def series(self, table: str, limit: int = 100) -> list[dict]:
        return [{"run_at": rec["run_at"], "score": rec["overall_score"]}
                for rec in self.history if rec["table"] == table][-limit:]

    def health(self) -> dict:
        if not self.history:
            return {"runs": 0, "latest_score": None}
        last = self.history[-1]
        return {"runs": len(self.history), "latest_table": last["table"],
                "latest_score": last["overall_score"]}