"""Unified Analytics Platform -- Configuration (Volume 50)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IngestionConfig:
    batch_size: int = 500
    flush_interval_seconds: int = 30
    dedup_window_seconds: int = 300
    late_event_hours: int = 48
    max_event_size_bytes: int = 65536


@dataclass
class AggregationConfig:
    default_granularity: str = "hour"
    retention_raw_days: int = 90
    retention_aggregate_days: int = 365
    retention_cost_days: int = 730
    enable_incremental: bool = True


@dataclass
class CostConfig:
    currency: str = "USD"
    enable_estimation: bool = True
    enable_forecasting: bool = True
    forecast_horizon_days: int = 90
    model_cost_per_1k_input_tokens: float = 0.01
    model_cost_per_1k_output_tokens: float = 0.03


@dataclass
class BudgetConfig:
    warning_threshold: float = 0.8
    soft_limit_threshold: float = 0.95
    hard_limit_threshold: float = 1.0
    enable_auto_enforce: bool = False


@dataclass
class AnomalyConfig:
    sensitivity: float = 2.0
    min_samples: int = 10
    lookback_days: int = 30
    cooldown_hours: int = 4


@dataclass
class ReportConfig:
    max_rows: int = 10000
    cache_ttl_seconds: int = 600
    enable_pdf: bool = True


@dataclass
class QueryConfig:
    max_time_range_days: int = 365
    max_rows: int = 50000
    rate_limit_per_minute: int = 120
    enable_caching: bool = True
    cache_ttl_seconds: int = 300


@dataclass
class AnalyticsConfig:
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    aggregation: AggregationConfig = field(default_factory=AggregationConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    anomaly: AnomalyConfig = field(default_factory=AnomalyConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    query: QueryConfig = field(default_factory=QueryConfig)
    warehouse_backend: str = "postgresql"
