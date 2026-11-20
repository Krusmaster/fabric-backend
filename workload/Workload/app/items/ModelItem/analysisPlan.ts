/**
 * WB4: "Recommended analyses" in Next, with other Fabric workloads (and so on the Data product page too).
 *
 * The engine's POST /workload/v1/analysis runs analysis_plan (round AP2, docs/ANALYSIS-PLAN.md) on this item's reviewed
 * plan: ten SAP order-to-cash analyses ranked by fixed rules over the plan and row counts, no AI. This file turns that
 * answer into cards. Pure functions, no React:
 *
 *   one word for the readiness (never colour alone): Ready, Partly ready, Not ready yet, Not applicable
 *   one line "Recommended because …" (or "Not ready yet because …")
 *   what is missing, or for a not-ready analysis what data would make it ready
 *   one action: for a ready A7, A8 or A3 the notebook starter (Download .ipynb, Copy the code), as the Data Science
 *   starter does; otherwise the request to ask Krusgraph in Claude, where the tools analysis_plan and
 *   analysis_notebook_draft exist. Krusgraph runs no analysis and creates nothing here.
 */

export type Readiness = "ready" | "partial" | "missing";

export interface AnalysisNotebook {
  filename: string;
  name: string;
  /** the notebook as .ipynb (nbformat 4), text */
  ipynb: string;
  /** the cells as Python, for Copy */
  code: string;
  cells: number;
  output: string;
  experiment: string;
}

export interface AnalysisRec {
  analysis: string;
  name: string;
  readiness: Readiness;
  score: number;
  value?: number;
  because: string;
  reasons: string[];
  missing: string[];
  caveats: string[];
  next_step: string;
  not_applicable?: boolean;
  notebook?: AnalysisNotebook;
}

export interface AnalysisAnswer {
  /** false: the schema has no SAP order-to-cash tables (`words` says so) */
  applies?: boolean;
  /** the check has not passed yet: nothing was ranked */
  waiting?: string;
  words?: string;
  summary?: string;
  rule_version?: string;
  recommendations: AnalysisRec[];
  land_next?: { land: string; unlocks: string[]; value: number }[];
  not_counted?: string[];
  note?: string;
}

export type AnalysisAction =
  | { kind: "notebook"; label: string; filename: string; mime: string; content: string; code: string; output: string }
  | { kind: "ask"; label: string; text: string };

export interface AnalysisCard {
  id: string;
  rank: number;
  title: string;
  readiness: Readiness;
  /** the readiness in words, shown beside its colour */
  word: string;
  /** one line: why it is recommended, or why not yet */
  line: string;
  /** what is missing (for a not-ready analysis: what data would make it ready) */
  missing: string;
  action: AnalysisAction;
}

export const READINESS_WORD: Record<Readiness | "not_applicable", string> = {
  ready: "Ready", partial: "Partly ready", missing: "Not ready yet", not_applicable: "Not applicable",
};

/** The notebooks phase 1 of the analysis pack writes (analysis_notebook.ANALYSES). */
export const NOTEBOOK_ANALYSES = ["A7", "A8", "A3"];

const first = (s: string) => s.split("; ")[0].trim();

/** The rule's own lead without its prefix: "Recommended because: a; b" -> "a". */
function lead(e: AnalysisRec): string {
  if (e.readiness !== "missing" && e.reasons.length) return e.reasons[0];
  const text = e.because.replace(/^(Recommended|Not recommended yet) because:\s*/, "");
  return first(text);
}

/** "Recommended because …" for a ready or partly ready analysis; "Not ready yet because …" otherwise. One line. */
export function becauseLine(e: AnalysisRec): string {
  if (e.not_applicable) return `Not applicable to this data because ${lead(e)}.`.replace(/\.\.$/, ".");
  return `${e.readiness === "missing" ? "Not ready yet because" : "Recommended because"} ${lead(e)}`;
}

/** What is missing. Ready: the rule's caveat that something in it is not ready (XYZ), else nothing. Partly ready: what
 * holds it back. Not ready: what data would make it ready (the rule's missing inputs). */
export function missingLine(e: AnalysisRec): string {
  if (e.readiness === "missing") {
    const what = e.missing.length ? e.missing.join("; ") : e.next_step.replace(/^land:\s*/, "");
    return e.not_applicable ? `To apply: ${what}` : `What would make it ready: ${what}`;
  }
  const weak = e.caveats.filter((c) => /not ready|capped at partial|below|only \d|not counted/i.test(c));
  if (e.missing.length) return `Missing: ${e.missing.join("; ")}`;
  if (weak.length) return `${e.readiness === "ready" ? "Not yet in it" : "Holding it back"}: ${weak.join("; ")}`;
  return "Missing: nothing on this data.";
}

/** The sentence to ask Krusgraph in Claude, for an analysis without a notebook here. */
export function askText(e: AnalysisRec, source: { displayName: string; schema: string }): string {
  const where = `${source.displayName}${source.schema ? ` (schema ${source.schema})` : ""}`;
  if (NOTEBOOK_ANALYSES.includes(e.analysis) && e.readiness === "partial") {
    return `Draft the ${e.analysis} ${e.name} notebook for ${where}: run analysis_notebook_draft with analysis="${e.analysis}". ` +
      "It creates and runs nothing.";
  }
  return `Which SAP analyses does ${where} support, and what would make ${e.analysis} ${e.name} ready? Run analysis_plan.`;
}

/** The cards, in the engine's rank (score, then readiness, then the catalogue's order; analysis_plan.recommend). */
export function analysisCards(answer: AnalysisAnswer | undefined, source: { displayName: string; schema: string }): AnalysisCard[] {
  if (!answer || answer.applies === false || answer.waiting) return [];
  return answer.recommendations.map((e, i) => {
    const nb = e.notebook;
    const action: AnalysisAction = nb && e.readiness === "ready" && NOTEBOOK_ANALYSES.includes(e.analysis)
      ? { kind: "notebook", label: "Download notebook (.ipynb)", filename: nb.filename, mime: "application/x-ipynb+json",
        content: nb.ipynb, code: nb.code, output: nb.output }
      : { kind: "ask", label: "Copy the request for Claude", text: askText(e, source) };
    return {
      id: e.analysis, rank: i + 1, title: `${e.analysis} ${e.name}`, readiness: e.readiness,
      word: e.not_applicable ? READINESS_WORD.not_applicable : READINESS_WORD[e.readiness],
      line: becauseLine(e), missing: missingLine(e), action,
    };
  });
}

/** The answer's headline: how many are ready, partly ready and not ready yet. */
export function analysisSummary(cards: AnalysisCard[]): string {
  const n = (r: Readiness) => cards.filter((c) => c.readiness === r).length;
  if (!cards.length) return "";
  return `${n("ready")} of ${cards.length} analyses ready, ${n("partial")} partly ready, ${n("missing")} not ready yet.`;
}

/** The key the answer is kept under in this browser tab: the source, the schema and what the check proved. */
export function analysisKey(source: { displayName?: string; schema?: string } | undefined, review: { items?: { id: string; review?: string; check?: { status?: string; checked_at?: string } }[] } | undefined): string {
  const items = (review?.items ?? []).map((it) => `${it.id}:${it.review ?? ""}:${it.check?.status ?? ""}:${it.check?.checked_at ?? ""}`);
  return JSON.stringify([source?.displayName ?? "", source?.schema ?? "", items]);
}
