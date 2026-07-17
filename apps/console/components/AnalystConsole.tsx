"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { listRuns, submitDecision } from "@/lib/api";
import { formatCurrency, formatDateTime, formatPercent, titleCase } from "@/lib/format";
import type { ApprovalPayload, Decision, Run, RuleHit } from "@/lib/types";

const ACTOR = "analyst.demo";

export function AnalystConsole() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [summaryEdit, setSummaryEdit] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: listRuns
  });

  const runs = runsQuery.data ?? [];
  const selectedRun = useMemo(() => {
    return runs.find((run) => run.run_id === selectedRunId) ?? runs[0] ?? null;
  }, [runs, selectedRunId]);

  const decisionMutation = useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: ApprovalPayload }) =>
      submitDecision(runId, payload),
    onSuccess: (run) => {
      setNotice(`Decision saved for ${run.run_id}: ${titleCase(run.decision)}.`);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
    }
  });

  function handleDecision(decision: Exclude<Decision, "pending">) {
    if (!selectedRun) {
      return;
    }

    const edits = summaryEdit.trim() ? { analyst_summary: summaryEdit.trim() } : undefined;
    decisionMutation.mutate({
      runId: selectedRun.run_id,
      payload: {
        decision,
        actor: ACTOR,
        reason: reason.trim() || undefined,
        edits
      }
    });
  }

  return (
    <main className="min-h-screen px-6 py-6 lg:px-8">
      <header className="mx-auto mb-6 flex max-w-7xl flex-col gap-4 rounded-3xl border border-white/70 bg-white/85 p-6 shadow-panel backdrop-blur md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-blue-700">
            SentinelDesk
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
            Analyst Console
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Review agent runs, verify cited evidence, and approve or reject the proposed CRM write.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <Metric label="Pending" value={String(runs.filter((run) => run.decision === "pending").length)} />
          <Metric label="Alerts" value={String(runs.filter((run) => run.alerts).length)} />
          <Metric label="Actor" value={ACTOR} compact />
        </div>
      </header>

      {notice ? (
        <div className="mx-auto mb-4 max-w-7xl rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          {notice}
        </div>
      ) : null}

      <section className="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="rounded-3xl border border-white/70 bg-white/90 p-4 shadow-panel">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">Queue</h2>
              <p className="text-sm text-slate-500">Ranked by anomaly score</p>
            </div>
            <StatusPill label={runsQuery.isFetching ? "Syncing" : "Live"} tone="blue" />
          </div>

          <div className="space-y-3">
            {runs.map((run) => (
              <button
                key={run.run_id}
                type="button"
                onClick={() => {
                  setSelectedRunId(run.run_id);
                  setSummaryEdit(run.brief?.summary ?? "");
                  setReason("");
                  setNotice(null);
                }}
                className={`w-full rounded-2xl border p-4 text-left transition ${
                  selectedRun?.run_id === run.run_id
                    ? "border-blue-400 bg-blue-50"
                    : "border-slate-200 bg-white hover:border-blue-200 hover:bg-slate-50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">{run.brief?.headline ?? run.email.subject}</p>
                    <p className="mt-1 text-xs text-slate-500">{formatDateTime(run.created_at)}</p>
                  </div>
                  <ScoreBadge score={run.final_score} alert={run.alerts} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusPill label={titleCase(run.status)} tone={run.alerts ? "red" : "slate"} />
                  <StatusPill label={run.extraction?.message_type ?? "UNKNOWN"} tone="slate" />
                  {run.score?.rule_hits.slice(0, 2).map((rule) => (
                    <StatusPill key={rule.rule_id} label={rule.label} tone="amber" />
                  ))}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {selectedRun ? (
          <RunWorkspace
            run={selectedRun}
            reason={reason}
            summaryEdit={summaryEdit || selectedRun.brief?.summary || ""}
            isSaving={decisionMutation.isPending}
            onReasonChange={setReason}
            onSummaryEditChange={setSummaryEdit}
            onDecision={handleDecision}
          />
        ) : (
          <EmptyState />
        )}
      </section>
    </main>
  );
}

function RunWorkspace({
  run,
  reason,
  summaryEdit,
  isSaving,
  onReasonChange,
  onSummaryEditChange,
  onDecision
}: {
  run: Run;
  reason: string;
  summaryEdit: string;
  isSaving: boolean;
  onReasonChange: (value: string) => void;
  onSummaryEditChange: (value: string) => void;
  onDecision: (decision: Exclude<Decision, "pending">) => void;
}) {
  return (
    <div className="space-y-6">
      <Panel>
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{run.run_id}</p>
            <h2 className="mt-1 text-2xl font-bold text-slate-950">
              {run.brief?.headline ?? run.email.subject}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              {run.email.from} to {run.email.to}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <StatusPill label={titleCase(run.decision)} tone={run.decision === "pending" ? "amber" : "green"} />
            <StatusPill label={`Hash ${run.input_hash}`} tone="slate" />
          </div>
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Extracted Instruction">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <Field label="Reference" value={run.extraction?.reference} />
            <Field label="Type" value={run.extraction?.message_type} />
            <Field label="Sender BIC" value={run.extraction?.sender_bic} />
            <Field label="Receiver BIC" value={run.extraction?.receiver_bic} />
            <Field
              label="Amount"
              value={formatCurrency(run.extraction?.amount ?? null, run.extraction?.currency ?? null)}
            />
            <Field label="Value Date" value={run.extraction?.value_date} />
            <Field label="Source" value={run.extraction?.source} />
            <Field label="Confidence" value={formatPercent(run.extraction?.confidence ?? 0)} />
          </dl>
          {run.extraction?.unresolved.length ? (
            <div className="mt-4 rounded-2xl bg-amber-50 p-3 text-sm text-amber-900">
              Unresolved: {run.extraction.unresolved.join(", ")}
            </div>
          ) : null}
        </Panel>

        <Panel title="Reconciliation">
          <div className="flex items-center justify-between">
            <StatusPill
              label={titleCase(run.reconcile?.status ?? "unmatched")}
              tone={run.reconcile?.status === "matched" ? "green" : "red"}
            />
            <p className="text-sm text-slate-500">Transaction {run.reconcile?.txn_id ?? "none"}</p>
          </div>
          <div className="mt-4 space-y-3">
            {run.reconcile?.discrepancies.length ? (
              run.reconcile.discrepancies.map((item) => (
                <div key={item.field} className="rounded-2xl border border-red-100 bg-red-50 p-3">
                  <p className="font-medium text-red-950">{titleCase(item.field)}</p>
                  <p className="mt-1 text-sm text-red-800">
                    Expected {String(item.expected)} but observed {String(item.observed)}
                  </p>
                </div>
              ))
            ) : (
              <p className="rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-800">
                Ledger transaction matched without discrepancies.
              </p>
            )}
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.9fr)]">
        <Panel title="Analyst Brief">
          <p className="text-sm leading-6 text-slate-700">{run.brief?.summary}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {run.brief?.citations.map((citation) => (
              <a
                key={`${citation.kind}-${citation.ref}`}
                href={`#${citation.ref}`}
                className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-800"
              >
                {citation.kind}: {citation.ref}
              </a>
            ))}
          </div>
          <label className="mt-5 block text-sm font-semibold text-slate-700" htmlFor="summary-edit">
            Edit proposed CRM summary
          </label>
          <textarea
            id="summary-edit"
            value={summaryEdit}
            onChange={(event) => onSummaryEditChange(event.target.value)}
            className="mt-2 min-h-28 w-full rounded-2xl border border-slate-200 bg-white p-3 text-sm outline-none ring-blue-200 focus:ring-4"
          />
        </Panel>

        <Panel title="Score and Rules">
          <div className="flex items-center gap-4">
            <div className="grid h-24 w-24 place-items-center rounded-full bg-slate-950 text-white">
              <div className="text-center">
                <p className="text-2xl font-bold">{formatPercent(run.score?.value ?? 0)}</p>
                <p className="text-xs text-slate-300">risk</p>
              </div>
            </div>
            <div>
              <p className="text-sm text-slate-500">Model score</p>
              <p className="text-xl font-semibold text-slate-950">
                {formatPercent(run.score?.model_score ?? 0)}
              </p>
              <p className="mt-1 text-sm text-slate-600">
                Recommended action: {titleCase(run.brief?.recommended_action ?? "monitor")}
              </p>
            </div>
          </div>
          <RuleHits rules={run.score?.rule_hits ?? []} />
          <div className="mt-4 space-y-2">
            {run.score?.feature_attribution.map((feature) => (
              <div key={feature.feature}>
                <div className="flex justify-between text-xs text-slate-500">
                  <span>{titleCase(feature.feature)}</span>
                  <span>{formatPercent(feature.impact)}</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-blue-600"
                    style={{ width: `${Math.min(feature.impact * 100, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="CRM Diff">
          <div className="space-y-3">
            {run.crm_diff.map((item) => (
              <div key={item.field} className="rounded-2xl border border-slate-200 p-3" id={item.field}>
                <p className="font-semibold text-slate-950">{titleCase(item.field)}</p>
                <div className="mt-2 grid gap-2 text-sm md:grid-cols-2">
                  <p className="rounded-xl bg-slate-100 p-2 text-slate-600">{item.current}</p>
                  <p className="rounded-xl bg-blue-50 p-2 text-blue-900">{item.proposed}</p>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Audit Trace">
          <ol className="space-y-3">
            {run.stages.map((stage) => (
              <li key={stage.agent} className="rounded-2xl border border-slate-200 bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">{titleCase(stage.agent)}</p>
                    <p className="text-xs text-slate-500">{stage.model ?? "deterministic"}</p>
                  </div>
                  <StatusPill label={`${stage.latency_ms} ms`} tone={stage.ok ? "green" : "red"} />
                </div>
                {stage.tool_calls.length ? (
                  <p className="mt-2 text-xs text-slate-500">Tools: {stage.tool_calls.join(", ")}</p>
                ) : null}
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      <Panel title="Actions">
        <label className="block text-sm font-semibold text-slate-700" htmlFor="decision-reason">
          Decision reason
        </label>
        <input
          id="decision-reason"
          value={reason}
          onChange={(event) => onReasonChange(event.target.value)}
          placeholder="Required for rejection, useful for eval feedback"
          className="mt-2 w-full rounded-2xl border border-slate-200 bg-white p-3 text-sm outline-none ring-blue-200 focus:ring-4"
        />
        <div className="mt-4 flex flex-wrap gap-3">
          <ActionButton disabled={isSaving} tone="green" onClick={() => onDecision("approved")}>
            Approve
          </ActionButton>
          <ActionButton disabled={isSaving} tone="blue" onClick={() => onDecision("approved_with_edits")}>
            Approve with edits
          </ActionButton>
          <ActionButton disabled={isSaving} tone="red" onClick={() => onDecision("rejected")}>
            Reject
          </ActionButton>
        </div>
      </Panel>
    </div>
  );
}

function RuleHits({ rules }: { rules: RuleHit[] }) {
  if (!rules.length) {
    return <p className="mt-4 rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-800">No rule hits.</p>;
  }

  return (
    <div className="mt-4 space-y-2">
      {rules.map((rule) => (
        <div key={rule.rule_id} id={rule.rule_id} className="rounded-2xl border border-amber-200 bg-amber-50 p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="font-semibold text-amber-950">{rule.label}</p>
            <StatusPill label={rule.severity} tone={rule.severity === "high" ? "red" : "amber"} />
          </div>
          <p className="mt-1 text-sm text-amber-900">{rule.detail}</p>
        </div>
      ))}
    </div>
  );
}

function Panel({
  title,
  children
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 p-5 shadow-panel">
      {title ? <h3 className="mb-4 text-lg font-semibold text-slate-950">{title}</h3> : null}
      {children}
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 font-semibold text-slate-950">{value ?? "Unresolved"}</dd>
    </div>
  );
}

function Metric({ label, value, compact = false }: { label: string; value: string; compact?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 font-bold text-slate-950 ${compact ? "text-sm" : "text-2xl"}`}>{value}</p>
    </div>
  );
}

function ScoreBadge({ score, alert }: { score: number | null; alert: boolean }) {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold ${
        alert ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"
      }`}
    >
      {score === null ? "N/A" : formatPercent(score)}
    </span>
  );
}

function StatusPill({ label, tone }: { label: string; tone: "amber" | "blue" | "green" | "red" | "slate" }) {
  const classes = {
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    blue: "border-blue-200 bg-blue-50 text-blue-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    red: "border-red-200 bg-red-50 text-red-800",
    slate: "border-slate-200 bg-slate-50 text-slate-700"
  };

  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${classes[tone]}`}>
      {label}
    </span>
  );
}

function ActionButton({
  children,
  disabled,
  tone,
  onClick
}: {
  children: ReactNode;
  disabled: boolean;
  tone: "blue" | "green" | "red";
  onClick: () => void;
}) {
  const classes = {
    blue: "bg-blue-700 hover:bg-blue-800",
    green: "bg-emerald-700 hover:bg-emerald-800",
    red: "bg-red-700 hover:bg-red-800"
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-2xl px-4 py-3 text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-60 ${classes[tone]}`}
    >
      {disabled ? "Saving..." : children}
    </button>
  );
}

function EmptyState() {
  return (
    <Panel>
      <div className="py-16 text-center">
        <p className="text-lg font-semibold text-slate-950">No runs available</p>
        <p className="mt-2 text-sm text-slate-500">New interrupted graph runs will appear here.</p>
      </div>
    </Panel>
  );
}
