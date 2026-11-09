/**
 * n174: what the Krusgraph Model builds, in words and as data the views read. Pure functions, no React, no Fabric client,
 * so they run in unit tests (buildWords.test.ts).
 *
 * Every output the MCP tools build: the silver notebook, the gold views and the pipeline (the data flow), the semantic
 * model and its report, the API for GraphQL, the ontology and the data agent. Their order, labels and delegated
 * permissions mirror fabric_backend/workload_api.KINDS (tests/test_workload_build.py checks the copy). Nothing here runs
 * or schedules a notebook or a pipeline, so no Execute permission is ever listed.
 */
import { CreatedItem, OutputChoice, OutputsDefinition, ProductDefinition } from "./ModelItemDefinition";
import { BuildCard, CreatedRef, DataProduct, ManyAnswer, OutputKind, OutputRequest } from "./engineClient";

export interface KindInfo {
  kind: OutputKind;
  label: string;
  /** the Fabric item type, for Open in Fabric */
  type: string;
  suffix: string;
  /** the tool updates an item of that name in place (a report never is) */
  updates: boolean;
  /** the delegated permissions, each "A or B" (Item.ReadWrite.All covers every item type) */
  needs: string[];
  what: string;
}

const NOTEBOOK = "Notebook.ReadWrite.All or Item.ReadWrite.All";

export const KINDS: KindInfo[] = [
  { kind: "silver_notebook", label: "Silver notebook", type: "Notebook", suffix: "silver", updates: true, needs: [NOTEBOOK],
    what: "A notebook that writes a clean copy of each table: one row per key, every link checked, broken rows set aside." },
  { kind: "gold_views", label: "Gold views", type: "Notebook", suffix: "gold", updates: true, needs: [NOTEBOOK],
    what: "A notebook that creates one wide view per fact table over the silver tables, with the keys and links as rules." },
  { kind: "pipeline", label: "Pipeline", type: "DataPipeline", suffix: "pipeline", updates: true,
    needs: [NOTEBOOK, "DataPipeline.ReadWrite.All or Item.ReadWrite.All"],
    what: "A pipeline that runs the silver notebook, then the gold views, then a check. It is not run or scheduled." },
  { kind: "semantic_model", label: "Semantic model", type: "SemanticModel", suffix: "model", updates: true,
    needs: ["SemanticModel.ReadWrite.All or Item.ReadWrite.All"],
    what: "A Power BI semantic model (Direct Lake) with the keys, links and suggested measures." },
  { kind: "report", label: "Report", type: "Report", suffix: "report", updates: false,
    needs: ["Report.ReadWrite.All or Item.ReadWrite.All", "SemanticModel.ReadWrite.All or Item.ReadWrite.All"],
    what: "A one-page report drawn from the semantic model's own measures and columns." },
  { kind: "graphql", label: "API for GraphQL", type: "GraphQLApi", suffix: "api", updates: true,
    needs: ["GraphQLApi.ReadWrite.All or Item.ReadWrite.All"], what: "An API for GraphQL over the tables, with the links as relationships." },
  { kind: "ontology", label: "Ontology", type: "Ontology", suffix: "ontology", updates: true, needs: ["Item.ReadWrite.All"],
    what: "A Fabric IQ ontology (preview): entity types with their keys and the links between them." },
  { kind: "data_agent", label: "Data agent", type: "DataAgent", suffix: "agent", updates: true,
    needs: ["DataAgent.ReadWrite.All or Item.ReadWrite.All"],
    what: "A data agent with the plan as its instructions and example questions, left unpublished as a draft." },
];

export const ORDER: OutputKind[] = KINDS.map((k) => k.kind);
export const FLOW_KINDS: OutputKind[] = ["silver_notebook", "gold_views", "pipeline"];

export function kindInfo(kind: string): KindInfo | undefined {
  return KINDS.find((k) => k.kind === kind);
}

const NAME = /^[A-Za-z0-9_]{1,123}$/;

export function validName(name: string): boolean {
  return NAME.test(name);
}

/** The default item name for an output: the lakehouse's name plus the kind's suffix, in characters Fabric allows. */
export function defaultName(kind: OutputKind, displayName: string): string {
  const base = (displayName || "model").replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "model";
  return `${base}_${kindInfo(kind)?.suffix ?? kind}`.slice(0, 123);
}

/** The outputs as the engine takes them: the enabled ones, in the build's order (the model before its report). */
export function toRequests(choices: OutputChoice[]): OutputRequest[] {
  return choices
    .filter((c) => c.enabled && kindInfo(c.type))
    .sort((a, b) => ORDER.indexOf(a.type as OutputKind) - ORDER.indexOf(b.type as OutputKind))
    .map((c) => ({ kind: c.type as OutputKind, name: c.name, ...(c.type === "report" && c.model ? { model: c.model } : {}) }));
}

