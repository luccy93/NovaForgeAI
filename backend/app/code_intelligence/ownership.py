"""Code Ownership analysis module for the code intelligence engine.

Parses CODEOWNERS, MAINTAINERS, OWNERS, and COLLABORATORS files, derives
ownership from git history, and computes ownership scores, bus-factor risk,
and contributor statistics.
"""

from __future__ import annotations

import fnmatch
import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import CodeHistory, CodeOwnership, CodeFile

logger = logging.getLogger(__name__)


# ─── Dataclasses ────────────────────────────────────────────────────────


@dataclass
class OwnershipRule:
    pattern: str
    owners: list[str]
    line_number: int
    source_file: str


@dataclass
class OwnerInfo:
    email: str
    name: Optional[str]
    ownership_score: float
    commits_count: int
    lines_changed: int
    last_commit_date: Optional[datetime]
    role: Optional[str] = None


@dataclass
class FileOwnershipResult:
    file_path: str
    owners: list[OwnerInfo]
    primary_owner: Optional[OwnerInfo]
    ownership_source: str
    bus_factor: int
    is_unowned: bool


@dataclass
class ContributorStats:
    email: str
    name: Optional[str]
    total_commits: int
    total_lines_added: int
    total_lines_deleted: int
    total_lines_changed: int
    files_touched: int
    first_commit_date: Optional[datetime]
    last_commit_date: Optional[datetime]
    ownership_score: float


@dataclass
class BusRiskItem:
    file_path: str
    sole_owner_email: str
    sole_owner_name: Optional[str]
    total_commits: int
    last_commit_date: Optional[datetime]
    risk_level: str


@dataclass
class OwnershipSummary:
    repository_id: uuid.UUID
    total_files: int
    files_with_ownership: int
    files_unowned: int
    unique_owners: int
    avg_bus_factor: float
    high_risk_files: int
    medium_risk_files: int
    low_risk_files: int
    top_contributors: list[ContributorStats]
    ownership_coverage: float


@dataclass
class OwnershipMap:
    repository_id: uuid.UUID
    files: dict[str, FileOwnershipResult]
    contributors: dict[str, ContributorStats]
    summary: OwnershipSummary


# ─── Constants ──────────────────────────────────────────────────────────

CODEOWNERS_PATHS = (".github/CODEOWNERS", "docs/CODEOWNERS", "CODEOWNERS")
MAINTAINERS_PATHS = ("MAINTAINERS", "docs/MAINTAINERS")
OWNERS_PATHS = ("OWNERS", "docs/OWNERS")
COLLABORATORS_PATHS = (".github/COLLABORATORS",)

DEFAULT_BUS_FACTOR_THRESHOLD = 2
DEFAULT_UNOWNED_THRESHOLD = 0.0
RECENCY_DECAY_HALF_LIFE_DAYS = 180

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2}


# ─── OwnershipAnalyzer ─────────────────────────────────────────────────


