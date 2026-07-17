import type { Run } from "./types";

export const mockRuns: Run[] = [
  {
    run_id: "run_9f2a1c",
    status: "pending_approval",
    created_at: "2026-07-16T13:42:11Z",
    input_hash: "sha256:7c9d1d9b3d22",
    final_score: 0.91,
    alerts: true,
    decision: "pending",
    actor: null,
    email: {
      from: "ops@centralbank-nord.example",
      to: "settlements@sentineldesk.example",
      subject: "MT202 settlement confirmation REF NCB-77421",
      received_at: "2026-07-16T13:40:02Z",
      body:
        "Please confirm receipt of MT202 settlement instruction NCB-77421 for USD 9,950,000.00 value date 2026-07-17. Sender BIC CBNORD33, receiver BIC SNTLUS33.",
      attachments: [
        {
          filename: "mt202-confirmation.txt",
          content_type: "text/plain",
          content: ":20:NCB-77421\n:32A:260717USD9950000,00\n:52A:CBNORD33\n:58A:SNTLUS33"
        }
      ]
    },
    extraction: {
      reference: "NCB-77421",
      sender_bic: "CBNORD33",
      receiver_bic: "SNTLUS33",
      currency: "USD",
      amount: 9950000,
      value_date: "2026-07-17",
      message_type: "MT202",
      confidence: 0.96,
      unresolved: [],
      source: "mixed"
    },
    reconcile: {
      status: "mismatch",
      txn_id: "txn_71ba0f",
      candidates: ["txn_71ba0f", "txn_2eb774"],
      discrepancies: [
        {
          field: "amount",
          expected: 9950000,
          observed: 995000,
          severity: "high"
        }
      ]
    },
    score: {
      value: 0.91,
      alert: true,
      model_score: 0.78,
      feature_attribution: [
        { feature: "amount_zscore_corridor", impact: 0.34 },
        { feature: "round_number_bias", impact: 0.22 },
        { feature: "days_since_last_seen", impact: 0.16 }
      ],
      rule_hits: [
        {
          rule_id: "rule_amount_transposition",
          label: "Possible amount transposition",
          severity: "high",
          detail: "Ledger amount differs by one decimal place from the instruction."
        },
        {
          rule_id: "rule_round_amount",
          label: "Round-number bias",
          severity: "medium",
          detail: "Instruction amount falls on a high-value round threshold."
        }
      ]
    },
    brief: {
      headline: "High-risk amount mismatch on MT202 settlement",
      summary:
        "The instruction references NCB-77421 for USD 9.95M, but the nearest ledger transaction records USD 995K. The difference matches a transposition pattern and should be escalated before any CRM update is committed.",
      citations: [
        { ref: "txn_71ba0f", kind: "transaction" },
        { ref: "rule_amount_transposition", kind: "rule" }
      ],
      recommended_action: "escalate",
      model_id: "bedrock:anthropic.claude-3-5-sonnet"
    },
    crm_diff: [
      { field: "case_status", current: "Open", proposed: "Escalated" },
      { field: "risk_rating", current: "Medium", proposed: "High" },
      {
        field: "analyst_summary",
        current: "Awaiting review",
        proposed: "Amount mismatch detected for NCB-77421; escalation recommended."
      }
    ],
    stages: [
      { agent: "ingest", model: null, ok: true, latency_ms: 43, tool_calls: [] },
      {
        agent: "extract",
        model: "bedrock:anthropic.claude-3-5-sonnet",
        ok: true,
        latency_ms: 1180,
        tool_calls: ["schema_validate"]
      },
      { agent: "reconcile", model: null, ok: true, latency_ms: 212, tool_calls: ["ledger.lookup"] },
      { agent: "score", model: "isolation-forest:v1", ok: true, latency_ms: 87, tool_calls: ["rules.evaluate"] },
      {
        agent: "summarize",
        model: "bedrock:anthropic.claude-3-5-sonnet",
        ok: true,
        latency_ms: 940,
        tool_calls: ["citations.validate"]
      },
      { agent: "approval", model: null, ok: true, latency_ms: 0, tool_calls: [] }
    ]
  },
  {
    run_id: "run_31a820",
    status: "pending_approval",
    created_at: "2026-07-16T12:18:45Z",
    input_hash: "sha256:a103ab41dd90",
    final_score: 0.28,
    alerts: false,
    decision: "pending",
    actor: null,
    email: {
      from: "payments@pacific-reserve.example",
      to: "settlements@sentineldesk.example",
      subject: "MT103 customer transfer PRB-22018",
      received_at: "2026-07-16T12:16:03Z",
      body:
        "MT103 instruction PRB-22018. Please process EUR 742,114.30 value date 2026-07-18. Sender PRCBGB2L, receiver SNTLUS33.",
      attachments: []
    },
    extraction: {
      reference: "PRB-22018",
      sender_bic: "PRCBGB2L",
      receiver_bic: "SNTLUS33",
      currency: "EUR",
      amount: 742114.3,
      value_date: "2026-07-18",
      message_type: "MT103",
      confidence: 0.93,
      unresolved: [],
      source: "body"
    },
    reconcile: {
      status: "matched",
      txn_id: "txn_c41d02",
      candidates: ["txn_c41d02"],
      discrepancies: []
    },
    score: {
      value: 0.28,
      alert: false,
      model_score: 0.22,
      feature_attribution: [
        { feature: "corridor_frequency", impact: 0.09 },
        { feature: "hour_of_day", impact: 0.05 },
        { feature: "log_amount", impact: 0.04 }
      ],
      rule_hits: []
    },
    brief: {
      headline: "Matched MT103 transfer with no rule alerts",
      summary:
        "The extracted EUR instruction matches ledger transaction txn_c41d02 with no discrepancies or triggered deterministic rules. Monitoring is sufficient.",
      citations: [{ ref: "txn_c41d02", kind: "transaction" }],
      recommended_action: "monitor",
      model_id: "bedrock:anthropic.claude-3-5-sonnet"
    },
    crm_diff: [
      { field: "case_status", current: "Open", proposed: "Ready for closure" },
      { field: "risk_rating", current: "Low", proposed: "Low" }
    ],
    stages: [
      { agent: "ingest", model: null, ok: true, latency_ms: 38, tool_calls: [] },
      {
        agent: "extract",
        model: "bedrock:anthropic.claude-3-5-sonnet",
        ok: true,
        latency_ms: 1044,
        tool_calls: ["schema_validate"]
      },
      { agent: "reconcile", model: null, ok: true, latency_ms: 145, tool_calls: ["ledger.lookup"] },
      { agent: "score", model: "isolation-forest:v1", ok: true, latency_ms: 78, tool_calls: ["rules.evaluate"] },
      {
        agent: "summarize",
        model: "bedrock:anthropic.claude-3-5-sonnet",
        ok: true,
        latency_ms: 821,
        tool_calls: ["citations.validate"]
      },
      { agent: "approval", model: null, ok: true, latency_ms: 0, tool_calls: [] }
    ]
  }
];