/** What a chosen output's problems are before any call: a bad name, two notebooks of one name, a report with no model. */
export function choiceProblems(choices: OutputChoice[]): string[] {
  const on = choices.filter((c) => c.enabled);
  const out: string[] = [];
  if (!on.length) out.push("Choose at least one thing to build.");
  for (const c of on) {
    if (!validName(c.name)) out.push(`${kindInfo(c.type)?.label ?? c.type}: letters, digits and underscores only.`);
  }
  const report = on.find((c) => c.type === "report");
  if (report && !report.model && !on.some((c) => c.type === "semantic_model")) {
    out.push("A report needs a semantic model: choose Semantic model too, or name an existing model.");
  }
  const s = on.find((c) => c.type === "silver_notebook");
  const g = on.find((c) => c.type === "gold_views");
  if (s && g && s.name.toLowerCase() === g.name.toLowerCase()) out.push("The silver and the gold notebook need two different names.");
  return out;
}

/** The output an item in outputs.json came from; phase 1 saved an API for GraphQL without `output`. */
export function outputOf(c: CreatedItem): string | undefined {
  return c.output ?? (c.type === "GraphQLApi" ? "graphql" : undefined);
}

export function nextFreeName(name: string, taken: string[]): string {
  const lower = new Set(taken.map((t) => t.toLowerCase()));
  for (let i = 2; i < 1000; i++) {
    const n = `${name.slice(0, 118)}_${i}`;
    if (!lower.has(n.toLowerCase())) return n;
  }
  return `${name.slice(0, 110)}_${Date.now() % 100000}`;
}

export interface NameAction {
  action: "create" | "update" | "new_name";
  button: string;
  suggestion?: string;
  reason?: string;
}

/** Re-opening the item: an output this Model already built is offered as Update where its tool updates in place, else
 * with a new name (a report is never updated in place). */
export function nameAction(kind: OutputKind, name: string, created: CreatedItem[]): NameAction {
  const built = created.find((c) => outputOf(c) === kind && c.name.toLowerCase() === name.toLowerCase());
  if (!built) return { action: "create", button: "Create" };
  const info = kindInfo(kind);
  if (info?.updates) return { action: "update", button: "Update", reason: `${name} was built by this item; Create updates it in place.` };
  return {
    action: "new_name",
    button: "Create with a new name",
    suggestion: nextFreeName(name, created.map((c) => c.name)),
    reason: `A ${info?.label.toLowerCase() ?? kind} is never updated in place; ${name} stays as it is.`,
  };
}

/** outputs.json's created list with what a build created: an item of the same id is replaced, a new one added. */
export function mergeCreated(prev: CreatedItem[], add: CreatedRef[]): CreatedItem[] {
  const out = [...prev];
  for (const a of add) {
    const item: CreatedItem = { type: a.type, id: a.id, name: a.name, workspace: a.workspace, ...(a.output ? { output: a.output } : {}) };
    const i = out.findIndex((c) => c.id === a.id);
    if (i >= 0) out[i] = item;
    else out.push(item);
  }
  return out;
}

/** The data product as outputs.json keeps it: the engine's product of a Create, with the created items' ids only. A
 * product of a dry run has no ids and is not stored. */
export function productToStore(p: DataProduct | undefined, builtAt: string): ProductDefinition | undefined {
  if (!p) return undefined;
  const items = p.items.filter((x) => typeof x.id === "string" && x.id).map((x) => ({
    type: x.type,
    id: x.id,
    name: x.name,
    workspace: x.workspace,
    ...(x.output ? { output: x.output } : {}),
  }));
  if (!items.length) return undefined;
  return {
    name: p.name,
    owner: p.owner,
    owner_note: p.owner_note,
    plan: p.plan,
    items,
    domains: p.domains.map((d) => ({ name: d.name, tables: d.tables, why: d.why })),
    built_at: builtAt,
  };
}

/** A later build of the same product adds its items to the stored ones (same id replaced). */
export function mergeProduct(prev: ProductDefinition | undefined, next: ProductDefinition | undefined): ProductDefinition | undefined {
  if (!next) return prev;
  if (!prev || prev.name !== next.name) return next;
  return { ...next, items: mergeCreated(prev.items, next.items) };
}

/** outputs.json after a Create: the choices, every created item, the product. */
export function afterCreate(outputs: OutputsDefinition, choices: OutputChoice[], a: ManyAnswer, builtAt: string): OutputsDefinition {
  return {
    ...outputs,
    outputs: choices,
    created: mergeCreated(outputs.created, a.created ?? []),
    product: mergeProduct(outputs.product, productToStore(a.product, builtAt)),
  };
}

export interface OpenLink {
  label: string;
  item: { id: string; workspaceId: string; type: string; displayName: string };
}

