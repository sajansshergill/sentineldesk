import { mockRuns } from "./mock-data";
import type { ApprovalPayload, Run } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });

  if (!response.ok) {
    throw new Error(`API request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function listRuns(): Promise<Run[]> {
  if (!API_BASE_URL) {
    return mockRuns;
  }

  try {
    return await request<Run[]>("/runs");
  } catch {
    return mockRuns;
  }
}

export async function submitDecision(runId: string, payload: ApprovalPayload): Promise<Run> {
  if (!API_BASE_URL) {
    const current = mockRuns.find((run) => run.run_id === runId) ?? mockRuns[0];
    return {
      ...current,
      status: payload.decision === "rejected" ? "rejected" : "committed",
      decision: payload.decision,
      actor: payload.actor
    };
  }

  return request<Run>(`/runs/${runId}/decision`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
