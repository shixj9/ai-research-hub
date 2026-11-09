"""Enable pgvector extension and add embedding columns to document_chunks.

Revision ID: 20261109_0005
Revises: 20261101_0004
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20261109_0005"
down_revision: str | None = "20261101_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.add_column(
            "document_chunks",
            sa.Column("embedding", Vector(256), nullable=True),
        )
        op.add_column(
            "document_chunks",
            sa.Column("embedding_model", sa.String(length=100), nullable=True),
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    else:
        op.add_column(
            "document_chunks",
            sa.Column("embedding", sa.Text(), nullable=True),
        )
        op.add_column(
            "document_chunks",
            sa.Column("embedding_model", sa.String(length=100), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding")
