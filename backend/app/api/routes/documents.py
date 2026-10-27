from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.document import Document
from backend.app.repositories.document import DocumentRepository
from backend.app.schemas.document import (
    DocumentCreate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
)
from backend.app.services.document_upload import (
    DuplicateDocumentError,
    InvalidPdfError,
    PdfStorageError,
    PdfTooLargeError,
    save_pdf_document,
)

router = APIRouter(prefix="/documents", tags=["documents"])
DatabaseSession = Annotated[Session, Depends(get_db)]
settings = get_settings()


def _get_document_or_404(db: Session, document_id: UUID) -> Document:
    document = DocumentRepository.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(payload: DocumentCreate, db: DatabaseSession) -> Document:
    try:
        return DocumentRepository.create(db, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with the same sha256 or storage_key already exists",
        ) from exc


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: Annotated[UploadFile, File(description="PDF file to store")],
    db: DatabaseSession,
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> Document:
    try:
        return save_pdf_document(
            db,
            file,
            title=title,
            storage_root=settings.storage_root,
            max_size_bytes=settings.max_pdf_size_bytes,
        )
    except PdfTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except InvalidPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except DuplicateDocumentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PdfStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store PDF",
        ) from exc


@router.get("", response_model=DocumentListResponse)
def list_documents(
    db: DatabaseSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> DocumentListResponse:
    items, total = DocumentRepository.list(db, offset=offset, limit=limit)
    return DocumentListResponse(items=items, total=total, offset=offset, limit=limit)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, db: DatabaseSession) -> Document:
    return _get_document_or_404(db, document_id)


@router.get("/{document_id}/file", response_class=FileResponse)
def open_document_file(document_id: UUID, db: DatabaseSession) -> FileResponse:
    document = _get_document_or_404(db, document_id)
    if document.storage_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document has no stored file",
        )

    storage_root = settings.storage_root.resolve()
    file_path = (storage_root / document.storage_key).resolve()
    if not file_path.is_relative_to(storage_root) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored PDF not found",
        )

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=document.original_filename or f"{document.id}.pdf",
        content_disposition_type="inline",
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    db: DatabaseSession,
) -> Document:
    if not payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one field must be provided",
        )

    document = _get_document_or_404(db, document_id)
    try:
        return DocumentRepository.update(db, document, payload)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with the same sha256 or storage_key already exists",
        ) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: UUID, db: DatabaseSession) -> Response:
    document = _get_document_or_404(db, document_id)
    DocumentRepository.soft_delete(db, document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
