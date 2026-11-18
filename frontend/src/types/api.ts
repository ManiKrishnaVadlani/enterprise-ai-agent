export interface DocumentSummary {
  document_id: string;
  filename: string;
  ingested_at: string;
  chunk_count: number;
}

export interface DocumentListResponse {
  documents: DocumentSummary[];
  total: number;
}

export interface SourceReference {
  document_id: string;
  filename: string;
  chunk_id: string;
  page_number: number | null;
  relevance_score: number;
}

export interface AgentRequest {
  question: string;
  conversation_id?: string;
}

export interface AgentResponse {
  question: string;
  answer: string;
  sources: SourceReference[];
  conversation_id: string | null;
  workflow: {
    status: string;
    steps: number;
    tool_calls: number;
    tools: Array<{ name: string; status: string; result_count?: number }>;
    stop_reason: string;
  };
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface ReadinessResponse {
  status: string;
  database: string;
}

export interface HealthResponse {
  status: string;
  application: string;
}
