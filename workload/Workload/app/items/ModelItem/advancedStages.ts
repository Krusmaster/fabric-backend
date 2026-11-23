/**
 * AA1: Advanced analytics in three stages, from the feature table to a model and to predictions in gold.
 *
 * Gustav ran the Data Science starter (WB10) in Fabric on 21 November 2026: the feature table and an ML experiment with one
 * run. This file takes it one step further for each analysis the rules recommend on the proven grain:
 *   1. Feature table        the starter notebook of the card (featureCells, unchanged)
 *   2. Model                a notebook that trains one simple baseline, logs it to the ML experiment and registers it
 *   3. Predictions in gold  a notebook that scores with the registered model (Fabric's PREDICT) into a gold table
 *
 * The notebooks are fabric_backend/advanced_stages.py's templates (advancedStages.generated.ts), filled here the way the
 * Python fills them; advancedStages.fixture.json holds the Python's answer for the shop sample and the SAP full demo, and
 * advancedStages.test.ts checks that this file gives the same cells. Pure functions, no AI. Krusgraph never runs them.
 */
import type { ReviewFile } from "./ModelItemDefinition";
import type { Grain } from "./nextSteps";
import { ADVANCED } from "./advancedStages.generated";

/** W1 (Gustav, 23 November 2026: "One row per orders"): a table's name as one of its rows, for a sentence. The same
 * rule as advanced_stages.one_row_of; the fixture holds both to the same words. */
const ONE_IRREGULAR: Record<string, string> = { people: "person", children: "child", men: "man", women: "woman", indices: "index", data: "data", staff: "staff" };

export function oneRowOf(table: string): string {
  const name = String(table ?? "");
  const m = /^(.*?)([a-z]+)$/.exec(name);
  if (!m || name !== name.toLowerCase()) return name;
  let w = m[2];
  if (w in ONE_IRREGULAR) w = ONE_IRREGULAR[w];
  else if (w.endsWith("ies") && w.length > 4) w = w.slice(0, -3) + "y";
  else if (/(sses|xes|ches|shes)$/.test(w)) w = w.slice(0, -2);
  else if (w.endsWith("s") && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);
  return w === m[2] ? name : (m[1] + w).replace(/_/g, " ");
}

export type Analysis = "forecast" | "segments" | "drivers";
export type Stage = "features" | "model" | "predictions";

export interface Link { source: string; columns: string[]; target: string; target_columns?: string[] }
export interface CustomerLink { table: string; column: string; key: string; parts: string[] }

export interface StageNotebook { stage: Stage; name: string; output: string; cells?: string[] }
export interface AnalysisPlan {
  analysis: Analysis;
  title: string;
  why: string;
  /** true when there are rows enough for a model (drivers has no model: false) */
  model: boolean;
  /** the one sentence said when there are too few rows (empty otherwise) */
  too_few: string;
  gold_table: string;
  model_name: string | null;
  stages: StageNotebook[];
}
export interface AdvancedPlan { values: Record<string, unknown>; analyses: AnalysisPlan[]; experiment: string }

const CUSTOMER_WORDS = /(cust|kunde|kna1|client|buyer|account|partner)/i;
const CLIENT = new Set(["MANDT", "RCLNT", "CLIENT"]);

export const ident = (s: string) => s.replace(/[^A-Za-z0-9_]+/g, "_").replace(/^(\d)/, "_$1").toLowerCase();

/** The proven links of the review (passed, not rejected), as advanced_stages.customer_link reads them. */
export function provenLinks(review: ReviewFile | undefined): Link[] {
  return (review?.items ?? [])
    .filter((it) => it.type === "relationship" && it.review !== "rejected" && it.check?.status === "passed")
    .map((it) => ({ source: it.source ?? "", columns: it.columns ?? [], target: it.target ?? "", target_columns: it.target_columns }));
}

/** advanced_stages.customer_link: the first proven link from the order table to a table whose name reads as a customer. */
export function customerLink(g: Pick<Grain, "parent">, links: Link[]): CustomerLink | null {
  const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
  const hits = links
    .filter((l) => l.source === g.parent && l.columns.length >= 1 && CUSTOMER_WORDS.test(l.target ?? ""))
    .sort((a, b) => cmp(a.target.toLowerCase(), b.target.toLowerCase()) || cmp(a.columns.map((c) => c.toLowerCase()).join("\u0000"), b.columns.map((c) => c.toLowerCase()).join("\u0000")));
  if (!hits.length) return null;
  const l = hits[0];
  const cols = l.columns.filter((c) => !CLIENT.has(c.toUpperCase()));
  const useCols = cols.length ? cols : l.columns;
  const tAll = l.target_columns?.length ? l.target_columns : l.columns;
  // several columns (SAP's client + customer): gold's combined key column (combined_keys.py: joined by _, plus _key)
  const key = tAll.length === 1 ? tAll[0] : `${tAll.join("_")}_key`;
  return { table: l.target, column: useCols[useCols.length - 1], key, parts: [...l.columns] };
}

type GrainIn = Pick<Grain, "parent" | "child" | "childColumns" | "parentColumns" | "parentRows"> & { childIds?: string[] };

