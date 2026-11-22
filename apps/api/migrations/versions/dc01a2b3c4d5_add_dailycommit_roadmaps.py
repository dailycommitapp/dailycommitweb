"""Add independent DailyCommit career roadmap tables.

Revision ID: dc01a2b3c4d5
Revises: 8d2b6f4c1e75

No LearnHouse table, data, enum or permission is changed. Startup create_all
may already have created these tables before Alembic runs.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "dc01a2b3c4d5"
down_revision = "8d2b6f4c1e75"
branch_labels = None
depends_on = None


def _already_exists(name: str, columns: set[str]) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(name):
        return False
    if {c["name"] for c in inspector.get_columns(name)} != columns:
        raise RuntimeError(f"Existing {name} does not match the roadmap schema; refusing to alter it")
    return True


def upgrade() -> None:
    if not _already_exists("roadmaps", {
        "id", "slug", "title", "summary", "sections", "status", "created_at", "updated_at",
    }):
        op.create_table(
            "roadmaps",
            sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("sections", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("slug", name="uq_roadmaps_slug"),
            sa.CheckConstraint("status IN ('draft', 'published')", name="ck_roadmaps_status"),
        )
    if not _already_exists("roadmap_nodes", {
        "id", "roadmap_id", "slug", "title", "summary", "sections", "connections",
        "course_links", "layout", "position",
    }):
        op.create_table(
            "roadmap_nodes",
            sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("roadmap_id", sa.Uuid(), nullable=False),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("sections", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("connections", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("course_links", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("layout", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("roadmap_id", "slug", name="uq_roadmap_nodes_roadmap_slug"),
            sa.CheckConstraint("position >= 0", name="ck_roadmap_nodes_position"),
        )
        op.create_index("ix_roadmap_nodes_roadmap_position", "roadmap_nodes", ["roadmap_id", "position"])


def downgrade() -> None:
    op.drop_table("roadmap_nodes")
    op.drop_table("roadmaps")
