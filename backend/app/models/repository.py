"""Repository model — source code repositories."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Integer, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    private: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    git_url: Mapped[Optional[str]] = mapped_column(String(1000))
    default_branch: Mapped[str] = mapped_column(String(100), default="main", nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(50))
    size: Mapped[Optional[int]] = mapped_column(Integer)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    last_indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization: Mapped[Optional["Organization"]] = relationship(back_populates="repositories")  # noqa: F821
    project: Mapped[Optional["Project"]] = relationship()  # noqa: F821
    branches: Mapped[list["Branch"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    commits: Mapped[list["Commit"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
    versions: Mapped[list["RepositoryVersion"]] = relationship(back_populates="repository", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_repositories_org_id", "organization_id"),
        Index("ix_repositories_language", "language"),
    )


class Branch(Base, TimestampMixin):
    __tablename__ = "branches"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    head_commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    repository: Mapped["Repository"] = relationship(back_populates="branches")

    __table_args__ = (
        Index("ix_branches_repo_id", "repository_id"),
        Index("ix_branches_repo_name", "repository_id", "name", unique=True),
    )


class Commit(Base, TimestampMixin):
    __tablename__ = "commits"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_email: Mapped[str] = mapped_column(String(255), nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committer_name: Mapped[Optional[str]] = mapped_column(String(255))
    committer_email: Mapped[Optional[str]] = mapped_column(String(255))
    additions: Mapped[Optional[int]] = mapped_column(Integer)
    deletions: Mapped[Optional[int]] = mapped_column(Integer)
    files_changed: Mapped[Optional[int]] = mapped_column(Integer)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    repository: Mapped["Repository"] = relationship(back_populates="commits")

    __table_args__ = (
        Index("ix_commits_repo_id", "repository_id"),
        Index("ix_commits_sha_repo", "sha", "repository_id", unique=True),
        Index("ix_commits_authored_at", "authored_at"),
    )


class RepositoryVersion(Base, TimestampMixin):
    __tablename__ = "repository_versions"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(255))
    release_notes: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    repository: Mapped["Repository"] = relationship(back_populates="versions")

    __table_args__ = (
        Index("ix_repo_versions_repo_id", "repository_id"),
        Index("ix_repo_versions_version", "repository_id", "version", unique=True),
    )