/** advanced_stages.values */
export function advValues(g: GrainIn, source: { name?: string; schema?: string }, customer: CustomerLink | null): Record<string, unknown> {
  const ids = [...new Set([...g.parentColumns, ...(g.childIds ?? []), ...g.childColumns, ...(customer ? [customer.column] : [])])]
    .sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const stem = ident(g.parent);
  return {
    source: `${source.name || "the lakehouse"}${source.schema ? ` / ${source.schema}` : ""}`,
    parent: g.parent, parent_one: oneRowOf(g.parent), child: g.child,
    feature_table: ident(`${g.parent}_features`),
    order_key: [...g.parentColumns],
    ids,
    child_prefix: ident(g.child),
    customer: customer?.column ?? null, customer_table: customer?.table ?? null, customer_key: customer?.key ?? null,
    customer_parts: customer?.parts ?? [],
    experiment: ident(`${g.parent}_experiment`),
    schemas_enabled: !!source.schema,
    gold_schema: "gold",
    orders: Math.trunc(g.parentRows || 0),
    forecast_model: `${stem}_weekly_forecast`, forecast_table: `${stem}_forecast`,
    segments_model: `${stem}_customer_segments`, segments_table: "customer_segment",
    drivers_table: `${stem}_top10`,
  };
}

/** Python's literal of a value (json.dumps; None, True, False). */
export function literal(x: unknown): string {
  if (x === null || x === undefined) return "None";
  if (typeof x === "boolean") return x ? "True" : "False";
  if (Array.isArray(x)) return `[${x.map(literal).join(", ")}]`;
  return JSON.stringify(x);
}

/** advanced_stages.fill: {{name}} as a Python literal (code), [[name]] as plain text (comments and prose). */
export function fill(template: string, vals: Record<string, unknown>): string {
  return template
    .replace(/\{\{(\w+)\}\}/g, (_, k: string) => literal(vals[k]))
    .replace(/\[\[(\w+)\]\]/g, (_, k: string) => (vals[k] === null || vals[k] === undefined ? "None" : String(vals[k])));
}

const T = ADVANCED.thresholds;

function fillValues(v: Record<string, unknown>, a: Analysis, stage: Stage): Record<string, unknown> {
  const table = { forecast: v.forecast_table, segments: v.segments_table, drivers: v.drivers_table }[a];
  const model = { forecast: v.forecast_model, segments: v.segments_model, drivers: null }[a];
  const stageTitle = stage === "model" && a !== "drivers" ? "stage 2, the model" : stage === "model" ? "stage 2, descriptive (no model)" : "stage 3, predictions in gold";
  return {
    ...v, title: ADVANCED.titles[a], stage_title: stageTitle, gold_table: table, model_name: model,
    min_orders: T.min_orders, min_weeks: T.min_weeks, min_customers: T.min_customers, horizon: T.horizon,
    k_range: [...T.k_range], k_tie: T.k_tie, mark: ADVANCED.mark, learn_autolog: ADVANCED.learn.autolog, learn_predict: ADVANCED.learn.predict,
  };
}

export function cells(v: Record<string, unknown>, a: Analysis, stage: Exclude<Stage, "features">): string[] {
  const key = `${stage}:${a}` as keyof typeof ADVANCED.templates;
  const vals = fillValues(v, a, stage);
  return (ADVANCED.templates[key] as readonly string[]).map((t) => fill(t, vals));
}

function notebookName(v: Record<string, unknown>, sourceName: string, a: Analysis, stage: "model" | "predictions"): string {
  const word = stage === "model" ? (a !== "drivers" ? "model" : "top10") : "predictions";
  return ident(`${sourceName}_${v.parent}_${a}_${word}`).slice(0, 123);
}

/** advanced_stages.recommend + stages: the analyses for this grain, each with its three stages (drivers: two). */
export function advancedStages(g: GrainIn, source: { name?: string; schema?: string }, links: Link[]): AdvancedPlan {
  const cust = customerLink(g, links);
  const v = advValues(g, source, cust);
  const orders = v.orders as number;
  const few = orders < T.min_orders;
  const tooFew = few ? ADVANCED.too_few.replace("{n}", String(orders)).replace("{min}", String(T.min_orders)) : "";
  const gold = (t: unknown) => `${v.gold_schema}.${t}`;
  const recs: Omit<AnalysisPlan, "stages">[] = [{
    analysis: "forecast", title: ADVANCED.titles.forecast,
    why: `One row per ${oneRowOf(g.parent)} with its date: the number of ${g.parent} per week is a series to forecast.`,
    model: !few, too_few: tooFew, gold_table: gold(v.forecast_table), model_name: v.forecast_model as string,
  }];
  if (cust) {
    recs.push({
      analysis: "segments", title: ADVANCED.titles.segments,
      why: `${g.parent}.${cust.column} -> ${cust.table} is proven: recency, frequency and value per customer come from the proven key, one row per order.`,
      model: !few, too_few: tooFew, gold_table: gold(v.segments_table), model_name: v.segments_model as string,
    });
  }
  recs.push({
    analysis: "drivers", title: ADVANCED.titles.drivers,
    why: `Which customers and which values of the text columns of ${g.parent} carry most orders and most value: descriptive, no model.`,
    model: false, too_few: "", gold_table: gold(v.drivers_table), model_name: null,
  });
  const name = source.name || "lakehouse";
  const analyses = recs.map((r) => {
    const st: StageNotebook[] = [{ stage: "features", name: ident(`${name}_${g.parent}_features`).slice(0, 123), output: v.feature_table as string }];
    st.push({ stage: "model", name: notebookName(v, name, r.analysis, "model"), cells: cells(v, r.analysis, "model"), output: r.model_name ?? r.gold_table });
    if (r.analysis !== "drivers") {
      st.push({ stage: "predictions", name: notebookName(v, name, r.analysis, "predictions"), cells: cells(v, r.analysis, "predictions"), output: r.gold_table });
    }
    return { ...r, stages: st };
  });
  return { values: v, analyses, experiment: v.experiment as string };
}

export const STAGE_WORD: Record<Stage, string> = { features: "Feature table", model: "Model", predictions: "Predictions in gold" };
