export interface Citation {
  ref: string;
  note: string;
  kind: "anomaly" | "aircraft" | "document" | "airport" | "trajectory" | "observations" | "other";
  link: string | null;
}
export interface ToolCall {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  error: string | null;
  records: string[];
}
export interface ChatReply {
  conversation_id: string;
  answer: string;
  citations: Citation[];
  tool_calls: ToolCall[];
  warnings: string[];
  provider: string;
  model: string;
  ai_generated: true;
  disclaimer: string;
}
export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name: string | null;
  tool_args: Record<string, unknown> | null;
  citations: Citation[] | null;
  warnings: string[] | null;
  provider: string | null;
  model: string | null;
  created_at: string;
}
export interface Conversation {
  id: string;
  title: string;
  owner: string;
  created_at: string;
}
export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}
export interface IntelItem {
  id: number;
  source_name: string;
  source_url: string;
  title: string;
  authors: string | null;
  publication_date: string | null;
  retrieved_at: string;
  excerpt: string;
  reliability_notes: string;
  tags: string[];
  origin: string;
  added_by: string;
}
export type Block =
  | { type: "paragraph"; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "table"; columns: string[]; rows: string[][] };
export interface ReportSection {
  id: string;
  title: string;
  provenance: "VERIFIED_PLATFORM_DATA" | "AI_GENERATED_UNVERIFIED";
  blocks: Block[];
}
export interface ReportMeta {
  id: number;
  title: string;
  subject_type: "anomaly" | "aircraft";
  subject: string;
  created_by: string;
  created_at: string;
  includes_ai: boolean;
  status: string;
}
export interface Report extends ReportMeta {
  structured: { title: string; notice: string; status: string; generated_at: string; sections: ReportSection[] };
  markdown: string;
}
