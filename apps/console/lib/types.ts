export type Decision = "approved" | "approved_with_edits" | "rejected" | "pending";

export type RecommendedAction = "escalate" | "monitor" | "clear";

export type ReconcileStatus = "matched" | "mismatch" | "unmatched";

export type MessageType = "MT103" | "MT202" | "UNKNOWN";

export type CitationKind = "transaction" | "rule";

export interface Attachment {
  filename: string;
  content_type: string;
  content: string;
}

export interface InboundEmail {
  from: string;
  to: string;
  subject: string;
  received_at: string;
  body: string;
  attachments: Attachment[];
}

export interface ExtractedInstruction {
  reference: string | null;
  sender_bic: string | null;
  receiver_bic: string | null;
  currency: string | null;
  amount: number | null;
  value_date: string | null;
  message_type: MessageType;
  confidence: number;
  unresolved: string[];
  source: "body" | "attachment" | "mixed" | "none";
}

export interface Discrepancy {
  field: string;
  expected: string | number | null;
  observed: string | number | null;
  severity: "low" | "medium" | "high";
}

export interface ReconcileResult {
  status: ReconcileStatus;
  txn_id: string | null;
  candidates: string[];
  discrepancies: Discrepancy[];
}

export interface RuleHit {
  rule_id: string;
  label: string;
  severity: "low" | "medium" | "high";
  detail: string;
}

export interface ScoreResult {
  value: number;
  alert: boolean;
  model_score: number;
  feature_attribution: Array<{
    feature: string;
    impact: number;
  }>;
  rule_hits: RuleHit[];
}

export interface Citation {
  ref: string;
  kind: CitationKind;
}

export interface AnalystBrief {
  headline: string;
  summary: string;
  citations: Citation[];
  recommended_action: RecommendedAction;
  model_id: string;
}

export interface CrmDiffItem {
  field: string;
  current: string;
  proposed: string;
}

export interface StageTrace {
  agent: string;
  model: string | null;
  ok: boolean;
  latency_ms: number;
  tool_calls: string[];
}

export interface Run {
  run_id: string;
  status: "pending_approval" | "halted" | "committed" | "rejected";
  created_at: string;
  input_hash: string;
  final_score: number | null;
  alerts: boolean;
  decision: Decision;
  actor: string | null;
  email: InboundEmail;
  extraction: ExtractedInstruction | null;
  reconcile: ReconcileResult | null;
  score: ScoreResult | null;
  brief: AnalystBrief | null;
  crm_diff: CrmDiffItem[];
  stages: StageTrace[];
}

export interface ApprovalPayload {
  decision: Exclude<Decision, "pending">;
  actor: string;
  reason?: string;
  edits?: Record<string, string>;
}
