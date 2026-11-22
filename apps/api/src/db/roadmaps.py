"""DailyCommit career roadmaps; independent of LearnHouse's LMS tables.

JSON references are deliberately not foreign keys. Future authoring endpoints
must validate section content, same-roadmap connections and course visibility.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer,
    Text, UniqueConstraint, Uuid, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_column(default: str) -> Column:
    # Production uses JSONB; the existing SQLite test suite can still create
    # the metadata without PostgreSQL-specific type compilation overrides.
    return Column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        server_default=text(default),
    )


class Roadmap(SQLModel, table=True):
    __tablename__ = "roadmaps"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_roadmaps_slug"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_roadmaps_status"),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=Column(
        Uuid(), primary_key=True, server_default=text("gen_random_uuid()"),
    ))
    slug: str = Field(sa_column=Column(Text, nullable=False))
    title: str = Field(sa_column=Column(Text, nullable=False))
    summary: str = Field(sa_column=Column(Text, nullable=False))
    sections: list[dict[str, Any]] = Field(default_factory=list, sa_column=_json_column("'[]'"))
    status: str = Field(default="draft", sa_column=Column(Text, nullable=False, server_default="draft"))
    created_at: datetime = Field(default_factory=_utcnow, sa_column=Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    ))
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    ))


class RoadmapNode(SQLModel, table=True):
    __tablename__ = "roadmap_nodes"
    __table_args__ = (
        UniqueConstraint("roadmap_id", "slug", name="uq_roadmap_nodes_roadmap_slug"),
        CheckConstraint("position >= 0", name="ck_roadmap_nodes_position"),
        Index("ix_roadmap_nodes_roadmap_position", "roadmap_id", "position"),
    )

    id: UUID = Field(default_factory=uuid4, sa_column=Column(
        Uuid(), primary_key=True, server_default=text("gen_random_uuid()"),
    ))
    roadmap_id: UUID = Field(sa_column=Column(
        Uuid(), ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False,
    ))
    slug: str = Field(sa_column=Column(Text, nullable=False))
    title: str = Field(sa_column=Column(Text, nullable=False))
    summary: str = Field(sa_column=Column(Text, nullable=False))
    sections: list[dict[str, Any]] = Field(default_factory=list, sa_column=_json_column("'[]'"))
    connections: list[dict[str, Any]] = Field(default_factory=list, sa_column=_json_column("'[]'"))
    course_links: list[dict[str, Any]] = Field(default_factory=list, sa_column=_json_column("'[]'"))
    layout: dict[str, Any] = Field(default_factory=dict, sa_column=_json_column("'{}'"))
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
