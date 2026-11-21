/**
 * ED1 (Gustav's editor test, 21 November 2026): fewer decisions on the Choose step. Every output that depends on another
 * says what it is built on, as a visible default: the report on the semantic model above (or the one this item built
 * before), the data agent on its layer, the ontology on the silver tables. Pure functions, no React (ed1Words.test.ts).
 */
import type { CreatedItem, OutputChoice } from "./ModelItemDefinition";
import { agentOf } from "./jobsWords";

const on = (choices: OutputChoice[], kind: string) => choices.find((c) => c.type === kind && c.enabled);

/** The semantic model this item built last, if any (outputs.json). */
export function builtModel(created: CreatedItem[]): string | undefined {
  return [...created].reverse().find((c) => c.output === "semantic_model" || c.type === "SemanticModel")?.name;
}

export interface BuiltOn {
  /** "Built on: shop_lh_model (the semantic model above)" */
  text: string;
  /** the report has nothing to be built on */
  missing?: boolean;
}

/** What an output is built on, or undefined for one that is not built on another output. */
export function builtOn(kind: string, choices: OutputChoice[], created: CreatedItem[], sourceName = "the source"): BuiltOn | undefined {
  const silver = !!on(choices, "silver_notebook") || !!on(choices, "pipeline");
  if (kind === "report") {
    const report = choices.find((c) => c.type === "report");
    if (report?.model) return { text: `Built on: ${report.model} (a semantic model in this workspace)` };
    const model = on(choices, "semantic_model");
    if (model) return { text: `Built on: ${model.name} (the semantic model above)` };
    const before = builtModel(created);
    if (before) return { text: `Built on: ${before} (the semantic model this item built before)` };
    return { text: "A report needs a semantic model: tick Semantic model, or choose one under Change.", missing: true };
  }
  if (kind === "data_agent") {
    const layer = agentOf(choices.find((c) => c.type === "data_agent")).layer;
    const gold = choices.find((c) => c.type === "gold_views")?.name;
    if (layer === "gold") return { text: `Built on: the gold views${gold ? ` (${gold})` : ""}` };
    if (layer === "source") return { text: `Built on: the source tables of ${sourceName}` };
    return { text: silver ? "Built on: the silver tables this build writes" : `Built on: the silver tables of ${sourceName}` };
  }
  if (kind === "ontology" || kind === "semantic_model")
    return { text: silver ? "Built on: the silver tables this build writes" : `Built on: the tables of ${sourceName}` };
  if (kind === "graphql") return { text: `Built on: the tables of ${sourceName}` };
  return undefined;
}

/** The pipeline's and the agent's own defaults, said in one line each (changed under Change). */
export function defaultsLine(kind: string, c: OutputChoice): string | undefined {
  if (kind === "pipeline") {
    const j = c.jobs;
    if (!j?.run_once && !j?.schedule) return undefined;        // the card's own words already say "It is not run or scheduled."
    const run = j?.run_once ? "runs once after Create" : "is not run";
    const sched = j?.schedule ? `, scheduled ${j.schedule.every === "hours" ? `every ${j.schedule.hours ?? 4} hours` : `daily at ${j.schedule.at}`}` : " or scheduled";
    return `It ${run}${sched}.`;
  }
  if (kind === "data_agent") {
    const a = agentOf(c);
    return a.publish ? `It is published in Fabric${a.copilot ? " and in Microsoft 365 Copilot" : ""}.` : "It is left as an unpublished draft.";
  }
  return undefined;
}

/** ED1: a sentence run into the next one without a space ("workspace.Silver"): what rendered help text must never have. */
export const JOINED = /(?:^|[\s(])[a-z]+[a-z)]\.[A-Z][a-z]+[\s,:;]/;

/** ED1: the data product card's owner line. Never a "?" placeholder: the plan is named once it is known, otherwise the
 * clause is left out ("Owner: <name>. Plan ?." before). */
export function productOwnerLine(p: { owner?: string | null; plan?: { plan_id?: string | null; schema_fingerprint?: string | null } | null }): string {
  const owner = `Owner: ${p.owner || "nobody has chosen one yet"}.`;
  const plan = p.plan?.plan_id;
  if (!plan) return owner;
  return `${owner} Plan ${plan}${p.plan?.schema_fingerprint ? `, schema ${p.plan.schema_fingerprint}` : ""}.`;
}

type CheckedItem = {
  id: string; type: string; table?: string; source?: string; target?: string; columns: string[];
  check?: { status?: string; result?: { rows?: number; rows_with_value?: number }; not_counted?: string; stale_because?: string } | null;
};

function itemName(it: CheckedItem): string {
  return it.type === "key" ? `the key of ${it.table}` : `${it.source}.${it.columns.join("+")} → ${it.target}`;
}

function why(it: CheckedItem): { text: string; again: boolean } {
  const c = it.check ?? {};
  if (c.status === "stale") return { text: c.stale_because || "it changed since the check", again: true };
  if (c.result && it.type === "key" && c.result.rows === 0) return { text: `${it.table} has no rows`, again: false };
  if (c.result && it.type !== "key" && c.result.rows_with_value === 0) return { text: "no row has a value in the column", again: false };
  if (c.not_counted) return { text: c.not_counted.replace(/^not counted: /, "").replace(/\.$/, ""), again: false };
  return { text: "the last check did not count it", again: false };
}

/** ED1: the one plain line behind "3 not checked": which ones and why ("not checked: the key of audit_log (audit_log has
 * no rows), ..."), and whether a check again would count them. Empty when every item was checked or nothing was. */
export function notCheckedLine(items: CheckedItem[] | undefined, checked: number): { text: string; again: boolean } | undefined {
  if (!checked) return undefined;
  const left = (items ?? []).filter((it) => it.check?.status !== "passed" && it.check?.status !== "failed");
  if (!left.length) return undefined;
  const parts = left.map((it) => ({ it, w: why(it) }));
  const shown = parts.slice(0, 3).map(({ it, w }) => `${itemName(it)} (${w.text})`).join("; ");
  const more = parts.length > 3 ? `; and ${parts.length - 3} more` : "";
  return { text: `Not checked: ${shown}${more}.`, again: parts.some((p) => p.w.again) };
}

