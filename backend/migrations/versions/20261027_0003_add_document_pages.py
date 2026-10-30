"""Add document_pages table and document parse metadata.

Revision ID: 20261027_0003
Revises: 20261026_0002
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261027_0003"
down_revision: str | None = "20261026_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("parse_error", sa.String(length=500), nullable=True))

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_document_pages_page_number"),
        sa.CheckConstraint("char_count >= 0", name="ck_document_pages_char_count"),
        sa.CheckConstraint(
            "status IN ('ready', 'empty', 'failed')",
            name="ck_document_pages_status",
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "page_number",
            name="uq_document_pages_document_id_page_number",
        ),
    )
    op.create_index(
        "ix_document_pages_document_id",
        "document_pages",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_pages_document_id", table_name="document_pages")
    op.drop_table("document_pages")
    op.drop_column("documents", "parse_error")
    op.drop_column("documents", "parsed_at")
