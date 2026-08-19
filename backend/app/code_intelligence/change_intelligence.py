"""Change Intelligence module for the code intelligence engine.

Analyses git history to detect hotspots, change frequency, churn metrics,
high-risk areas, author activity, change bursts, file timelines, and stale
files.  Built on top of the CodeHistory model populated by the git ingestion
pipeline.
"""

import logging
import math
import uuid as _uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeFile,
    CodeHistory,
    CodeIndex,
    CodeMetrics,
    CodeSymbol,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

STALE_DEFAULT_DAYS = 90
CHANGE_BURST_DEFAULT_WINDOW_DAYS = 7
CHANGE_BURST_DEFAULT_THRESHOLD = 3.0


# ── Dataclasses ──────────────────────────────────────────────────────────


@dataclass
class HotspotItem:
    """A file identified as a change hotspot."""

    file_path: str
    file_id: Optional[str]
    change_count: int
    unique_authors: int
    lines_added: int
    lines_deleted: int
    first_change: Optional[datetime]
    last_change: Optional[datetime]
    hotspot_score: float = 0.0


@dataclass
class ChangeFrequencyItem:
    """Change frequency information for a single file."""

    file_path: str
    file_id: Optional[str]
    total_changes: int
    days_in_window: int
    changes_per_day: float
    weekly_average: float
    monthly_average: float


@dataclass
class RecentModification:
    """A file that was recently modified."""

    file_path: str
    file_id: Optional[str]
    last_modified: datetime
    commit_sha: str
    author_name: Optional[str]
    author_email: Optional[str]
    lines_added: int
    lines_deleted: int
    change_type: Optional[str]
    message: Optional[str]


@dataclass
class ChurnMetrics:
    """Aggregate churn metrics for a repository."""

    repository_id: str
    total_lines_added: int
    total_lines_deleted: int
    total_lines_changed: int
    net_lines_changed: int
    commit_count: int
    unique_authors: int
    files_changed: int
    avg_lines_per_commit: float
    churn_ratio: float
    period_days: int
    daily_avg_added: float
    daily_avg_deleted: float


@dataclass
class HighRiskArea:
    """A file with both high churn and high complexity."""

    file_path: str
    file_id: Optional[str]
    change_count: int
    lines_added: int
    lines_deleted: int
    total_lines_changed: int
    cyclomatic_complexity: Optional[int]
    cognitive_complexity: Optional[int]
    maintainability_index: Optional[float]
    nesting_depth: Optional[int]
    risk_score: float
    risk_level: str
    unique_authors: int
    last_change: Optional[datetime]


@dataclass
class AuthorActivity:
    """Activity statistics for a single author."""

    author_email: Optional[str]
    author_name: Optional[str]
    total_commits: int
    files_changed: int
    lines_added: int
    lines_deleted: int
    lines_changed: int
    first_commit: Optional[datetime]
    last_commit: Optional[datetime]
    avg_lines_per_commit: float
    top_files: list[dict]
    active_days: int


@dataclass
class CollaborationPair:
    """Collaboration information for a pair of authors."""

    author_a: str
    author_b: str
    shared_files: int
    total_overlapping_changes: int


@dataclass
class ChangeBurst:
    """A detected burst of unusual activity."""

    file_path: str
    file_id: Optional[str]
    burst_start: datetime
    burst_end: datetime
    burst_changes: int
    baseline_avg: float
    spike_ratio: float
    involved_authors: list[str]


@dataclass
class FileTimelineEntry:
    """A single change event in a file's timeline."""

    commit_sha: str
    commit_date: Optional[datetime]
    author_name: Optional[str]
    author_email: Optional[str]
    change_type: Optional[str]
    lines_added: int
    lines_deleted: int
    message: Optional[str]


@dataclass
class FileTimeline:
    """Complete timeline for a specific file."""

    file_path: str
    file_id: Optional[str]
    total_commits: int
    entries: list[FileTimelineEntry]
    period_days: int


@dataclass
class StaleFile:
    """A file that has not been changed recently."""

    file_path: str
    file_id: Optional[str]
    last_changed: Optional[datetime]
    days_since_change: Optional[int]
    total_historical_changes: int
    primary_author: Optional[str]