class OwnershipAnalyzer:
    """Main class for code ownership analysis."""

    def __init__(self, half_life_days: int = RECENCY_DECAY_HALF_LIFE_DAYS) -> None:
        self._half_life_days = half_life_days
        logger.info("OwnershipAnalyzer initialized (half_life=%d days)", half_life_days)

    # ── Parsing ──────────────────────────────────────────────────────

    def parse_codeowners(
        self,
        repository_id: uuid.UUID,
        content: str,
        source_file: str = "CODEOWNERS",
    ) -> list[OwnershipRule]:
        """Parse a CODEOWNERS / MAINTAINERS / OWNERS / COLLABORATORS file.

        Supports GitHub CODEOWNERS, Kubernetes OWNERS (approvers/reviewers),
        and simple email-per-line MAINTAINERS / COLLABORATORS formats.
        """
        logger.debug("Parsing ownership file %s for repository %s", source_file, repository_id)
        if self._is_owners_format(content):
            rules = self._parse_owners_yaml(content.splitlines(), source_file)
        elif self._is_maintainers_format(content):
            rules = self._parse_maintainers(content.splitlines(), source_file)
        else:
            rules = self._parse_codeowners_lines(content.splitlines(), source_file)
        logger.info("Parsed %d rules from %s for repository %s", len(rules), source_file, repository_id)
        return rules

    def _parse_codeowners_lines(self, lines: list[str], source_file: str) -> list[OwnershipRule]:
        rules: list[OwnershipRule] = []
        for line_num, raw in enumerate(lines, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            owners = [self._norm(o) for o in parts[1:] if o]
            if owners:
                rules.append(OwnershipRule(pattern=pattern, owners=owners, line_number=line_num, source_file=source_file))
        return rules

    def _parse_maintainers(self, lines: list[str], source_file: str) -> list[OwnershipRule]:
        owners: list[str] = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            email = self._extract_email(line)
            owners.append(email or self._norm(line))
        owners = [o for o in owners if o]
        return [OwnershipRule(pattern="*", owners=owners, line_number=1, source_file=source_file)] if owners else []

    def _parse_owners_yaml(self, lines: list[str], source_file: str) -> list[OwnershipRule]:
        rules: list[OwnershipRule] = []
        current_section: Optional[str] = None
        section_owners: list[str] = []

        def _flush(line_num: int) -> None:
            nonlocal current_section, section_owners
            if current_section and section_owners:
                for owner in section_owners:
                    rules.append(OwnershipRule(pattern="*", owners=[owner], line_number=line_num, source_file=source_file))
            section_owners = []

        for line_num, raw in enumerate(lines, 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not raw.startswith(" ") and not raw.startswith("\t"):
                _flush(line_num)
                current_section = stripped.split(":")[0].strip().lower()
                value = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
                if value:
                    for item in value.split(","):
                        n = self._norm(item.strip())
                        if n:
                            section_owners.append(n)
            else:
                n = self._norm(stripped.strip("- ").strip())
                if n:
                    section_owners.append(n)

        _flush(line_num if lines else 0)
        return rules

    @staticmethod
    def _is_owners_format(content: str) -> bool:
        lower = content.lower()
        return "approvers:" in lower or "reviewers:" in lower

    @staticmethod
    def _is_maintainers_format(content: str) -> bool:
        non_comment = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not non_comment:
            return False
        # Require lines that look like real emails (name@domain.tld) or
        # are wrapped in angle brackets.  GitHub CODEOWNERS uses bare
        # ``@username`` handles which must NOT be treated as MAINTAINERS.
        emailish = re.compile(r"@[^@\s]+\.[^@\s]+|<[^>]+>")
        return sum(1 for l in non_comment if emailish.search(l)) / len(non_comment) > 0.5

    @staticmethod
    def _norm(raw: str) -> Optional[str]:
        cleaned = raw.strip().strip("@").strip("<>").strip()
        return cleaned if cleaned else None

    @staticmethod
    def _extract_email(line: str) -> Optional[str]:
        m = re.search(r"<([^>]+)>", line)
        if m:
            return m.group(1).strip().lower()
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", line.strip()):
            return line.strip().lower()
        return None

    @staticmethod
    def _matches_pattern(file_path: str, pattern: str) -> bool:
        pattern = pattern.strip("/")
        file_path = file_path.strip("/")
        if pattern.startswith("**"):
            inner = pattern.lstrip("*/")
            return fnmatch.fnmatch(file_path, inner) or fnmatch.fnmatch(file_path, pattern)
        if pattern.endswith("**"):
            return file_path.startswith(pattern.rstrip("*/"))
        if "/" in pattern:
            return fnmatch.fnmatch(file_path, pattern)
        return fnmatch.fnmatch(file_path.split("/")[-1], pattern) or fnmatch.fnmatch(file_path, f"**/{pattern}")

    # ── History-based derivation ─────────────────────────────────────

    def _recency_weight(self, commit_date: Optional[datetime], reference: Optional[datetime] = None) -> float:
        if commit_date is None:
            return 0.5
        ref = reference or datetime.now(timezone.utc)
        if commit_date.tzinfo is None:
            commit_date = commit_date.replace(tzinfo=timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        days = max((ref - commit_date).total_seconds() / 86400, 0)
        return math.exp(-0.693 * days / self._half_life_days)

    async def derive_ownership_from_history(
        self, repository_id: uuid.UUID, db: AsyncSession,
    ) -> list[CodeOwnership]:
        """Aggregate commits and lines per (file, author) and compute scores."""
        stmt = (
            select(
                CodeHistory.file_path,
                CodeHistory.author_email,
                CodeHistory.author_name,
                func.count(CodeHistory.commit_sha).label("commits"),
                func.coalesce(func.sum(CodeHistory.lines_added), 0).label("added"),
                func.coalesce(func.sum(CodeHistory.lines_deleted), 0).label("deleted"),
                func.max(CodeHistory.commit_date).label("last_date"),
            )
            .where(and_(
                CodeHistory.repository_id == repository_id,
                CodeHistory.author_email.isnot(None),
                CodeHistory.author_email != "",
            ))
            .group_by(CodeHistory.file_path, CodeHistory.author_email, CodeHistory.author_name)
        )
        rows = (await db.execute(stmt)).all()
        now = datetime.now(timezone.utc)

        aggregated: dict[tuple[str, str], dict] = {}
        for row in rows:
            key = (row.file_path, row.author_email)
            e = aggregated.setdefault(key, {"commits": 0, "added": 0, "deleted": 0, "last_date": None, "name": row.author_name})
            e["commits"] += row.commits
            e["added"] += row.added
            e["deleted"] += row.deleted
            e["name"] = e["name"] or row.author_name
            if row.last_date and (e["last_date"] is None or row.last_date > e["last_date"]):
                e["last_date"] = row.last_date

        file_totals: dict[str, int] = {}
        for (fp, _), e in aggregated.items():
            file_totals[fp] = file_totals.get(fp, 0) + e["commits"]

        records: list[CodeOwnership] = []
        for (file_path, email), e in aggregated.items():
            total_for_file = file_totals.get(file_path, 1)
            commit_ratio = e["commits"] / max(total_for_file, 1)
            recency = self._recency_weight(e["last_date"], now)
            lines_changed = e["added"] + e["deleted"]
            line_weight = min(lines_changed / 500.0, 1.0)
            score = round(commit_ratio * 0.5 + recency * 0.3 + line_weight * 0.2, 4)
            records.append(CodeOwnership(
                repository_id=repository_id, file_path=file_path, owner_email=email,
                owner_name=e["name"], ownership_score=score, commits_count=e["commits"],
                lines_changed=lines_changed, last_commit_date=e["last_date"],
            ))
        records.sort(key=lambda o: o.ownership_score, reverse=True)
        logger.info("Derived %d ownership records for repository %s", len(records), repository_id)
        return records

    async def persist_ownership(
        self, repository_id: uuid.UUID, db: AsyncSession,
        records: list[CodeOwnership], *, delete_existing: bool = True,
    ) -> int:
        if delete_existing:
            from sqlalchemy import delete as sa_delete
            await db.execute(sa_delete(CodeOwnership).where(CodeOwnership.repository_id == repository_id))
        for r in records:
            db.add(r)
        await db.flush()
        logger.info("Persisted %d ownership records for repository %s", len(records), repository_id)
        return len(records)

    # ── Queries ──────────────────────────────────────────────────────

    async def get_file_owners(
        self, repository_id: uuid.UUID, file_path: str, db: AsyncSession,
    ) -> list[OwnerInfo]:
        stmt = (
            select(CodeOwnership)
            .where(and_(CodeOwnership.repository_id == repository_id, CodeOwnership.file_path == file_path))
            .order_by(CodeOwnership.ownership_score.desc())
        )
        return [
            OwnerInfo(email=r.owner_email, name=r.owner_name, ownership_score=r.ownership_score,
                      commits_count=r.commits_count, lines_changed=r.lines_changed,
                      last_commit_date=r.last_commit_date, role=r.role)
            for r in (await db.execute(stmt)).scalars().all()
        ]

    async def get_repository_ownership_map(
        self, repository_id: uuid.UUID, db: AsyncSession,
        codeowners_content: Optional[str] = None,
    ) -> OwnershipMap:
        """Build a full ownership map combining CODEOWNERS rules with history."""
        codeowner_rules: list[OwnershipRule] = []
        if codeowners_content:
            codeowner_rules = self.parse_codeowners(repository_id, codeowners_content)

        all_ownership = (await db.execute(
            select(CodeOwnership).where(CodeOwnership.repository_id == repository_id)
        )).scalars().all()

        all_files = [
            r.file_path for r in (await db.execute(
                select(CodeFile.file_path).where(CodeFile.repository_id == repository_id)
            )).all()
        ]

        by_file: dict[str, list[CodeOwnership]] = {}
        for o in all_ownership:
            by_file.setdefault(o.file_path, []).append(o)

        contributor_stats = await self.get_contributor_stats(repository_id, db)

        files_map: dict[str, FileOwnershipResult] = {}
        for fp in all_files:
            owners: list[OwnerInfo] = []
            source = "history"

            if codeowner_rules:
                matching = [r for r in codeowner_rules if self._matches_pattern(fp, r.pattern)]
                if matching:
                    source = "codeowners"
                    for rule in matching:
                        for owner_id in rule.owners:
                            existing = next(
                                (o for o in by_file.get(fp, []) if o.owner_email == owner_id or o.owner_name == owner_id), None,
                            )
                            if existing:
                                owners.append(OwnerInfo(email=existing.owner_email, name=existing.owner_name,
                                                        ownership_score=existing.ownership_score, commits_count=existing.commits_count,
                                                        lines_changed=existing.lines_changed, last_commit_date=existing.last_commit_date))
                            else:
                                owners.append(OwnerInfo(email=owner_id, name=None, ownership_score=1.0,
                                                        commits_count=0, lines_changed=0, last_commit_date=None, role="codeowners"))

            if not owners:
                for o in by_file.get(fp, []):
                    owners.append(OwnerInfo(email=o.owner_email, name=o.owner_name, ownership_score=o.ownership_score,
                                            commits_count=o.commits_count, lines_changed=o.lines_changed,
                                            last_commit_date=o.last_commit_date, role=o.role))

            owners.sort(key=lambda o: o.ownership_score, reverse=True)
            primary = owners[0] if owners else None
            files_map[fp] = FileOwnershipResult(
                file_path=fp, owners=owners, primary_owner=primary,
                ownership_source=source, bus_factor=len(owners), is_unowned=not owners,
            )

        summary = await self._build_summary(repository_id, files_map, contributor_stats)
        logger.info("Built ownership map for repository %s: %d files, %d contributors",
                     repository_id, len(files_map), len(contributor_stats))
        return OwnershipMap(repository_id=repository_id, files=files_map, contributors=contributor_stats, summary=summary)

    async def get_contributor_stats(
        self, repository_id: uuid.UUID, db: AsyncSession,
    ) -> dict[str, ContributorStats]:
        stmt = (
            select(
                CodeOwnership.owner_email, CodeOwnership.owner_name,
                func.sum(CodeOwnership.commits_count).label("total_commits"),
                func.sum(CodeOwnership.lines_changed).label("total_lines"),
                func.count(CodeOwnership.file_path).label("files_count"),
                func.min(CodeOwnership.last_commit_date).label("first_date"),
                func.max(CodeOwnership.last_commit_date).label("last_date"),
                func.sum(CodeOwnership.ownership_score).label("score_sum"),
            )
            .where(CodeOwnership.repository_id == repository_id)
            .group_by(CodeOwnership.owner_email, CodeOwnership.owner_name)
        )
        result: dict[str, ContributorStats] = {}
        for row in (await db.execute(stmt)).all():
            total = row.total_lines or 0
            result[row.owner_email] = ContributorStats(
                email=row.owner_email, name=row.owner_name,
                total_commits=row.total_commits or 0, total_lines_added=total,
                total_lines_deleted=0, total_lines_changed=total,
                files_touched=row.files_count or 0,
                first_commit_date=row.first_date, last_commit_date=row.last_date,
                ownership_score=round(row.score_sum or 0.0, 4),
            )
        return result

    async def identify_bus_risk(
        self, repository_id: uuid.UUID, db: AsyncSession,
        threshold: int = DEFAULT_BUS_FACTOR_THRESHOLD,
    ) -> list[BusRiskItem]:
        """Find files with few significant owners (bus factor <= threshold)."""
        stmt = (
            select(
                CodeOwnership.file_path, CodeOwnership.owner_email, CodeOwnership.owner_name,
                CodeOwnership.ownership_score, CodeOwnership.commits_count,
                CodeOwnership.last_commit_date,
                func.count(CodeOwnership.owner_email).over(partition_by=CodeOwnership.file_path).label("owner_count"),
            )
            .where(and_(CodeOwnership.repository_id == repository_id, CodeOwnership.ownership_score > 0.1))
            .order_by(CodeOwnership.file_path, CodeOwnership.ownership_score.desc())
        )
        file_owners: dict[str, list] = {}
        for row in (await db.execute(stmt)).all():
            file_owners.setdefault(row.file_path, []).append(row)

        items: list[BusRiskItem] = []
        for fp, owners in file_owners.items():
            if len(owners) <= threshold:
                sole = owners[0]
                days = self._days_since(sole.last_commit_date)
                if sole.owner_count == 1:
                    risk = "high" if days < 90 else "medium"
                elif days < 180:
                    risk = "medium"
                else:
                    risk = "low"
                items.append(BusRiskItem(
                    file_path=fp, sole_owner_email=sole.owner_email, sole_owner_name=sole.owner_name,
                    total_commits=sole.commits_count, last_commit_date=sole.last_commit_date, risk_level=risk,
                ))
        items.sort(key=lambda r: (_RISK_ORDER[r.risk_level], r.file_path))
        logger.info("Identified %d bus-risk files in repository %s", len(items), repository_id)
        return items

    async def identify_unowned_files(
        self, repository_id: uuid.UUID, db: AsyncSession,
        score_threshold: float = DEFAULT_UNOWNED_THRESHOLD,
    ) -> list[str]:
        """Return files with no meaningful ownership record."""
        all_files = {r.file_path for r in (await db.execute(
            select(CodeFile.file_path).where(CodeFile.repository_id == repository_id)
        )).all()}
        owned = {r.file_path for r in (await db.execute(
            select(CodeOwnership.file_path).where(and_(
                CodeOwnership.repository_id == repository_id,
                CodeOwnership.ownership_score > score_threshold,
            )).distinct()
        )).all()}
        unowned = sorted(all_files - owned)
        logger.info("Identified %d unowned files in repository %s", len(unowned), repository_id)
        return unowned

    async def get_ownership_summary(
        self, repository_id: uuid.UUID, db: AsyncSession,
    ) -> OwnershipSummary:
        """Aggregate ownership statistics for a repository."""
        ownership_rows = (await db.execute(
            select(CodeOwnership).where(CodeOwnership.repository_id == repository_id)
        )).scalars().all()

        by_file: dict[str, list] = {}
        for o in ownership_rows:
            by_file.setdefault(o.file_path, []).append(o)

        total_files = (await db.execute(
            select(func.count(CodeFile.id)).where(CodeFile.repository_id == repository_id)
        )).scalar() or 0

        unique_owners = (await db.execute(
            select(func.count(func.distinct(CodeOwnership.owner_email)))
            .where(CodeOwnership.repository_id == repository_id)
        )).scalar() or 0

        bus_factors = [
            len([o for o in owners if o.ownership_score > 0.1]) or 0
            for owners in by_file.values()
        ]
        avg_bf = round(sum(bus_factors) / len(bus_factors), 2) if bus_factors else 0.0
        files_with = len(by_file)
        coverage = round((files_with / total_files) * 100, 2) if total_files > 0 else 0.0
        top = sorted(
            (await self.get_contributor_stats(repository_id, db)).values(),
            key=lambda c: c.ownership_score, reverse=True,
        )[:10]

        return OwnershipSummary(
            repository_id=repository_id, total_files=total_files,
            files_with_ownership=files_with, files_unowned=max(total_files - files_with, 0),
            unique_owners=unique_owners, avg_bus_factor=avg_bf,
            high_risk_files=sum(1 for bf in bus_factors if bf <= 1),
            medium_risk_files=sum(1 for bf in bus_factors if 1 < bf <= 2),
            low_risk_files=sum(1 for bf in bus_factors if bf > 2),
            top_contributors=top, ownership_coverage=coverage,
        )

    # ── Matching helpers ─────────────────────────────────────────────

    def match_codeowners_to_files(
        self, rules: list[OwnershipRule], file_paths: list[str],
    ) -> dict[str, list[str]]:
        """Match CODEOWNERS rules against file paths. Last match wins."""
        result: dict[str, list[str]] = {}
        for fp in file_paths:
            matched: list[str] = []
            for rule in rules:
                if self._matches_pattern(fp, rule.pattern):
                    matched = list(rule.owners)
            result[fp] = matched
        return result

    async def merge_codeowners_with_history(
        self, repository_id: uuid.UUID, rules: list[OwnershipRule], db: AsyncSession,
    ) -> int:
        """Persist CODEOWNERS entries that don't already exist in history data."""
        existing = {
            (r.file_path, r.owner_email) for r in (await db.execute(
                select(CodeOwnership.file_path, CodeOwnership.owner_email)
                .where(CodeOwnership.repository_id == repository_id)
            )).all()
        }
        merged = 0
        for rule in rules:
            for owner in rule.owners:
                if (rule.pattern, owner) not in existing:
                    db.add(CodeOwnership(
                        repository_id=repository_id, file_path=rule.pattern,
                        owner_email=owner, ownership_score=1.0, role="codeowners",
                    ))
                    merged += 1
        await db.flush()
        logger.info("Merged %d CODEOWNERS records for repository %s", merged, repository_id)
        return merged

    # ── Composite entry point ────────────────────────────────────────

    async def analyze_repository(
        self, repository_id: uuid.UUID, db: AsyncSession,
        codeowners_content: Optional[str] = None,
    ) -> OwnershipMap:
        """Run the full ownership analysis pipeline."""
        logger.info("Starting full ownership analysis for repository %s", repository_id)
        records = await self.derive_ownership_from_history(repository_id, db)
        await self.persist_ownership(repository_id, db, records)
        if codeowners_content:
            rules = self.parse_codeowners(repository_id, codeowners_content)
            await self.merge_codeowners_with_history(repository_id, rules, db)
        await db.commit()
        ownership_map = await self.get_repository_ownership_map(repository_id, db, codeowners_content)
        logger.info("Completed ownership analysis for repository %s: %.1f%% coverage",
                     repository_id, ownership_map.summary.ownership_coverage)
        return ownership_map

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _days_since(date: Optional[datetime]) -> int:
        if date is None:
            return 9999
        now = datetime.now(timezone.utc)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(int((now - date).total_seconds() / 86400), 0)

    async def _build_summary(
        self, repository_id: uuid.UUID,
        files_map: dict[str, FileOwnershipResult],
        contributor_stats: dict[str, ContributorStats],
    ) -> OwnershipSummary:
        total = len(files_map)
        files_with = sum(1 for f in files_map.values() if not f.is_unowned)
        bus_factors = [f.bus_factor for f in files_map.values()]
        avg_bf = round(sum(bus_factors) / len(bus_factors), 2) if bus_factors else 0.0
        top = sorted(contributor_stats.values(), key=lambda c: c.ownership_score, reverse=True)[:10]
        coverage = round((files_with / total) * 100, 2) if total > 0 else 0.0
        return OwnershipSummary(
            repository_id=repository_id, total_files=total,
            files_with_ownership=files_with, files_unowned=total - files_with,
            unique_owners=len(contributor_stats), avg_bus_factor=avg_bf,
            high_risk_files=sum(1 for bf in bus_factors if bf <= 1),
            medium_risk_files=sum(1 for bf in bus_factors if 1 < bf <= 2),
            low_risk_files=sum(1 for bf in bus_factors if bf > 2),
            top_contributors=top, ownership_coverage=coverage,
        )
