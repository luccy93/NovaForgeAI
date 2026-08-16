"""Data Quality module for NovaForge Data Platform & Knowledge Fabric."""
import json, uuid, os, logging, re, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class QualityDimension(Enum):
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    FRESHNESS = "freshness"
    VALIDITY = "validity"
    UNIQUENESS = "uniqueness"
    INTEGRITY = "integrity"
    TIMELINESS = "timeliness"
    CONFORMITY = "conformity"


class QualitySeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class QualityStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"
    SKIPPED = "skipped"


class QualityRuleType(Enum):
    SCHEMA_VALIDATION = "schema_validation"
    RANGE_CHECK = "range_check"
    PATTERN_MATCH = "pattern_match"
    REFERENTIAL_INTEGRITY = "referential_integrity"
    UNIQUE_CHECK = "unique_check"
    NOT_NULL = "not_null"
    CUSTOM_SQL = "custom_sql"
    FRESHNESS_CHECK = "freshness_check"
    CROSS_FIELD_VALIDATION = "cross_field_validation"
    STATISTICAL_OUTLIER = "statistical_outlier"


@dataclass
class QualityRule:
    id: str
    org_id: str
    name: str
    description: str = ""
    dimension: QualityDimension = QualityDimension.COMPLETENESS
    rule_type: QualityRuleType = QualityRuleType.NOT_NULL
    severity: QualitySeverity = QualitySeverity.MEDIUM
    target_entity: str = ""
    target_field: str = ""
    threshold: float = 0.0
    expression: str = ""
    params: dict = field(default_factory=dict)
    enabled: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dimension"] = self.dimension.value
        d["rule_type"] = self.rule_type.value
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityRule":
        data = data.copy()
        data["dimension"] = QualityDimension(data.get("dimension", "completeness"))
        data["rule_type"] = QualityRuleType(data.get("rule_type", "not_null"))
        data["severity"] = QualitySeverity(data.get("severity", "medium"))
        return cls(**data)


@dataclass
class QualityCheckExecution:
    id: str
    rule_id: str
    org_id: str
    status: QualityStatus = QualityStatus.PASS
    score: float = 1.0
    records_scanned: int = 0
    records_passed: int = 0
    records_failed: int = 0
    execution_time_ms: float = 0.0
    error_message: str = ""
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    triggered_by: str = "manual"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityCheckExecution":
        data = data.copy()
        data["status"] = QualityStatus(data.get("status", "pass"))
        return cls(**data)


@dataclass
class QualityReport:
    id: str
    org_id: str
    name: str = ""
    dimension: QualityDimension = QualityDimension.COMPLETENESS
    period_start: str = ""
    period_end: str = ""
    overall_score: float = 1.0
    by_rule: list = field(default_factory=list)
    by_entity: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dimension"] = self.dimension.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityReport":
        data = data.copy()
        data["dimension"] = QualityDimension(data.get("dimension", "completeness"))
        return cls(**data)


@dataclass
class QualityScorecard:
    id: str
    org_id: str
    overall_score: float = 1.0
    by_dimension: dict = field(default_factory=dict)
    by_entity: dict = field(default_factory=dict)
    trend_direction: str = "stable"
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "QualityScorecard":
        return cls(**data)


@dataclass
class QualityAnomaly:
    id: str
    org_id: str
    rule_id: str
    entity: str = ""
    field_name: str = ""
    expected_value: Any = None
    actual_value: Any = None
    deviation: float = 0.0
    severity: QualitySeverity = QualitySeverity.MEDIUM
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "open"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityAnomaly":
        data = data.copy()
        data["severity"] = QualitySeverity(data.get("severity", "medium"))
        return cls(**data)


