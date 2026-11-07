export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";
export type DocumentPageStatus = "ready" | "empty" | "failed";
export type DocumentChunkType = "text" | "table" | "image";

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
}

export interface ChunkSearchHit {
  chunk: DocumentChunkRecord;
  document_title: string;
  score: number;
  matched_keywords: string[];
}

export interface ChunkSearchResponse {
  query: string;
  extracted_keywords: string[];
  total: number;
  items: ChunkSearchHit[];
}
