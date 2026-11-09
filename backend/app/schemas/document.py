from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentPageStatus(StrEnum):
    READY = "ready"
    EMPTY = "empty"
    FAILED = "failed"


class DocumentChunkType(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGE = "image"


class SearchMode(StrEnum):
    HYBRID = "hybrid"
    SEMANTIC = "semantic"
    KEYWORD = "keyword"


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
    parsed_at: datetime | None = None
    parse_error: str | None = None
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    offset: int
    limit: int


class DocumentPageCreate(BaseModel):
    page_number: Annotated[int, Field(ge=1)]
    text: str = ""
    char_count: Annotated[int, Field(ge=0)] = 0
    status: DocumentPageStatus = DocumentPageStatus.READY
    error_message: Annotated[str | None, Field(max_length=500)] = None


class DocumentPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    page_number: int
    text: str
    char_count: int
    status: DocumentPageStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class DocumentPageListResponse(BaseModel):
    document_id: UUID
    document_status: DocumentStatus
    parsed_at: datetime | None
    parse_error: str | None
    total_pages: int
    non_empty_pages: int
    total_chars: int
    items: list[DocumentPageResponse]


class DocumentChunkCreate(BaseModel):
    page_number: Annotated[int, Field(ge=1)]
    chunk_index: Annotated[int, Field(ge=0)]
    chunk_type: DocumentChunkType = DocumentChunkType.TEXT
    title: Annotated[str | None, Field(max_length=300)] = None
    content: str = ""
    char_count: Annotated[int, Field(ge=0)] = 0
    meta: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    embedding_model: str | None = None


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    page_number: int
    chunk_index: int
    chunk_type: DocumentChunkType
    title: str | None
    content: str
    char_count: int
    meta: dict[str, Any] = Field(default_factory=dict)
    has_embedding: bool = False
    embedding_model: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentChunkListResponse(BaseModel):
    document_id: UUID
    document_status: DocumentStatus
    parsed_at: datetime | None
    keywords: list[str] = Field(default_factory=list)
    total_chunks: int
    text_chunks: int
    table_chunks: int
    image_chunks: int
    embedded_chunks: int = 0
    embedding_model: str | None = None
    items: list[DocumentChunkResponse]


class DocumentParseResponse(BaseModel):
    document: DocumentResponse
    total_pages: int
    non_empty_pages: int
    empty_pages: int
    failed_pages: int
    total_chars: int
    keywords: list[str] = Field(default_factory=list)
    total_chunks: int = 0
    text_chunks: int = 0
    table_chunks: int = 0
    image_chunks: int = 0
    embedded_chunks: int = 0
    embedding_model: str | None = None


class ChunkSearchHit(BaseModel):
    chunk: DocumentChunkResponse
    document_title: str
    score: float
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)


class ChunkSearchResponse(BaseModel):
    query: str
    mode: SearchMode = SearchMode.HYBRID
    embedding_model: str = "local_bilingual:bilingual-semantic-256d"
    extracted_keywords: list[str]
    total: int
    items: list[ChunkSearchHit]


class AIConfigSummaryResponse(BaseModel):
    config_file: str
    active_embedding: str
    embedding_model: str
    embedding_type: str
    embedding_dimensions: int
    embedding_api_configured: bool
    active_llm: str
    llm_model: str
    llm_base_url: str
    llm_api_configured: bool
    llm_api_key_masked: str = ""
    available_embedding_providers: list[str]
    available_llm_providers: list[str]
    llm_presets: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AIConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    active_llm: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    active_embedding: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None



class RagAskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: Annotated[str, Field(min_length=1, max_length=500)]
    document_id: UUID | None = None
    mode: SearchMode = SearchMode.HYBRID
    top_k: Annotated[int, Field(ge=1, le=12)] = 5


class RagCitation(BaseModel):
    citation_index: int
    chunk_id: UUID
    document_id: UUID
    document_title: str
    page_number: int
    chunk_index: int
    chunk_type: DocumentChunkType
    title: str | None = None
    snippet: str
    score: float
    semantic_score: float = 0.0
    keyword_score: float = 0.0


class RagAskResponse(BaseModel):
    question: str
    answer: str
    llm_provider: str
    llm_model: str
    used_extractive_fallback: bool
    llm_error: str | None = None
    retrieval_mode: SearchMode
    embedding_model: str
    citations: list[RagCitation] = Field(default_factory=list)