/** One Open in Fabric per created item, with the item's type label. */
export function openLinks(items: CreatedItem[]): OpenLink[] {
  return items
    .filter((c) => c.id)
    .map((c) => {
      const out = outputOf(c);
      const info = out ? kindInfo(out) : undefined;
      const what = c.type === "Notebook" && out === "pipeline" ? "Notebook" : info?.label ?? c.type;
      return { label: `${what} ${c.name}`, item: { id: c.id, workspaceId: c.workspace, type: c.type, displayName: c.name } };
    });
}

/** The card's title: what Create would do, or why it will not. */
export function cardTitle(c: BuildCard): string {
  if (c.refusal) return `${c.label} ${c.name}: not built`;
  if (c.answer?.error) return `${c.label} ${c.name}: ${c.dry_run ? "the dry run stopped" : "not built"}`;
  if (!c.dry_run) return `${c.label} ${c.name}: ${c.would === "update" ? "updated" : "created"}`;
  return `${c.would === "update" ? "Update" : "Create"} ${c.label.toLowerCase()} ${c.name}`;
}

/** The problem of a card in one line: the refusal, the tool's error, or the consent the dry run sees. */
export function cardProblem(c: BuildCard): { error: string; kind: string; hint?: string; steps?: string[] } | undefined {
  const r = c.refusal ?? (c.answer?.error ? (c.answer as BuildCard["refusal"]) : undefined) ?? c.consent;
  if (!r) return undefined;
  return { error: r.error, kind: r.kind, hint: r.hint, steps: r.entra_steps };
}

/** A few facts from the tool's own dry run, per kind, in plain words (counts only; nothing invented). */
export function cardFacts(c: BuildCard): string[] {
  const a = c.answer;
  if (!a || a.error) return [];
  const n = (x: unknown) => (Array.isArray(x) ? x.length : 0);
  switch (c.output) {
    case "silver_notebook":
      return [`${n(a.steps)} silver table(s)`, ...(n(a.not_checked) ? [`${n(a.not_checked)} column(s) not checked: ambiguous`] : [])];
    case "gold_views":
      return [`${n(a.views)} gold view(s)`];
    case "pipeline":
      return (a.steps as string[]) ?? [];
    case "semantic_model":
      return a.summary ? [String(a.summary).split("\n")[0]] : [];
    case "report": {
      const r = a.report ?? {};
      const on = r.bound_to?.semantic_model ? ` on ${r.bound_to.semantic_model}` : "";
      return [`One page with ${n(r.visuals)} visual(s)${on}`];
    }
    case "graphql":
      return a.summary ? [String(a.summary).split("\n")[0]] : [];
    case "ontology":
      return typeof a.summary === "object" && a.summary
        ? [`${a.summary.entity_types} entity type(s), ${a.summary.relationship_types} relationship type(s)`]
        : [];
    case "data_agent":
      return [`${n(a.agent?.tables_to_select)} table(s) selected, ${n(a.agent?.fewshots)} example question(s)`, "Left unpublished: a draft only you see"];
    default:
      return [];
  }
}

/** Builder's line under the preview: how many outputs, how many would be refused. */
export function previewLine(a: ManyAnswer): string {
  const ok = a.outputs.length - a.refused;
  const total = a.outputs.length;
  const verbs = a.outputs.filter((c) => !c.refusal && !c.answer?.error);
  const upd = verbs.filter((c) => c.would === "update").length;
  if (!ok) return "Nothing can be built as it stands: each card below says why.";
  return (
    `This is the dry run: nothing exists yet. Create makes ${ok} of ${total}` +
    (upd ? ` (${upd} updated in place)` : "") +
    ". Nothing is run or scheduled."
  );
}

export function resultLine(a: ManyAnswer): string {
  const made = (a.created ?? []).length;
  return made
    ? `${made} item(s) are in Fabric now. Open each one there; what is still to do is listed under it.`
    : "Nothing was created: each card below says why.";
}

/** The choices the outputs view starts from: what outputs.json saved (phase 1 saved the API for GraphQL), the rest off
 * with a default name. A new item starts with the API for GraphQL on, as before. */
export function choicesFor(saved: OutputChoice[], displayName: string): OutputChoice[] {
  return KINDS.map(
    (k) =>
      saved.find((c) => c.type === k.kind) ?? {
        type: k.kind,
        name: defaultName(k.kind, displayName),
        enabled: k.kind === "graphql" && saved.length === 0,
      }
  );
}

/** The Create button's words: Create, or Create and update when an output is updated in place. */
export function createLabel(a: ManyAnswer | undefined): string {
  const upd = (a?.outputs ?? []).some((c) => !c.refusal && !c.answer?.error && c.would === "update");
  return upd ? "Create and update" : "Create";
}
