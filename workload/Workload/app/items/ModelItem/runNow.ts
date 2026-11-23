/**
 * ED3 (Gustav, 21 November 2026, after Create: "sen kanske se resultatet?"): Run now on a notebook or pipeline Krusgraph
 * created. Pure functions (runNow.test.ts): the states a run goes through, one line per state with Fabric's message once,
 * when to read it again, and the preview of the table the run wrote. Never automatic: only the person's click starts a
 * run (POST /workload/v1/run, fabric_backend/workload_api.run_item, Fabric's Job Scheduler as the signed-in user).
 */

export type RunState = "idle" | "starting" | "queued" | "running" | "succeeded" | "failed" | "unknown" | "refused";

export const RUN_ONLY_WHEN = "Krusgraph runs it only when you choose Run now.";

/** What the engine answers for a run (start or read). */
export interface RunAnswer {
  state: "queued" | "running" | "succeeded" | "failed" | "unknown";
  run_id?: string;
  words?: string;
  message?: string;
  preview?: RunPreview;
}

export interface RunPreview {
  table: string;
  columns?: string[];
  rows?: Record<string, unknown>[];
  row_count?: number;
  missing?: boolean;
  words?: string;
  personal_data?: { notice?: string; masked?: boolean };
}

/** The item types Run now runs: notebooks and pipelines Krusgraph created. */
export const RUNNABLE = ["Notebook", "DataPipeline"];

export function runnable(type: string | undefined): boolean {
  return !!type && RUNNABLE.includes(type);
}

export interface RunView {
  state: RunState;
  runId?: string;
  line?: string;
  message?: string;
  preview?: RunPreview;
  polls: number;
}

export const IDLE: RunView = { state: "idle", polls: 0 };

/** The next view after an answer (or an error). Fabric's message is kept once, on failed. */
export function nextView(prev: RunView, a: RunAnswer | { error: string; kind?: string; hint?: string }): RunView {
  if ("error" in a) {
    const refused = a.kind === "needs_permission";
    return { state: refused ? "refused" : "failed", polls: prev.polls, runId: prev.runId,
      message: [a.error, a.hint].filter(Boolean).join(" ") };
  }
  return { state: a.state, runId: a.run_id ?? prev.runId, line: a.words, polls: prev.polls + 1,
    message: a.state === "failed" ? a.message : undefined, preview: a.state === "succeeded" ? a.preview : undefined };
}

/** Whether to read the run again, and after how long: every 5 s for the first minute, then every 15 s, at most 30 min. */
export function pollDelay(v: RunView): number | undefined {
  if (!(v.state === "queued" || v.state === "running" || v.state === "unknown") || !v.runId) return undefined;
  if (v.polls > 130) return undefined;
  return v.polls < 12 ? 5000 : 15000;
}

const WORD: Record<RunState, string> = {
  idle: "", starting: "Starting the run…", queued: "Queued in Fabric", running: "Running in Fabric", succeeded: "Succeeded",
  failed: "Failed", unknown: "No answer from Fabric yet", refused: "Not started",
};

/** The status word (the badge) and the one line under it. Fabric's message appears once, in the line, never twice. */
export function runStatus(v: RunView): { word: string; line?: string } {
  if (v.state === "idle") return { word: "" };
  if (v.state === "failed" || v.state === "refused") return { word: WORD[v.state], line: v.message };
  return { word: WORD[v.state], line: v.state === "succeeded" ? v.preview?.words : undefined };
}

/** The table the run writes, for the preview: a feature starter's saveAsTable or an analysis' output. */
export function outputTable(code: string | undefined): string | undefined {
  const m = /saveAsTable\(\s*["'`]([A-Za-z_][A-Za-z0-9_]*)["'`]\s*\)/.exec(code ?? "");
  return m?.[1];
}

/** The preview's rows as text cells, in the columns' order (values shortened as the engine shortened them). */
export function previewCells(p: RunPreview): { columns: string[]; rows: string[][] } {
  const columns = p.columns ?? Object.keys(p.rows?.[0] ?? {});
  const rows = (p.rows ?? []).slice(0, 10).map((r) => columns.map((c) => (r[c] === null || r[c] === undefined ? "" : String(r[c]))));
  return { columns, rows };
}
