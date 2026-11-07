from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from backend.app.models.document import Document
from backend.app.repositories.document import DocumentRepository
from backend.app.schemas.document import (
    DocumentChunkCreate,
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentChunkType,
    DocumentPageCreate,
    DocumentPageListResponse,
    DocumentPageResponse,
    DocumentPageStatus,
    DocumentParseResponse,
    DocumentResponse,
    DocumentStatus,
)
from backend.app.services.document_chunker import (
    build_text_chunks_for_page,
    extract_document_keywords,
    extract_image_chunks_for_page,
    extract_table_chunks_for_page,
)

SCANNED_PDF_ERROR_MESSAGE = (
    "未检测到可提取的文本层（疑似扫描版或纯图片 PDF，后续需通过 OCR 解析）"
)


class DocumentParseError(Exception):
    """Base exception for expected PDF parsing errors."""


class DocumentFileMissingError(DocumentParseError):
    """The document does not have a readable PDF file on local storage."""


class UnreadablePdfParseError(DocumentParseError):
    """The stored PDF file could not be opened or read by the parser."""


def _normalize_page_text(raw_text: str | None) -> str:
    if not raw_text:
        return ""
    without_nul = raw_text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return without_nul.strip()


def _resolve_stored_pdf_path(document: Document, storage_root: Path) -> Path:
    if not document.storage_key:
        raise DocumentFileMissingError("Document has no stored file")

    resolved_root = storage_root.resolve()
    file_path = (resolved_root / document.storage_key).resolve()
    if not file_path.is_relative_to(resolved_root) or not file_path.is_file():
        raise DocumentFileMissingError("Stored PDF not found")
    return file_path


