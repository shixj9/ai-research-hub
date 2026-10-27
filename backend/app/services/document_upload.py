import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.document import Document
from backend.app.repositories.document import DocumentRepository
from backend.app.schemas.document import DocumentCreate

READ_CHUNK_SIZE = 1024 * 1024
PDF_HEADER_SCAN_SIZE = 1024


class PdfUploadError(Exception):
    """Base exception for expected PDF upload failures."""


class InvalidPdfError(PdfUploadError):
    """The uploaded content is not a supported, readable PDF."""


class PdfTooLargeError(PdfUploadError):
    """The uploaded PDF exceeds the configured size limit."""


class DuplicateDocumentError(PdfUploadError):
    def __init__(self, document_id) -> None:
        super().__init__(f"This PDF already exists as document {document_id}")
        self.document_id = document_id


class PdfStorageError(PdfUploadError):
    """The file or metadata could not be persisted."""


def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise InvalidPdfError("A PDF filename is required")

    normalized = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
    if not normalized or len(normalized) > 500:
        raise InvalidPdfError("The PDF filename is invalid or too long")
    if Path(normalized).suffix.lower() != ".pdf":
        raise InvalidPdfError("Only files with a .pdf extension are accepted")
    return normalized


def _write_upload_to_temp(
    source: BinaryIO,
    temporary_path: Path,
    max_size_bytes: int,
) -> tuple[int, str]:
    size = 0
    digest = hashlib.sha256()
    source.seek(0)

    with temporary_path.open("wb") as destination:
        first_chunk = source.read(READ_CHUNK_SIZE)
        if not first_chunk:
            raise InvalidPdfError("The uploaded PDF is empty")
        if b"%PDF-" not in first_chunk[:PDF_HEADER_SCAN_SIZE]:
            raise InvalidPdfError("The uploaded file does not contain a valid PDF header")

        for chunk in (first_chunk,):
            size += len(chunk)
            if size > max_size_bytes:
                raise PdfTooLargeError(
                    f"PDF exceeds the {max_size_bytes // (1024 * 1024)} MB upload limit"
                )
            digest.update(chunk)
            destination.write(chunk)

        while chunk := source.read(READ_CHUNK_SIZE):
            size += len(chunk)
            if size > max_size_bytes:
                raise PdfTooLargeError(
                    f"PDF exceeds the {max_size_bytes // (1024 * 1024)} MB upload limit"
                )
            digest.update(chunk)
            destination.write(chunk)

    return size, digest.hexdigest()


def _validate_pdf(temporary_path: Path) -> int:
    try:
        reader = PdfReader(temporary_path, strict=False)
        if reader.is_encrypted:
            raise InvalidPdfError("Encrypted PDFs are not supported yet")
        page_count = len(reader.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise InvalidPdfError("The uploaded file is not a readable PDF") from exc

    if page_count < 1:
        raise InvalidPdfError("The PDF must contain at least one page")
    return page_count


def save_pdf_document(
    db: Session,
    upload: UploadFile,
    *,
    title: str | None,
    storage_root: Path,
    max_size_bytes: int,
) -> Document:
    original_filename = _safe_filename(upload.filename)
    document_title = (title or Path(original_filename).stem).strip()
    if not document_title:
        document_title = "Untitled document"
    document_title = document_title[:300]

    temporary_directory = storage_root / "tmp"
    temporary_directory.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix="pdf-upload-",
        suffix=".tmp",
        dir=temporary_directory,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    final_path: Path | None = None
    final_path_existed = False
    try:
        file_size, sha256 = _write_upload_to_temp(
            upload.file,
            temporary_path,
            max_size_bytes,
        )
        page_count = _validate_pdf(temporary_path)

        duplicate = DocumentRepository.get_by_sha256(db, sha256)
        if duplicate is not None:
            raise DuplicateDocumentError(duplicate.id)

        storage_key = f"blobs/{sha256[:2]}/{sha256}.pdf"
        final_path = storage_root / Path(storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path_existed = final_path.exists()
        if not final_path_existed:
            os.replace(temporary_path, final_path)

        payload = DocumentCreate(
            title=document_title,
            original_filename=original_filename,
            mime_type="application/pdf",
            file_size=file_size,
            sha256=sha256,
            storage_key=storage_key,
            status="uploaded",
        )

        try:
            return DocumentRepository.create(db, payload, page_count=page_count)
        except IntegrityError as exc:
            db.rollback()
            duplicate = DocumentRepository.get_by_sha256(db, sha256)
            if duplicate is not None:
                raise DuplicateDocumentError(duplicate.id) from exc
            if final_path is not None and not final_path_existed:
                final_path.unlink(missing_ok=True)
            raise PdfStorageError("Unable to save PDF metadata") from exc
    except OSError as exc:
        raise PdfStorageError("Unable to write PDF to local storage") from exc
    finally:
        temporary_path.unlink(missing_ok=True)

