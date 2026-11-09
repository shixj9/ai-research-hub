import type {
  AIConfigSummary,
  ChunkSearchResponse,
  DocumentChunkListResponse,
  DocumentChunkType,
  DocumentListResponse,
  DocumentPageListResponse,
  DocumentParseResponse,
  DocumentRecord,
  SearchMode,
} from "./types";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "/api/v1"
).replace(/\/$/, "");

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
  } catch {
    // The fallback below is clearer for non-JSON server errors.
  }
  return `请求失败（HTTP ${response.status}）`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) throw new Error(await parseError(response));
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function checkBackend(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export function getAIConfig(): Promise<AIConfigSummary> {
  return request<AIConfigSummary>("/documents/ai-config");
}

export function updateAIConfig(
  payload: import("./types").AIConfigUpdatePayload,
): Promise<AIConfigSummary> {
  return request<AIConfigSummary>("/documents/ai-config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function listDocuments(): Promise<DocumentListResponse> {
  return request<DocumentListResponse>("/documents?limit=100");
}

export function uploadDocument(file: File, title: string): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("file", file);
  if (title.trim()) body.append("title", title.trim());
  return request<DocumentRecord>("/documents/upload", { method: "POST", body });
}

export function deleteDocument(documentId: string): Promise<void> {
  return request<void>(`/documents/${documentId}`, { method: "DELETE" });
}

export function parseDocument(documentId: string): Promise<DocumentParseResponse> {
  return request<DocumentParseResponse>(`/documents/${documentId}/parse`, {
    method: "POST",
  });
}

export function listDocumentPages(documentId: string): Promise<DocumentPageListResponse> {
  return request<DocumentPageListResponse>(`/documents/${documentId}/pages`);
}

export function listDocumentChunks(
  documentId: string,
  chunkType?: DocumentChunkType,
): Promise<DocumentChunkListResponse> {
  const query = chunkType ? `?chunk_type=${encodeURIComponent(chunkType)}` : "";
  return request<DocumentChunkListResponse>(`/documents/${documentId}/chunks${query}`);
}

export function searchDocumentChunks(
  q: string,
  options?: {
    documentId?: string;
    chunkType?: DocumentChunkType;
    mode?: SearchMode;
  },
): Promise<ChunkSearchResponse> {
  const params = new URLSearchParams({ q });
  if (options?.documentId) params.set("document_id", options.documentId);
  if (options?.chunkType) params.set("chunk_type", options.chunkType);
  if (options?.mode) params.set("mode", options.mode);
  return request<ChunkSearchResponse>(`/documents/search?${params.toString()}`);
}

export function documentFileUrl(documentId: string, pageNumber?: number): string {
  const base = `${API_BASE_URL}/documents/${documentId}/file`;
  return pageNumber && pageNumber >= 1 ? `${base}#page=${pageNumber}` : base;
}


export function askDocumentQuestion(
  documentId: string,
  question: string,
  mode: SearchMode = "hybrid",
  topK = 4,
): Promise<import("./types").RagAskResponse> {
  return request<import("./types").RagAskResponse>(`/documents/${documentId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode, top_k: topK }),
  });
}
