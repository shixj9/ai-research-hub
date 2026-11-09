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
    AIConfigSummaryResponse,
    AIConfigUpdateRequest,
    ChunkSearchResponse,
    DocumentChunkListResponse,
    DocumentChunkType,
    DocumentCreate,
    DocumentListResponse,
    DocumentPageListResponse,
    DocumentParseResponse,
    DocumentResponse,
    DocumentUpdate,
    RagAskRequest,
    RagAskResponse,
    SearchMode,
)
from backend.app.services.document_chunker import search_document_chunks
from backend.app.services.document_parser import (
    DocumentFileMissingError,
    UnreadablePdfParseError,
    list_document_chunks,
    list_document_pages,
    parse_pdf_document,
)
from backend.app.services.document_upload import (
    DuplicateDocumentError,
    InvalidPdfError,
    PdfStorageError,
    PdfTooLargeError,
    save_pdf_document,
)
from backend.app.services.embedding_service import (
    get_ai_config_summary,
    update_ai_providers_config,
)
from backend.app.services.rag_qa import answer_question_with_rag

router = APIRouter(prefix="/documents", tags=["documents"])
DatabaseSession = Annotated[Session, Depends(get_db)]
settings = get_settings()


def _get_document_or_404(db: Session, document_id: UUID) -> Document:
    document = DocumentRepository.get(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.get("/ai-config", response_model=AIConfigSummaryResponse)
def get_ai_config() -> AIConfigSummaryResponse:
    return AIConfigSummaryResponse(**get_ai_config_summary())


@router.put("/ai-config", response_model=AIConfigSummaryResponse)
def update_ai_config(payload: AIConfigUpdateRequest) -> AIConfigSummaryResponse:
    updated = update_ai_providers_config(
        active_llm=payload.active_llm,
        llm_model=payload.llm_model,
        llm_base_url=payload.llm_base_url,
        llm_api_key=payload.llm_api_key,
        active_embedding=payload.active_embedding,
        embedding_model=payload.embedding_model,
        embedding_base_url=payload.embedding_base_url,
        embedding_api_key=payload.embedding_api_key,
    )
    return AIConfigSummaryResponse(**updated)


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


@router.get("/search", response_model=ChunkSearchResponse)
def search_chunks(
    db: DatabaseSession,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    document_id: Annotated[UUID | None, Query()] = None,
    chunk_type: Annotated[DocumentChunkType | None, Query()] = None,
    mode: Annotated[SearchMode, Query()] = SearchMode.HYBRID,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ChunkSearchResponse:
    return search_document_chunks(
        db,
        q,
        document_id=document_id,
        chunk_type=chunk_type,
        mode=mode,
        limit=limit,
    )


@router.post("/ask", response_model=RagAskResponse)
def ask_documents(
    payload: RagAskRequest,
    db: DatabaseSession,
) -> RagAskResponse:
    if payload.document_id is not None:
        _get_document_or_404(db, payload.document_id)
    return answer_question_with_rag(db, payload)


@router.post("/{document_id}/ask", response_model=RagAskResponse)
def ask_single_document(
    document_id: UUID,
    payload: RagAskRequest,
    db: DatabaseSession,
) -> RagAskResponse:
    _get_document_or_404(db, document_id)
    return answer_question_with_rag(db, payload, override_document_id=document_id)


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


@router.post("/{document_id}/parse", response_model=DocumentParseResponse)
def parse_document(document_id: UUID, db: DatabaseSession) -> DocumentParseResponse:
    document = _get_document_or_404(db, document_id)
    try:
        return parse_pdf_document(db, document, storage_root=settings.storage_root)
    except DocumentFileMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except UnreadablePdfParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/{document_id}/pages", response_model=DocumentPageListResponse)
def get_document_pages(document_id: UUID, db: DatabaseSession) -> DocumentPageListResponse:
    document = _get_document_or_404(db, document_id)
    return list_document_pages(db, document)


@router.get("/{document_id}/chunks", response_model=DocumentChunkListResponse)
def get_document_chunks(
    document_id: UUID,
    db: DatabaseSession,
    chunk_type: Annotated[DocumentChunkType | None, Query()] = None,
) -> DocumentChunkListResponse:
    document = _get_document_or_404(db, document_id)
    return list_document_chunks(db, document, chunk_type=chunk_type)


@router.get("/{document_id}/figures/{figure_name}", response_class=FileResponse)
def open_document_figure(
    document_id: UUID,
    figure_name: str,
    db: DatabaseSession,
) -> FileResponse:
    _get_document_or_404(db, document_id)
    figures_root = (settings.storage_root.resolve() / "figures" / str(document_id)).resolve()
    file_path = (figures_root / figure_name).resolve()
    if not file_path.is_relative_to(figures_root) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Figure not found",
        )
    return FileResponse(file_path, media_type="image/png", content_disposition_type="inline")


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
