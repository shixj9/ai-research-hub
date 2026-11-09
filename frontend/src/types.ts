export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";
export type DocumentPageStatus = "ready" | "empty" | "failed";
export type DocumentChunkType = "text" | "table" | "image";
export type SearchMode = "hybrid" | "semantic" | "keyword";

export interface DocumentRecord {
  id: string;
  title: string;
  original_filename: string | null;
  mime_type: string | null;
  file_size: number | null;
  page_count: number | null;
  sha256: string | null;
  storage_key: string | null;
  status: DocumentStatus;
  parsed_at: string | null;
  parse_error: string | null;
  keywords: string[];
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentRecord[];
  total: number;
  offset: number;
  limit: number;
}

export interface DocumentPageRecord {
  id: string;
  document_id: string;
  page_number: number;
  text: string;
  char_count: number;
  status: DocumentPageStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentPageListResponse {
  document_id: string;
  document_status: DocumentStatus;
  parsed_at: string | null;
  parse_error: string | null;
  total_pages: number;
  non_empty_pages: number;
  total_chars: number;
  items: DocumentPageRecord[];
}

export interface TableKeyValuePair {
  key: string;
  value: string;
}

export interface DocumentChunkMeta {
  headers?: string[];
  rows?: TableKeyValuePair[][];
  row_count?: number;
  col_count?: number;
  figure_name?: string;
  image_url?: string;
  width?: number;
  height?: number;
  caption?: string | null;
  ocr_status?: string;
  ocr_text?: string | null;
  vlm_description?: string | null;
  strategy?: string;
  paragraph_count?: number;
}

export interface DocumentChunkRecord {
  id: string;
  document_id: string;
  page_number: number;
  chunk_index: number;
  chunk_type: DocumentChunkType;
  title: string | null;
  content: string;
  char_count: number;
  meta: DocumentChunkMeta;
  has_embedding: boolean;
  embedding_model: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentChunkListResponse {
  document_id: string;
  document_status: DocumentStatus;
  parsed_at: string | null;
  keywords: string[];
  total_chunks: number;
  text_chunks: number;
  table_chunks: number;
  image_chunks: number;
  embedded_chunks: number;
  embedding_model: string | null;
  items: DocumentChunkRecord[];
}

export interface DocumentParseResponse {
  document: DocumentRecord;
  total_pages: number;
  non_empty_pages: number;
  empty_pages: number;
  failed_pages: number;
  total_chars: number;
  keywords: string[];
  total_chunks: number;
  text_chunks: number;
  table_chunks: number;
  image_chunks: number;
  embedded_chunks: number;
  embedding_model: string | null;
}

export interface ChunkSearchHit {
  chunk: DocumentChunkRecord;
  document_title: string;
  score: number;
  semantic_score: number;
  keyword_score: number;
  matched_keywords: string[];
}

export interface ChunkSearchResponse {
  query: string;
  mode: SearchMode;
  embedding_model: string;
  extracted_keywords: string[];
  total: number;
  items: ChunkSearchHit[];
}

export interface LLMPresetInfo {
  model: string;
  base_url: string;
  api_configured: boolean;
  api_key_masked: string;
  description: string;
}

export interface AIConfigSummary {
  config_file: string;
  active_embedding: string;
  embedding_model: string;
  embedding_type: string;
  embedding_dimensions: number;
  embedding_api_configured: boolean;
  active_llm: string;
  llm_model: string;
  llm_base_url: string;
  llm_api_configured: boolean;
  llm_api_key_masked?: string;
  available_embedding_providers: string[];
  available_llm_providers: string[];
  llm_presets?: Record<string, LLMPresetInfo>;
}

export interface AIConfigUpdatePayload {
  active_llm?: string;
  llm_model?: string;
  llm_base_url?: string;
  llm_api_key?: string;
  active_embedding?: string;
}


export interface RagCitation {
  citation_index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number;
  chunk_index: number;
  chunk_type: DocumentChunkType;
  title: string | null;
  snippet: string;
  score: number;
  semantic_score: number;
  keyword_score: number;
}

export interface RagAskResponse {
  question: string;
  answer: string;
  llm_provider: string;
  llm_model: string;
  used_extractive_fallback: boolean;
  llm_error?: string | null;
  retrieval_mode: SearchMode;
  embedding_model: string;
  citations: RagCitation[];
}
