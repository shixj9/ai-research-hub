export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";
export type DocumentPageStatus = "ready" | "empty" | "failed";

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

export interface DocumentParseResponse {
  document: DocumentRecord;
  total_pages: number;
  non_empty_pages: number;
  empty_pages: number;
  failed_pages: number;
  total_chars: number;
}