class DataQuality:
    def __init__(self, storage_dir: str = "data_quality_data"):
        self.storage_dir = storage_dir
        self._rules: dict[str, QualityRule] = {}
        self._executions: dict[str, QualityCheckExecution] = {}
        self._reports: dict[str, QualityReport] = {}
        self._scorecards: dict[str, QualityScorecard] = {}
        self._anomalies: dict[str, QualityAnomaly] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rules_path(self) -> str:
        return os.path.join(self.storage_dir, "rules.json")

    def _executions_path(self) -> str:
        return os.path.join(self.storage_dir, "executions.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _scorecards_path(self) -> str:
        return os.path.join(self.storage_dir, "scorecards.json")

    def _anomalies_path(self) -> str:
        return os.path.join(self.storage_dir, "anomalies.json")

    def _save(self) -> None:
        try:
            with open(self._rules_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._rules.items()}, f, indent=2, default=str)
            with open(self._executions_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._executions.items()}, f, indent=2, default=str)
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
            with open(self._scorecards_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._scorecards.items()}, f, indent=2, default=str)
            with open(self._anomalies_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._anomalies.items()}, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save data quality data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            for path, store, cls in [
                (self._rules_path(), self._rules, QualityRule),
                (self._executions_path(), self._executions, QualityCheckExecution),
                (self._reports_path(), self._reports, QualityReport),
                (self._scorecards_path(), self._scorecards, QualityScorecard),
                (self._anomalies_path(), self._anomalies, QualityAnomaly),
            ]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try:
                            store[k] = cls.from_dict(v)
                        except Exception as e:
                            logger.warning("Skipping malformed entry %s: %s", k, e)
        except Exception as e:
            logger.error("Failed to load data quality data: %s", e, exc_info=True)

    def create_rule(self, rule: QualityRule) -> QualityRule:
        self._telemetry["create_rule_calls"] += 1
        self._rules[rule.id] = rule
        self._save()
        logger.info("Created quality rule: %s", rule.name)
        return rule

    def update_rule(self, rule_id: str, updates: dict) -> Optional[QualityRule]:
        self._telemetry["update_rule_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            return None
        for key, value in updates.items():
            if hasattr(rule, key) and key not in ("id", "created_at"):
                if key in ("dimension",):
                    setattr(rule, key, QualityDimension(value) if isinstance(value, str) else value)
                elif key in ("rule_type",):
                    setattr(rule, key, QualityRuleType(value) if isinstance(value, str) else value)
                elif key in ("severity",):
                    setattr(rule, key, QualitySeverity(value) if isinstance(value, str) else value)
                else:
                    setattr(rule, key, value)
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return rule

    def list_rules(self, org_id: str, dimension: Optional[QualityDimension] = None, enabled: Optional[bool] = None) -> list[QualityRule]:
        self._telemetry["list_rules_calls"] += 1
        results = [r for r in self._rules.values() if r.org_id == org_id]
        if dimension:
            results = [r for r in results if r.dimension == dimension]
        if enabled is not None:
            results = [r for r in results if r.enabled == enabled]
        return results

    def execute_rule(self, rule_id: str, data: list[dict]) -> QualityCheckExecution:
        self._telemetry["execute_rule_calls"] += 1
        start = time.time()
        rule = self._rules.get(rule_id)
        if not rule:
            return QualityCheckExecution(id=str(uuid.uuid4()), rule_id=rule_id, org_id="", status=QualityStatus.ERROR, error_message="Rule not found")

        records_scanned = len(data)
        records_passed = 0
        records_failed = 0
        errors = []

        for record in data:
            value = record.get(rule.target_field)
            if rule.rule_type == QualityRuleType.NOT_NULL:
                if value is not None and value != "":
                    records_passed += 1
                else:
                    records_failed += 1
                    errors.append(f"{rule.target_field} is null")
            elif rule.rule_type == QualityRuleType.RANGE_CHECK:
                try:
                    threshold = rule.threshold
                    expr = rule.expression
                    fv = float(value) if value is not None else None
                    if fv is None:
                        records_failed += 1
                        errors.append(f"{rule.target_field}={value} is None")
                    elif ">" in expr and fv > threshold:
                        records_passed += 1
                    elif "<" in expr and fv < threshold:
                        records_passed += 1
                    elif ">=" in expr and fv >= threshold:
                        records_passed += 1
                    elif "<=" in expr and fv <= threshold:
                        records_passed += 1
                    elif "==" in expr and fv == threshold:
                        records_passed += 1
                    else:
                        records_failed += 1
                        errors.append(f"{rule.target_field}={fv} fails {expr} {threshold}")
                except (ValueError, TypeError):
                    records_failed += 1
                    errors.append(f"{rule.target_field}={value} not numeric")
            elif rule.rule_type == QualityRuleType.PATTERN_MATCH:
                pattern = rule.expression or rule.params.get("pattern", "")
                if pattern and re.search(pattern, str(value or "")):
                    records_passed += 1
                else:
                    records_failed += 1
                    errors.append(f"{rule.target_field}='{value}' doesn't match '{pattern}'")
            elif rule.rule_type == QualityRuleType.UNIQUE_CHECK:
                seen = set()
                val = str(value)
                if val in seen:
                    records_failed += 1
                    errors.append(f"{rule.target_field}='{val}' is duplicate")
                else:
                    seen.add(val)
                    records_passed += 1
            elif rule.rule_type == QualityRuleType.SCHEMA_VALIDATION:
                required = rule.params.get("required_fields", [])
                missing = [f for f in required if f not in record]
                if not missing:
                    records_passed += 1
                else:
                    records_failed += 1
                    errors.append(f"Missing fields: {missing}")
            else:
                records_passed += 1

        elapsed = (time.time() - start) * 1000
        score = records_passed / max(records_scanned, 1)
        status = QualityStatus.PASS if score >= (rule.threshold or 0.8) else QualityStatus.FAIL

        execution = QualityCheckExecution(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            org_id=rule.org_id,
            status=status,
            score=round(score, 4),
            records_scanned=records_scanned,
            records_passed=records_passed,
            records_failed=records_failed,
            execution_time_ms=round(elapsed, 2),
            error_message="; ".join(errors[:10]),
        )
        self._executions[execution.id] = execution
        self._save()
        return execution

    def run_quality_check(self, org_id: str, data: list[dict]) -> list[QualityCheckExecution]:
        self._telemetry["run_quality_check_calls"] += 1
        rules = self.list_rules(org_id, enabled=True)
        results = []
        for rule in rules:
            result = self.execute_rule(rule.id, data)
            results.append(result)
        return results

    def generate_report(self, org_id: str, start_date: str, end_date: str) -> QualityReport:
        self._telemetry["generate_report_calls"] += 1
        rules = self.list_rules(org_id)
        executions = [e for e in self._executions.values() if e.org_id == org_id]
        by_entity = defaultdict(lambda: {"passed": 0, "failed": 0, "total": 0})
        findings = []
        recommendations = []
        total_score = 0.0

        for e in executions:
            rule = self._rules.get(e.rule_id)
            entity = rule.target_entity if rule else "unknown"
            by_entity[entity]["passed"] += e.records_passed
            by_entity[entity]["failed"] += e.records_failed
            by_entity[entity]["total"] += e.records_scanned
            if e.status in (QualityStatus.FAIL, QualityStatus.WARN):
                findings.append(f"Rule {e.rule_id}: {e.records_failed} failures, {e.error_message}")
            total_score += e.score

        avg_score = round(total_score / max(len(executions), 1), 4)
        if avg_score < 0.8:
            recommendations.append("Increase data validation coverage")
        if any(v["failed"] > 0 for v in by_entity.values()):
            recommendations.append("Review failed records and fix data quality issues")

        report = QualityReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name=f"Quality Report {start_date} to {end_date}",
            overall_score=avg_score,
            by_rule=[e.to_dict() for e in executions[:20]],
            by_entity=dict(by_entity),
            findings=findings[:10],
            recommendations=recommendations,
            period_start=start_date,
            period_end=end_date,
        )
        self._reports[report.id] = report
        self._save()
        return report

    def get_scorecard(self, org_id: str) -> QualityScorecard:
        self._telemetry["get_scorecard_calls"] += 1
        rules = self.list_rules(org_id)
        by_dim = defaultdict(list)
        for r in rules:
            by_dim[r.dimension.value].append(r)

        by_dim_scores = {}
        total = 0.0
        count = 0
        for dim, dim_rules in by_dim.items():
            dim_scores = []
            for r in dim_rules:
                exes = [e for e in self._executions.values() if e.rule_id == r.id]
                if exes:
                    dim_scores.append(max(e.score for e in exes))
            if dim_scores:
                by_dim_scores[dim] = round(sum(dim_scores) / len(dim_scores), 4)
                total += by_dim_scores[dim]
                count += 1

        overall = round(total / max(count, 1), 4)

        scorecard = QualityScorecard(
            id=str(uuid.uuid4()),
            org_id=org_id,
            overall_score=overall,
            by_dimension=by_dim_scores,
            last_updated=datetime.now(timezone.utc).isoformat(),
        )
        self._scorecards[scorecard.id] = scorecard
        self._save()
        return scorecard

    def detect_anomaly(self, rule_id: str, current_value: Any) -> Optional[QualityAnomaly]:
        self._telemetry["detect_anomaly_calls"] += 1
        rule = self._rules.get(rule_id)
        if not rule:
            return None
        executions = [e for e in self._executions.values() if e.rule_id == rule_id]
        if not executions:
            return None
        avg_score = sum(e.score for e in executions) / len(executions)
        deviation = abs(current_value - avg_score) if isinstance(current_value, (int, float)) else 0.0
        if deviation > (rule.threshold or 0.2):
            anomaly = QualityAnomaly(
                id=str(uuid.uuid4()),
                org_id=rule.org_id,
                rule_id=rule_id,
                entity=rule.target_entity,
                field=rule.target_field,
                expected_value=avg_score,
                actual_value=current_value,
                deviation=round(deviation, 4),
                severity=rule.severity,
            )
            self._anomalies[anomaly.id] = anomaly
            self._save()
            return anomaly
        return None

    def get_quality_trends(self, org_id: str, days: int = 90) -> list[dict]:
        self._telemetry["get_quality_trends_calls"] += 1
        executions = [e for e in self._executions.values() if e.org_id == org_id]
        daily = defaultdict(list)
        for e in executions:
            day = e.executed_at[:10] if e.executed_at else "unknown"
            daily[day].append(e.score)
        trends = []
        for day in sorted(daily.keys(), reverse=True)[:days]:
            scores = daily[day]
            trends.append({"date": day, "avg_score": round(sum(scores) / len(scores), 4), "checks": len(scores)})
        return trends

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