def parse_pdf_document(
    db: Session,
    document: Document,
    *,
    storage_root: Path,
) -> DocumentParseResponse:
    file_path = _resolve_stored_pdf_path(document, storage_root)

    try:
        reader = PdfReader(file_path, strict=False)
        if reader.is_encrypted:
            raise UnreadablePdfParseError("Encrypted PDFs are not supported yet")
        raw_pages = list(reader.pages)
    except DocumentParseError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        DocumentRepository.replace_pages(
            db,
            document,
            [],
            status=DocumentStatus.FAILED,
            parse_error="无法读取 PDF 文件结构",
        )
        raise UnreadablePdfParseError("The stored PDF could not be parsed") from exc

    if not raw_pages:
        DocumentRepository.replace_pages(
            db,
            document,
            [],
            status=DocumentStatus.FAILED,
            parse_error="PDF 不包含任何页面",
            page_count=0,
        )
        raise UnreadablePdfParseError("The PDF contains no pages")

    parsed_pages: list[DocumentPageCreate] = []
    all_chunks: list[DocumentChunkCreate] = []
    all_table_terms: list[str] = []

    plumber_pdf = None
    try:
        plumber_pdf = pdfplumber.open(file_path)
    except Exception:
        plumber_pdf = None

    try:
        for page_number, page in enumerate(raw_pages, start=1):
            cleaned_text = ""
            try:
                cleaned_text = _normalize_page_text(page.extract_text())
                char_count = len(cleaned_text)
                page_status = (
                    DocumentPageStatus.READY if char_count > 0 else DocumentPageStatus.EMPTY
                )
                parsed_pages.append(
                    DocumentPageCreate(
                        page_number=page_number,
                        text=cleaned_text,
                        char_count=char_count,
                        status=page_status,
                        error_message=None,
                    )
                )
            except Exception as exc:
                parsed_pages.append(
                    DocumentPageCreate(
                        page_number=page_number,
                        text="",
                        char_count=0,
                        status=DocumentPageStatus.FAILED,
                        error_message=f"单页文本提取失败: {exc}"[:500],
                    )
                )

            if plumber_pdf is not None and page_number <= len(plumber_pdf.pages):
                table_chunks, table_terms = extract_table_chunks_for_page(
                    plumber_pdf.pages[page_number - 1],
                    page_number,
                    start_index=len(all_chunks),
                )
                all_chunks.extend(table_chunks)
                all_table_terms.extend(table_terms)

            if cleaned_text:
                text_chunks = build_text_chunks_for_page(
                    page_number,
                    cleaned_text,
                    start_index=len(all_chunks),
                )
                all_chunks.extend(text_chunks)

            image_chunks = extract_image_chunks_for_page(
                page,
                page_number,
                document_id=document.id,
                page_text=cleaned_text,
                storage_root=storage_root,
                start_index=len(all_chunks),
            )
            all_chunks.extend(image_chunks)
    finally:
        if plumber_pdf is not None:
            plumber_pdf.close()

    total_pages = len(parsed_pages)
    non_empty_pages = sum(
        1 for page in parsed_pages if page.status == DocumentPageStatus.READY
    )
    empty_pages = sum(
        1 for page in parsed_pages if page.status == DocumentPageStatus.EMPTY
    )
    failed_pages = sum(
        1 for page in parsed_pages if page.status == DocumentPageStatus.FAILED
    )
    total_chars = sum(page.char_count for page in parsed_pages)

    keywords = extract_document_keywords(
        document.title,
        [p.text for p in parsed_pages if p.text],
        table_values=all_table_terms,
    )

    if non_empty_pages == 0 and not all_chunks:
        document_status = DocumentStatus.FAILED
        parse_error = (
            "所有页面文本提取均报错"
            if failed_pages == total_pages
            else SCANNED_PDF_ERROR_MESSAGE
        )
    else:
        document_status = DocumentStatus.READY
        parse_error = None

    DocumentRepository.replace_pages(
        db,
        document,
        parsed_pages,
        chunks=all_chunks,
        keywords=keywords,
        status=document_status,
        parse_error=parse_error,
        page_count=total_pages,
    )

    text_chunks_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.TEXT)
    table_chunks_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.TABLE)
    image_chunks_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.IMAGE)

    return DocumentParseResponse(
        document=DocumentResponse.model_validate(document),
        total_pages=total_pages,
        non_empty_pages=non_empty_pages,
        empty_pages=empty_pages,
        failed_pages=failed_pages,
        total_chars=total_chars,
        keywords=keywords,
        total_chunks=len(all_chunks),
        text_chunks=text_chunks_count,
        table_chunks=table_chunks_count,
        image_chunks=image_chunks_count,
    )


def list_document_pages(db: Session, document: Document) -> DocumentPageListResponse:
    pages = DocumentRepository.list_pages(db, document.id)
    items = [DocumentPageResponse.model_validate(page) for page in pages]
    non_empty_pages = sum(
        1 for item in items if item.status == DocumentPageStatus.READY
    )
    total_chars = sum(item.char_count for item in items)

    return DocumentPageListResponse(
        document_id=document.id,
        document_status=DocumentStatus(document.status),
        parsed_at=document.parsed_at,
        parse_error=document.parse_error,
        total_pages=len(items),
        non_empty_pages=non_empty_pages,
        total_chars=total_chars,
        items=items,
    )


def list_document_chunks(
    db: Session,
    document: Document,
    *,
    chunk_type: DocumentChunkType | None = None,
) -> DocumentChunkListResponse:
    all_chunks = DocumentRepository.list_chunks(db, document.id)
    filtered = (
        [c for c in all_chunks if c.chunk_type == chunk_type.value]
        if chunk_type is not None
        else all_chunks
    )
    items = [DocumentChunkResponse.model_validate(chunk) for chunk in filtered]
    text_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.TEXT.value)
    table_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.TABLE.value)
    image_count = sum(1 for c in all_chunks if c.chunk_type == DocumentChunkType.IMAGE.value)

    return DocumentChunkListResponse(
        document_id=document.id,
        document_status=DocumentStatus(document.status),
        parsed_at=document.parsed_at,
        keywords=document.keywords,
        total_chunks=len(all_chunks),
        text_chunks=text_count,
        table_chunks=table_count,
        image_chunks=image_count,
        items=items,
    )
