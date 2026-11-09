import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from backend.app.db.base import Base

EMBEDDING_DIMENSIONS = 256


class EmbeddingVector(TypeDecorator):
    """Uses native pgvector Vector(dim) on PostgreSQL and JSON Text on SQLite/other dialects."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIMENSIONS) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        vec = [float(x) for x in value]
        if dialect.name == "postgresql":
            return vec
        return json.dumps(vec)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return [float(x) for x in json.loads(value)]
            except ValueError:
                return None
        return [float(x) for x in value]


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index",
        ),
        CheckConstraint("page_number >= 1", name="ck_document_chunks_page_number"),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_chunk_index"),
        CheckConstraint("char_count >= 0", name="ck_document_chunks_char_count"),
        CheckConstraint(
            "chunk_type IN ('text', 'table', 'image')",
            name="ck_document_chunks_chunk_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    title: Mapped[str | None] = mapped_column(String(300))
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        EmbeddingVector(EMBEDDING_DIMENSIONS),
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def meta(self) -> dict[str, Any]:
        if not self.metadata_json:
            return {}
        try:
            loaded = json.loads(self.metadata_json)
            if isinstance(loaded, dict):
                return loaded
        except ValueError:
            return {}
        return {}

    @property
    def has_embedding(self) -> bool:
        return self.embedding is not None and len(self.embedding) > 0
