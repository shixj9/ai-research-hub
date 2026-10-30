from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.models.document import Document
from backend.app.models.document_page import DocumentPage
from backend.app.schemas.document import (
    DocumentCreate,
    DocumentPageCreate,
    DocumentStatus,
    DocumentUpdate,
)


class DocumentRepository:
    @staticmethod
    def create(
        db: Session,
        payload: DocumentCreate,
        *,
        page_count: int | None = None,
    ) -> Document:
        document = Document(**payload.model_dump(), page_count=page_count)
        db.add(document)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def restore(
        db: Session,
        document: Document,
        payload: DocumentCreate,
        *,
        page_count: int | None = None,
    ) -> Document:
        for field, value in payload.model_dump().items():
            setattr(document, field, value)
        document.page_count = page_count
        document.deleted_at = None
        document.parsed_at = None
        document.parse_error = None
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def list(db: Session, *, offset: int, limit: int) -> tuple[list[Document], int]:
        active_documents = Document.deleted_at.is_(None)
        items = db.scalars(
            select(Document)
            .where(active_documents)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        total = db.scalar(select(func.count()).select_from(Document).where(active_documents)) or 0
        return list(items), total

    @staticmethod
    def get(db: Session, document_id: UUID) -> Document | None:
        return db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.deleted_at.is_(None),
            )
        )

    @staticmethod
    def get_by_sha256(db: Session, sha256: str) -> Document | None:
        return db.scalar(select(Document).where(Document.sha256 == sha256))

    @staticmethod
    def update(db: Session, document: Document, payload: DocumentUpdate) -> Document:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(document, field, value)
        db.commit()
        db.refresh(document)
        return document

    @staticmethod
    def soft_delete(db: Session, document: Document) -> None:
        document.deleted_at = datetime.now(UTC)
        db.commit()

    @staticmethod
    def replace_pages(
        db: Session,
        document: Document,
        pages: list[DocumentPageCreate],
        *,
        status: DocumentStatus,
        parse_error: str | None = None,
        page_count: int | None = None,
    ) -> list[DocumentPage]:
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
        page_models = [
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                text=page.text,
                char_count=page.char_count,
                status=page.status.value,
                error_message=page.error_message,
            )
            for page in pages
        ]
        db.add_all(page_models)
        document.status = status.value
        document.parsed_at = datetime.now(UTC)
        document.parse_error = parse_error
        if page_count is not None:
            document.page_count = page_count
        db.commit()
        db.refresh(document)
        return page_models

    @staticmethod
    def list_pages(db: Session, document_id: UUID) -> list[DocumentPage]:
        return list(
            db.scalars(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number.asc())
            ).all()
        )