@dataclass
class ChangeSummary:
    """Aggregate change statistics for the repository."""

    repository_id: str
    total_commits: int
    total_files_ever_changed: int
    unique_authors: int
    total_lines_added: int
    total_lines_deleted: int
    total_lines_changed: int
    period_days: int
    first_commit: Optional[datetime]
    last_commit: Optional[datetime]
    avg_commits_per_day: float
    top_hotspots: list[HotspotItem]
    top_contributors: list[AuthorActivity]
    recent_modifications_count: int
    stale_files_count: int
    high_risk_count: int
    overall_churn_ratio: float


# ── Risk thresholds ──────────────────────────────────────────────────────

RISK_LOW = 0.3
RISK_MEDIUM = 0.6
RISK_HIGH = 0.85


def _risk_level(score: float) -> str:
    """Map a 0-1 risk score to a human-readable level."""
    if score < RISK_LOW:
        return "LOW"
    if score < RISK_MEDIUM:
        return "MEDIUM"
    if score < RISK_HIGH:
        return "HIGH"
    return "CRITICAL"


# ── ChangeAnalyzer ───────────────────────────────────────────────────────


class ChangeAnalyzer:
    """Main change intelligence analyzer.

    Provides methods to detect hotspots, calculate change frequency, find
    recent modifications, compute churn metrics, identify high-risk areas,
    track author activity, detect change bursts, retrieve file timelines,
    and find stale files.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self._db = db_session

    # ── Hotspot detection ───────────────────────────────────────────────

    async def detect_hotspots(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        top_n: int = 20,
    ) -> list[HotspotItem]:
        """Detect the most frequently changed files in the repository.

        Scores files by a weighted combination of change count, unique
        authors, and total churn.
        """
        logger.info(
            "Detecting top %d hotspots for repository %s", top_n, repository_id,
        )

        stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.file_id,
                func.count().label("change_count"),
                func.count(func.distinct(CodeHistory.author_email)).label(
                    "unique_authors"
                ),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "lines_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "lines_deleted"
                ),
                func.min(CodeHistory.commit_date).label("first_change"),
                func.max(CodeHistory.commit_date).label("last_change"),
            )
            .where(CodeHistory.repository_id == repository_id)
            .group_by(CodeHistory.file_path, CodeHistory.file_id)
            .order_by(desc("change_count"))
            .limit(top_n)
        )

        result = await db.execute(stmt)
        rows = result.all()

        items: list[HotspotItem] = []
        for row in rows:
            change_count = row.change_count
            unique_authors = row.unique_authors
            total_churn = row.lines_added + row.lines_deleted

            # Weighted score: 50% frequency, 25% author diversity, 25% churn
            freq_score = min(change_count / max(top_n, 1), 1.0)
            author_score = min(unique_authors / 10.0, 1.0)
            churn_score = min(total_churn / 5000.0, 1.0)
            hotspot_score = round(
                0.50 * freq_score + 0.25 * author_score + 0.25 * churn_score,
                4,
            )

            items.append(
                HotspotItem(
                    file_path=row.file_path,
                    file_id=str(row.file_id) if row.file_id else None,
                    change_count=change_count,
                    unique_authors=unique_authors,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                    first_change=row.first_change,
                    last_change=row.last_change,
                    hotspot_score=hotspot_score,
                )
            )

        items.sort(key=lambda h: h.hotspot_score, reverse=True)
        logger.info("Found %d hotspots", len(items))
        return items

    # ── Change frequency ────────────────────────────────────────────────

    async def get_change_frequency(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        days: int = 90,
    ) -> list[ChangeFrequencyItem]:
        """Calculate change frequency per file over the given time window.

        Returns files sorted by daily average (descending).
        """
        logger.info(
            "Calculating change frequency for repository %s over %d days",
            repository_id,
            days,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.file_id,
                func.count().label("total_changes"),
                func.min(CodeHistory.commit_date).label("first_change_in_window"),
                func.max(CodeHistory.commit_date).label("last_change_in_window"),
            )
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.commit_date >= cutoff,
            )
            .group_by(CodeHistory.file_path, CodeHistory.file_id)
            .order_by(desc("total_changes"))
        )

        result = await db.execute(stmt)
        rows = result.all()

        items: list[ChangeFrequencyItem] = []
        for row in rows:
            total_changes = row.total_changes
            first_in = row.first_change_in_window
            last_in = row.last_change_in_window

            if first_in and last_in:
                span = (last_in - first_in).days + 1
                days_in_window = min(span, days)
            else:
                days_in_window = days

            changes_per_day = (
                round(total_changes / max(days_in_window, 1), 4)
            )
            weekly_average = round(changes_per_day * 7, 2)
            monthly_average = round(changes_per_day * 30, 2)

            items.append(
                ChangeFrequencyItem(
                    file_path=row.file_path,
                    file_id=str(row.file_id) if row.file_id else None,
                    total_changes=total_changes,
                    days_in_window=days_in_window,
                    changes_per_day=changes_per_day,
                    weekly_average=weekly_average,
                    monthly_average=monthly_average,
                )
            )

        items.sort(key=lambda f: f.changes_per_day, reverse=True)
        logger.info(
            "Calculated change frequency for %d files", len(items),
        )
        return items

    # ── Recent modifications ────────────────────────────────────────────

    async def get_recent_modifications(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        days: int = 30,
    ) -> list[RecentModification]:
        """Return files modified in the last N days, most recent first."""
        logger.info(
            "Finding recent modifications for repository %s in last %d days",
            repository_id,
            days,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Subquery to get the latest commit per file
        latest_commit_subq = (
            select(
                CodeHistory.file_path,
                func.max(CodeHistory.commit_date).label("latest_date"),
            )
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.commit_date >= cutoff,
            )
            .group_by(CodeHistory.file_path)
            .subquery()
        )

        stmt = (
            select(CodeHistory)
            .join(
                latest_commit_subq,
                and_(
                    CodeHistory.file_path == latest_commit_subq.c.file_path,
                    CodeHistory.commit_date == latest_commit_subq.c.latest_date,
                ),
            )
            .where(CodeHistory.repository_id == repository_id)
            .order_by(desc(CodeHistory.commit_date))
        )

        result = await db.execute(stmt)
        rows = result.scalars().all()

        modifications: list[RecentModification] = []
        seen_files: set[str] = set()
        for row in rows:
            if row.file_path in seen_files:
                continue
            seen_files.add(row.file_path)

            modifications.append(
                RecentModification(
                    file_path=row.file_path,
                    file_id=str(row.file_id) if row.file_id else None,
                    last_modified=row.commit_date or datetime.now(timezone.utc),
                    commit_sha=row.commit_sha,
                    author_name=row.author_name,
                    author_email=row.author_email,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                    change_type=row.change_type,
                    message=row.message,
                )
            )

        logger.info("Found %d recently modified files", len(modifications))
        return modifications

    # ── Churn metrics ───────────────────────────────────────────────────

    async def compute_churn_metrics(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
    ) -> ChurnMetrics:
        """Compute aggregate churn metrics for the repository's full history.

        Churn ratio is defined as (lines_deleted / lines_added) — higher values
        indicate more rework.
        """
        logger.info("Computing churn metrics for repository %s", repository_id)

        stats_stmt = (
            select(
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "total_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "total_deleted"
                ),
                func.count().label("commit_count"),
                func.count(func.distinct(CodeHistory.author_email)).label(
                    "unique_authors"
                ),
                func.count(func.distinct(CodeHistory.file_path)).label(
                    "files_changed"
                ),
                func.min(CodeHistory.commit_date).label("first_commit"),
                func.max(CodeHistory.commit_date).label("last_commit"),
            ).where(CodeHistory.repository_id == repository_id)
        )

        result = await db.execute(stats_stmt)
        row = result.one()

        total_added = row.total_added
        total_deleted = row.total_deleted
        total_changed = total_added + total_deleted
        net_changed = total_added - total_deleted
        commit_count = row.commit_count

        first = row.first_commit
        last = row.last_commit
        if first and last:
            period_days = max((last - first).days + 1, 1)
        else:
            period_days = 1

        avg_per_commit = (
            round(total_changed / max(commit_count, 1), 2)
        )
        churn_ratio = (
            round(total_deleted / max(total_added, 1), 4)
        )
        daily_avg_added = round(total_added / max(period_days, 1), 2)
        daily_avg_deleted = round(total_deleted / max(period_days, 1), 2)

        return ChurnMetrics(
            repository_id=str(repository_id),
            total_lines_added=total_added,
            total_lines_deleted=total_deleted,
            total_lines_changed=total_changed,
            net_lines_changed=net_changed,
            commit_count=commit_count,
            unique_authors=row.unique_authors,
            files_changed=row.files_changed,
            avg_lines_per_commit=avg_per_commit,
            churn_ratio=churn_ratio,
            period_days=period_days,
            daily_avg_added=daily_avg_added,
            daily_avg_deleted=daily_avg_deleted,
        )

    # ── High-risk area identification ───────────────────────────────────

    async def identify_high_risk_areas(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
    ) -> list[HighRiskArea]:
        """Identify files with both high churn and high complexity.

        A risk score is computed from the file's change frequency, lines
        changed, cyclomatic complexity, and maintainability index.
        """
        logger.info(
            "Identifying high-risk areas for repository %s", repository_id,
        )

        # Step 1: Get per-file churn stats
        churn_stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.file_id,
                func.count().label("change_count"),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "lines_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "lines_deleted"
                ),
                func.max(CodeHistory.commit_date).label("last_change"),
                func.count(func.distinct(CodeHistory.author_email)).label(
                    "unique_authors"
                ),
            )
            .where(CodeHistory.repository_id == repository_id)
            .group_by(CodeHistory.file_path, CodeHistory.file_id)
        )

        churn_result = await db.execute(churn_stmt)
        churn_rows = churn_result.all()

        if not churn_rows:
            return []

        # Compute percentile thresholds for scoring
        change_counts = [r.change_count for r in churn_rows]
        max_changes = max(change_counts) if change_counts else 1

        # Step 2: Load metrics for all files in the repository
        metrics_stmt = select(CodeMetrics).where(
            CodeMetrics.repository_id == repository_id,
            CodeMetrics.symbol_id.is_(None),
        )
        metrics_result = await db.execute(metrics_stmt)
        metrics_map: dict[_uuid.UUID, CodeMetrics] = {}
        for m in metrics_result.scalars().all():
            metrics_map[m.file_id] = m

        high_risk: list[HighRiskArea] = []
        for churn_row in churn_rows:
            total_lines_changed = churn_row.lines_added + churn_row.lines_deleted
            file_id = churn_row.file_id
            metrics = metrics_map.get(file_id) if file_id else None

            # Churn factor: normalized change count
            churn_factor = churn_row.change_count / max(max_changes, 1)

            # Volume factor: normalized total lines changed
            volume_factor = min(total_lines_changed / 5000.0, 1.0)

            # Complexity factor from metrics
            complexity_factor = 0.0
            cc: Optional[int] = None
            cog: Optional[int] = None
            mi: Optional[float] = None
            nd: Optional[int] = None
            if metrics:
                cc = metrics.cyclomatic_complexity
                cog = metrics.cognitive_complexity
                mi = metrics.maintainability_index
                nd = metrics.nesting_depth
                cc_val = cc or 0
                cog_val = cog or 0
                nd_val = nd or 0
                mi_val = mi if mi is not None else 100.0

                # Higher complexity => higher factor
                cc_factor = min(cc_val / 30.0, 1.0)
                cog_factor = min(cog_val / 30.0, 1.0)
                nd_factor = min(nd_val / 8.0, 1.0)
                # Lower maintainability => higher factor
                mi_factor = max(1.0 - (mi_val / 100.0), 0.0)

                complexity_factor = (
                    0.35 * cc_factor
                    + 0.25 * cog_factor
                    + 0.20 * nd_factor
                    + 0.20 * mi_factor
                )

            # Author diversity factor (more authors => higher risk)
            author_factor = min(churn_row.unique_authors / 10.0, 1.0)

            # Combined risk score
            risk_score = round(
                0.35 * churn_factor
                + 0.25 * volume_factor
                + 0.25 * complexity_factor
                + 0.15 * author_factor,
                4,
            )

            high_risk.append(
                HighRiskArea(
                    file_path=churn_row.file_path,
                    file_id=str(file_id) if file_id else None,
                    change_count=churn_row.change_count,
                    lines_added=churn_row.lines_added,
                    lines_deleted=churn_row.lines_deleted,
                    total_lines_changed=total_lines_changed,
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    maintainability_index=mi,
                    nesting_depth=nd,
                    risk_score=risk_score,
                    risk_level=_risk_level(risk_score),
                    unique_authors=churn_row.unique_authors,
                    last_change=churn_row.last_change,
                )
            )

        high_risk.sort(key=lambda h: h.risk_score, reverse=True)
        logger.info(
            "Identified %d high-risk files", len(high_risk),
        )
        return high_risk

    # ── Author activity ─────────────────────────────────────────────────

    async def get_author_activity(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
    ) -> list[AuthorActivity]:
        """Return per-author activity statistics for the repository.

        Includes per-author top files, active days, and collaboration
        awareness (see ``get_collaboration_pairs``).
        """
        logger.info(
            "Computing author activity for repository %s", repository_id,
        )

        author_stmt = (
            select(
                CodeHistory.author_email,
                CodeHistory.author_name,
                func.count().label("total_commits"),
                func.count(func.distinct(CodeHistory.file_path)).label(
                    "files_changed"
                ),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "lines_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "lines_deleted"
                ),
                func.min(CodeHistory.commit_date).label("first_commit"),
                func.max(CodeHistory.commit_date).label("last_commit"),
            )
            .where(CodeHistory.repository_id == repository_id)
            .group_by(CodeHistory.author_email, CodeHistory.author_name)
            .order_by(desc("total_commits"))
        )

        result = await db.execute(author_stmt)
        author_rows = result.all()

        activities: list[AuthorActivity] = []
        for row in author_rows:
            total_lines = row.lines_added + row.lines_deleted
            avg_per_commit = round(
                total_lines / max(row.total_commits, 1), 2,
            )

            # Top files for this author
            top_files = await self._get_author_top_files(
                repository_id, row.author_email, db, limit=10,
            )

            # Active days count
            active_days = await self._count_active_days(
                repository_id, row.author_email, db,
            )

            activities.append(
                AuthorActivity(
                    author_email=row.author_email,
                    author_name=row.author_name,
                    total_commits=row.total_commits,
                    files_changed=row.files_changed,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                    lines_changed=total_lines,
                    first_commit=row.first_commit,
                    last_commit=row.last_commit,
                    avg_lines_per_commit=avg_per_commit,
                    top_files=top_files,
                    active_days=active_days,
                )
            )

        logger.info("Computed activity for %d authors", len(activities))
        return activities

    async def get_collaboration_pairs(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        top_n: int = 20,
    ) -> list[CollaborationPair]:
        """Find pairs of authors who frequently change the same files."""
        logger.info(
            "Detecting collaboration pairs for repository %s", repository_id,
        )

        # Get per-file author sets
        file_authors_stmt = (
            select(
                CodeHistory.file_path,
                func.group_concat(func.distinct(CodeHistory.author_email)).label(
                    "authors_str"
                ),
            )
            .where(CodeHistory.repository_id == repository_id)
            .group_by(CodeHistory.file_path)
        )

        result = await db.execute(file_authors_stmt)
        rows = result.all()

        # Build file->authors mapping
        file_authors: dict[str, set[str]] = {}
        for row in rows:
            if row.authors_str:
                authors = {a.strip() for a in row.authors_str.split(",") if a.strip()}
                file_authors[row.file_path] = authors

        # Count shared files per author pair
        pair_counts: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"shared_files": 0, "total_changes": 0}
        )

        for file_path, authors in file_authors.items():
            author_list = sorted(authors)
            for i, a in enumerate(author_list):
                for b in author_list[i + 1 :]:
                    pair_counts[(a, b)]["shared_files"] += 1

        # Count overlapping changes for each pair
        all_history_stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.author_email,
            )
            .where(CodeHistory.repository_id == repository_id)
        )
        hist_result = await db.execute(all_history_stmt)
        hist_rows = hist_result.all()

        file_by_author: dict[str, set[str]] = defaultdict(set)
        for h_row in hist_rows:
            file_by_author[h_row.author_email].add(h_row.file_path)

        pairs: list[CollaborationPair] = []
        for (a, b), counts in pair_counts.items():
            shared_files = file_by_author.get(a, set()) & file_by_author.get(
                b, set()
            )
            pairs.append(
                CollaborationPair(
                    author_a=a,
                    author_b=b,
                    shared_files=counts["shared_files"],
                    total_overlapping_changes=len(shared_files),
                )
            )

        pairs.sort(key=lambda p: p.shared_files, reverse=True)
        pairs = pairs[:top_n]
        logger.info("Found %d collaboration pairs", len(pairs))
        return pairs

    # ── Change burst detection ──────────────────────────────────────────

    async def detect_change_bursts(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        window_days: int = CHANGE_BURST_DEFAULT_WINDOW_DAYS,
        threshold: float = CHANGE_BURST_DEFAULT_THRESHOLD,
    ) -> list[ChangeBurst]:
        """Detect unusual spikes in change activity.

        Uses a sliding window approach: for each file, if the number of
        changes in a window exceeds ``threshold`` times the file's average
        changes per window, it is flagged as a burst.
        """
        logger.info(
            "Detecting change bursts for repository %s "
            "(window=%d days, threshold=%.1f)",
            repository_id,
            window_days,
            threshold,
        )

        now = datetime.now(timezone.utc)

        # Get all changes ordered by date
        all_stmt = (
            select(CodeHistory)
            .where(CodeHistory.repository_id == repository_id)
            .order_by(desc(CodeHistory.commit_date))
        )

        result = await db.execute(all_stmt)
        all_changes = result.scalars().all()

        if not all_changes:
            return []

        # Group changes by file
        file_changes: dict[str, list[CodeHistory]] = defaultdict(list)
        for change in all_changes:
            file_changes[change.file_path].append(change)

        bursts: list[ChangeBurst] = []

        for file_path, changes in file_changes.items():
            if len(changes) < 3:
                continue

            dates = [
                c.commit_date for c in changes if c.commit_date is not None
            ]
            if not dates:
                continue

            # Compute overall rate
            date_min = min(dates)
            date_max = max(dates)
            total_span = max((date_max - date_min).days + 1, 1)
            avg_per_window = (len(changes) / total_span) * window_days

            if avg_per_window < 0.5:
                # Not enough activity to have meaningful bursts
                continue

            # Slide a window across the timeline
            window_delta = timedelta(days=window_days)
            sorted_changes = sorted(
                changes, key=lambda c: c.commit_date or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

            # Check the most recent window
            window_start = now - window_delta
            window_changes = [
                c for c in sorted_changes
                if c.commit_date and c.commit_date >= window_start
            ]

            if len(window_changes) > avg_per_window * threshold:
                # Calculate the date range of this burst
                burst_dates = [
                    c.commit_date for c in window_changes if c.commit_date
                ]
                if not burst_dates:
                    continue
                involved = list(
                    {
                        c.author_email
                        for c in window_changes
                        if c.author_email
                    }
                )

                bursts.append(
                    ChangeBurst(
                        file_path=file_path,
                        file_id=(
                            str(window_changes[0].file_id)
                            if window_changes[0].file_id
                            else None
                        ),
                        burst_start=min(burst_dates),
                        burst_end=max(burst_dates),
                        burst_changes=len(window_changes),
                        baseline_avg=round(avg_per_window, 2),
                        spike_ratio=round(
                            len(window_changes) / max(avg_per_window, 0.1), 2,
                        ),
                        involved_authors=involved,
                    )
                )

        bursts.sort(key=lambda b: b.spike_ratio, reverse=True)
        logger.info("Detected %d change bursts", len(bursts))
        return bursts

    # ── File timeline ───────────────────────────────────────────────────

    async def get_file_timeline(
        self,
        repository_id: _uuid.UUID,
        file_path: str,
        db: AsyncSession,
    ) -> FileTimeline:
        """Return the full change history (timeline) for a specific file."""
        logger.info(
            "Retrieving timeline for file %s in repository %s",
            file_path,
            repository_id,
        )

        stmt = (
            select(CodeHistory)
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.file_path == file_path,
            )
            .order_by(desc(CodeHistory.commit_date))
        )

        result = await db.execute(stmt)
        rows = result.scalars().all()

        entries: list[FileTimelineEntry] = []
        for row in rows:
            entries.append(
                FileTimelineEntry(
                    commit_sha=row.commit_sha,
                    commit_date=row.commit_date,
                    author_name=row.author_name,
                    author_email=row.author_email,
                    change_type=row.change_type,
                    lines_added=row.lines_added,
                    lines_deleted=row.lines_deleted,
                    message=row.message,
                )
            )

        dates = [e.commit_date for e in entries if e.commit_date]
        if dates:
            period_days = max((max(dates) - min(dates)).days + 1, 1)
        else:
            period_days = 0

        file_id: Optional[str] = None
        if rows and rows[0].file_id:
            file_id = str(rows[0].file_id)

        return FileTimeline(
            file_path=file_path,
            file_id=file_id,
            total_commits=len(entries),
            entries=entries,
            period_days=period_days,
        )

    # ── Stale file detection ────────────────────────────────────────────

    async def detect_stale_files(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
        stale_days: int = STALE_DEFAULT_DAYS,
    ) -> list[StaleFile]:
        """Find files that have not been modified in the last N days.

        Only considers files that *have* historical changes (i.e. were
        created within the repository's history).
        """
        logger.info(
            "Detecting stale files (> %d days) for repository %s",
            stale_days,
            repository_id,
        )

        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)

        # Get last change date per file
        last_change_stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.file_id,
                func.max(CodeHistory.commit_date).label("last_changed"),
                func.count().label("total_changes"),
            )
            .where(CodeHistory.repository_id == repository_id)
            .group_by(CodeHistory.file_path, CodeHistory.file_id)
        )

        result = await db.execute(last_change_stmt)
        rows = result.all()

        stale_files: list[StaleFile] = []
        for row in rows:
            last_changed = row.last_changed
            if last_changed is None:
                continue

            # Normalize timezone awareness so SQLite (naive) and Postgres
            # (aware) datetimes compare without raising.
            _cutoff = cutoff
            if last_changed.tzinfo is None and _cutoff.tzinfo is not None:
                _cutoff = _cutoff.replace(tzinfo=None)
            elif last_changed.tzinfo is not None and _cutoff.tzinfo is None:
                last_changed = last_changed.replace(tzinfo=timezone.utc)

            if last_changed >= _cutoff:
                # Still active
                continue

            _now = datetime.now(timezone.utc)
            if last_changed.tzinfo is None:
                last_changed = last_changed.replace(tzinfo=timezone.utc)
            days_since = (_now - last_changed).days

            # Find the primary author (most commits)
            primary_author = await self._get_file_primary_author(
                repository_id, row.file_path, db,
            )

            stale_files.append(
                StaleFile(
                    file_path=row.file_path,
                    file_id=str(row.file_id) if row.file_id else None,
                    last_changed=last_changed,
                    days_since_change=days_since,
                    total_historical_changes=row.total_changes,
                    primary_author=primary_author,
                )
            )

        stale_files.sort(
            key=lambda s: s.days_since_change or 0,
            reverse=True,
        )
        logger.info("Found %d stale files", len(stale_files))
        return stale_files

    # ── Aggregate summary ───────────────────────────────────────────────

    async def get_change_summary(
        self,
        repository_id: _uuid.UUID,
        db: AsyncSession,
    ) -> ChangeSummary:
        """Provide a comprehensive aggregate change summary for the repository."""
        logger.info(
            "Building change summary for repository %s", repository_id,
        )

        stats_stmt = (
            select(
                func.count().label("total_commits"),
                func.count(func.distinct(CodeHistory.file_path)).label(
                    "total_files"
                ),
                func.count(func.distinct(CodeHistory.author_email)).label(
                    "unique_authors"
                ),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "total_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "total_deleted"
                ),
                func.min(CodeHistory.commit_date).label("first_commit"),
                func.max(CodeHistory.commit_date).label("last_commit"),
            ).where(CodeHistory.repository_id == repository_id)
        )

        result = await db.execute(stats_stmt)
        row = result.one()

        total_added = row.total_added
        total_deleted = row.total_deleted
        total_changed = total_added + total_deleted
        first = row.first_commit
        last = row.last_commit
        period_days = max((last - first).days + 1, 1) if first and last else 1
        avg_commits_per_day = round(
            row.total_commits / max(period_days, 1), 2,
        )
        churn_ratio = round(total_deleted / max(total_added, 1), 4)

        # Sub-summary components
        hotspots = await self.detect_hotspots(repository_id, db, top_n=10)
        author_activity = await self.get_author_activity(repository_id, db)
        top_contributors = author_activity[:10]
        recent_mods = await self.get_recent_modifications(
            repository_id, db, days=30,
        )
        stale = await self.detect_stale_files(repository_id, db, stale_days=90)
        high_risk = await self.identify_high_risk_areas(repository_id, db)

        return ChangeSummary(
            repository_id=str(repository_id),
            total_commits=row.total_commits,
            total_files_ever_changed=row.total_files,
            unique_authors=row.unique_authors,
            total_lines_added=total_added,
            total_lines_deleted=total_deleted,
            total_lines_changed=total_changed,
            period_days=period_days,
            first_commit=first,
            last_commit=last,
            avg_commits_per_day=avg_commits_per_day,
            top_hotspots=hotspots,
            top_contributors=top_contributors,
            recent_modifications_count=len(recent_mods),
            stale_files_count=len(stale),
            high_risk_count=len(high_risk),
            overall_churn_ratio=churn_ratio,
        )

    # ── Private helpers ─────────────────────────────────────────────────

    async def _get_author_top_files(
        self,
        repository_id: _uuid.UUID,
        author_email: Optional[str],
        db: AsyncSession,
        limit: int = 10,
    ) -> list[dict]:
        """Return the top files changed by a specific author."""
        if not author_email:
            return []

        stmt = (
            select(
                CodeHistory.file_path,
                func.count().label("commit_count"),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label(
                    "lines_added"
                ),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label(
                    "lines_deleted"
                ),
            )
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.author_email == author_email,
            )
            .group_by(CodeHistory.file_path)
            .order_by(desc("commit_count"))
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [
            {
                "file_path": r.file_path,
                "commit_count": r.commit_count,
                "lines_added": r.lines_added,
                "lines_deleted": r.lines_deleted,
            }
            for r in rows
        ]

    async def _count_active_days(
        self,
        repository_id: _uuid.UUID,
        author_email: Optional[str],
        db: AsyncSession,
    ) -> int:
        """Count the number of distinct days an author committed to the repo."""
        if not author_email:
            return 0

        stmt = (
            select(
                func.count(func.distinct(
                    func.date(CodeHistory.commit_date)
                )).label("active_days")
            )
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.author_email == author_email,
                CodeHistory.commit_date.isnot(None),
            )
        )

        result = await db.execute(stmt)
        row = result.one()
        return row.active_days or 0

    async def _get_file_primary_author(
        self,
        repository_id: _uuid.UUID,
        file_path: str,
        db: AsyncSession,
    ) -> Optional[str]:
        """Return the author with the most commits for a file."""
        stmt = (
            select(
                CodeHistory.author_name,
                func.count().label("commit_count"),
            )
            .where(
                CodeHistory.repository_id == repository_id,
                CodeHistory.file_path == file_path,
                CodeHistory.author_name.isnot(None),
            )
            .group_by(CodeHistory.author_name)
            .order_by(desc("commit_count"))
            .limit(1)
        )

        result = await db.execute(stmt)
        row = result.first()
        return row.author_name if row else None
