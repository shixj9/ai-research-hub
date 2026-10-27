from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=1, max_length=300)]
    original_filename: Annotated[str | None, Field(max_length=500)] = None
    mime_type: Annotated[str | None, Field(max_length=100)] = None
    file_size: Annotated[int | None, Field(ge=0)] = None
    sha256: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None
    storage_key: Annotated[str | None, Field(max_length=1000)] = None
    status: DocumentStatus = DocumentStatus.UPLOADED


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Annotated[str | None, Field(min_length=1, max_length=300)] = None
    original_filename: Annotated[str | None, Field(max_length=500)] = None
    mime_type: Annotated[str | None, Field(max_length=100)] = None
    file_size: Annotated[int | None, Field(ge=0)] = None
    sha256: Annotated[str | None, Field(pattern=r"^[a-fA-F0-9]{64}$")] = None
    storage_key: Annotated[str | None, Field(max_length=1000)] = None
    status: DocumentStatus | None = None

    @field_validator("title", "status")
    @classmethod
    def required_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("field cannot be null")
        return value


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    original_filename: str | None
    mime_type: str | None
    file_size: int | None
    page_count: int | None
    sha256: str | None
    storage_key: str | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    offset: int
    limit: int
