import type {
  AgentRequest,
  AgentResponse,
  ConversationDetail,
  ConversationSummary,
  DocumentListResponse,
  DocumentSummary,
  HealthResponse,
  ReadinessResponse,
} from "../types/api";

const TOKEN_KEY = "enterprise-agent-session-token";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_UPLOAD_BYTES = Number(import.meta.env.VITE_MAX_UPLOAD_BYTES) || DEFAULT_MAX_UPLOAD_BYTES;
export const SESSION_EXPIRED_EVENT = "enterprise-agent:session-expired";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

function handleUnauthorized(): void {
  clearStoredToken();
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status}).`;
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === "string") message = detail;
      else if (Array.isArray(detail)) message = "Please review the submitted information and try again.";
    }
  } catch {
    // The server may return an empty or non-JSON error body.
  }
  if (response.status === 401) handleUnauthorized();
  return new ApiError(message, response.status);
}

async function request<T>(path: string, init: RequestInit = {}, bearerToken?: string): Promise<T> {
  const headers = new Headers(init.headers);
  const token = bearerToken ?? getStoredToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof Blob) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Could not reach the API. Check that the backend is running and the API URL is correct.", 0);
  }
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  getHealth: () => request<HealthResponse>("/health"),
  getReadiness: () => request<ReadinessResponse>("/ready"),
  listDocuments: () => request<DocumentListResponse>("/documents"),
  verifyToken: (token: string) => request<DocumentListResponse>("/documents", {}, token),
  deleteDocument: (documentId: string) =>
    request<void>(`/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" }),
  listConversations: async () => {
    const response = await request<{ conversations: ConversationSummary[] }>("/conversations");
    return response.conversations;
  },
  createConversation: (title = "New conversation") =>
    request<ConversationSummary>("/conversations", { method: "POST", body: JSON.stringify({ title }) }),
  getConversation: (conversationId: string) =>
    request<ConversationDetail>(`/conversations/${encodeURIComponent(conversationId)}`),
  deleteConversation: (conversationId: string) =>
    request<void>(`/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" }),
  runAgent: (body: AgentRequest) =>
    request<AgentResponse>("/agent", { method: "POST", body: JSON.stringify(body) }),
  uploadDocument: (file: File, onProgress: (percentage: number) => void) =>
    new Promise<DocumentSummary>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE_URL}/documents/upload`);
      xhr.setRequestHeader("X-Filename", file.name);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      const token = getStoredToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
      };
      xhr.onerror = () => reject(new ApiError("Upload failed because the API could not be reached.", 0));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as DocumentSummary);
          } catch {
            reject(new ApiError("The API returned an unreadable upload response.", xhr.status));
          }
          return;
        }
        let message = `Upload failed (${xhr.status}).`;
        try {
          const payload = JSON.parse(xhr.responseText) as { detail?: unknown };
          if (typeof payload.detail === "string") message = payload.detail;
        } catch {
          // Do not display raw response text.
        }
        if (xhr.status === 401) handleUnauthorized();
        reject(new ApiError(message, xhr.status));
      };
      xhr.send(file);
    }),
};

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}
