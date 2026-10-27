export type DocumentStatus = "uploaded" | "processing" | "ready" | "failed";

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
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentRecord[];
  total: number;
  offset: number;
  limit: number;
}
