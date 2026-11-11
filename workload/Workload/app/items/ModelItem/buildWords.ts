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
import {
  BuildCard, CreatedRef, DataProduct, EngineCallError, EngineError, ExistingCounts, ManyAnswer, OutputKind, OutputRequest,
} from "./engineClient";
import { appFacts, itemTypeLabel, progressLine, reportFacts, running, visualCount } from "./createWords";

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
  { kind: "rayfin_app", label: "App (Rayfin, preview)", type: "AppBackend", suffix: "app", updates: false,
    needs: ["Item.ReadWrite.All"],
    what: "A Fabric App (preview): key figures, list pages and charts you tick, over a read-only connector with every link. Create makes the App item; its pages are published with the package and three commands." },
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
    .map((c) => ({
      kind: c.type as OutputKind,
      name: c.name,
      ...(c.type === "report" && c.model ? { model: c.model } : {}),
      ...(c.type === "rayfin_app" && c.app ? { app: c.app } : {}),       // n181: the ticked key figures, pages, charts
      ...(c.type === "pipeline" && c.jobs ? { jobs: c.jobs } : {}),        // n185: Run once and Schedule
      ...(c.type === "data_agent" && c.agent ? { agent: c.agent } : {}),   // n185: the layer, Publish and Copilot
    }));
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
    const item: CreatedItem = {
      type: a.type, id: a.id, name: a.name, workspace: a.workspace,
      ...(a.output ? { output: a.output } : {}),
      ...(a.plan ? { plan: a.plan } : {}),                  // n180: the plan it was built from
      ...(a.published !== undefined ? { published: a.published } : {}),   // n185: a data agent published in Fabric
    };
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
      const what = itemTypeLabel(c.type, outputOf(c));          // n184: the item's own type (a pipeline's notebooks too)
      return { label: `${what} ${c.name}`, item: { id: c.id, workspaceId: c.workspace, type: c.type, displayName: c.name } };
    });
}

/** The card's title: what Create would do, or why it will not. */
export function cardTitle(c: BuildCard): string {
  if (c.status === "waiting" && c.after_run === "waiting") return `${c.label} ${c.name}: waits for the pipeline's run`;
  if (c.status === "waiting") return `${c.label} ${c.name}: waiting`;
  if (c.status === "running" && c.progress?.state === "waiting_capacity") return `${c.label} ${c.name}: waiting for capacity`;
  if (c.status === "running" && c.progress?.state === "pending_fabric") return `${c.label} ${c.name}: still running in Fabric`;
  if (c.status === "running") return `${c.label} ${c.name}: creating in Fabric…`;
  if (c.status === "lost") return `${c.label} ${c.name}: no answer yet`;
  if (c.after_run === "stopped") return `${c.label} ${c.name}: not built, the pipeline's run did not succeed`;
  if (c.already_built && c.dry_run) return `${c.label} ${c.name}: already built from this plan, will be skipped`;
  if (c.dry_run && c.built_from && c.choices?.length)                // n209: Create writes nothing for it and asks
    return `${c.label} ${c.name}: ${c.built_from.words}; Create will ask: ${c.choices.includes("update") ? "Update or a new name" : "a new name"}`;
  if (c.already_built) return `${c.label} ${c.name}: already built`;
  if (needsChoice(c)) return `${c.label} ${c.name}: ${c.built_from!.words}`;
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
  if (c.already_built || needsChoice(c)) return existingFacts(c.output, c.existing);   // n180: what the item holds
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
      return modelFacts(a.summary);
    case "report":
      return reportFacts(c);                                   // n184: one count for the dry run and Create
    case "rayfin_app":
      return appFacts(c);                                      // n184: the App item is empty until the package is published
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

/** n180: the semantic model's one refresh in words: what the dry run plans, and how Create's refresh ended. */
export function refreshWords(c: BuildCard): string | undefined {
  const r = c.refresh;
  if (!r) return undefined;
  switch (r.status) {
    case "planned":
      return "Create refreshes the model once; nothing else is run or scheduled." +
        (r.scope ? ` Your sign-in lacks ${r.scope}, so it would be refreshed in the portal instead.` : "");
    case "refreshed":
      return "Refreshed once: the report built on it can read its data.";
    case "refreshing":
      return `Refreshing: ${r.reason ?? "still running"}. Open the report when the refresh has finished.`;
    case "failed":
      return `Refresh failed: ${r.reason ?? "no reason given"}. Refresh the model once in the portal before opening the report.`;
    case "not_run":
      return `Not refreshed: ${r.reason ?? "no permission"}${r.hint ? ` ${r.hint}` : ""}`;
    default:
      return undefined;
  }
}

/** n180: the card of an existing item built from another plan (or plan unknown), waiting for Update or a new name. */
export function needsChoice(c: BuildCard): boolean {
  return !!(c.built_from && c.choices?.length && !c.dry_run);
}

/** n180: what an existing item holds, as its definition says it. Only counts that were read and are above zero: an item
 * whose definition was not read shows no count, never "0 visual(s)" for a report that has visuals. */
export function existingFacts(kind: OutputKind, e: ExistingCounts | undefined): string[] {
  if (!e) return [];
  const has = (n: number | undefined): n is number => typeof n === "number" && n > 0;
  const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  const out: string[] = [];
  if (kind === "gold_views" && has(e.views)) out.push(`Holds ${plural(e.views, "gold view")}`);
  else if (has(e.cells)) out.push(`Holds ${plural(e.cells, "notebook cell")}`);
  if (has(e.pages)) out.push(`Holds ${plural(e.pages, "page")}` + (has(e.visuals) ? ` with ${plural(e.visuals, "visual")}` : ""));
  if (has(e.tables)) out.push(`Holds ${plural(e.tables, "table")}` + (has(e.relationships) ? `, ${plural(e.relationships, "relationship")}` : ""));
  if (has(e.questions)) out.push(`Holds ${plural(e.questions, "example question")}` + (has(e.data_sources) ? ` over ${plural(e.data_sources, "data source")}` : ""));
  return out;
}

/** n180: the Update of a card built from another plan. From the choice card, always the dry run (nothing is written);
 * from that dry run's card, the Create with its confirm_update. Never a write without the dry run before it. */
export async function runUpdate(
  card: BuildCard,
  send: (dryRun: boolean, confirm?: string) => Promise<ManyAnswer>
): Promise<{ card: BuildCard; created: CreatedRef[] }> {
  const confirming = card.dry_run && !!card.confirm_update;
  const a = await send(!confirming, confirming ? card.confirm_update : undefined);
  const next = a.outputs.find((x) => x.output === card.output) ?? a.outputs[0];
  return { card: { ...next, status: "done" }, created: confirming ? a.created ?? next?.created ?? [] : [] };
}

/** n180: Choose a new name for an output whose name is taken by an item built from another plan. */
export function newNameFor(card: BuildCard, taken: string[]): string {
  return nextFreeName(card.name, [...taken, ...(card.existing_items ?? []).map((c) => c.name), card.name]);
}

/** n179: the semantic model's summary in words, as the MCP card says it (the founder saw "[object Object]"): tables,
 * relationships active and inactive, measures, the date table. A text summary keeps its first line. */
export function modelFacts(summary: unknown): string[] {
  if (typeof summary === "string") return summary ? [summary.split("\n")[0]] : [];
  if (!summary || typeof summary !== "object") return [];
  const m = summary as Record<string, any>;
  const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  const out: string[] = [];
  if (typeof m.tables === "number") out.push(plural(m.tables, "table") + (m.storage_mode ? ` in Direct Lake` : ""));
  const act = Number(m.relationships_active ?? 0);
  const inact = Number(m.relationships_inactive ?? 0);
  out.push(`${plural(act, "relationship")} active` + (inact ? `, ${inact} inactive (another path joins the same tables)` : ""));
  if (Number(m.relationships_not_expressible ?? 0)) out.push(`${plural(Number(m.relationships_not_expressible), "link")} over several columns left out (a model relationship has one column)`);
  const measures = Array.isArray(m.measures) ? m.measures.length : 0;
  const orderMeasures = Array.isArray(m.order_amount?.measures) ? m.order_amount.measures.length : 0;
  out.push(measures + orderMeasures ? plural(measures + orderMeasures, "measure") : "No measures");
  if (m.date_table && typeof m.date_table === "object") {
    const rel = Array.isArray(m.date_table.related) ? m.date_table.related.length : 0;
    out.push(`Date table ${m.date_table.name}, marked as the date table` + (rel ? `, related to ${plural(rel, "date column")}` : ""));
  } else {
    out.push("No date table: no date column to relate one to");
  }
  return out;
}

// ------------------------------------------------------------------ n179: the schema, picked from a list ------------

/** The schema to select after the list comes: the saved one as the source spells it (its case corrected), else the
 * engine's preselection (the only schema with tables, or dbo when it is the only one); undefined: the person picks. */
export function schemaToUse(
  list: { schemas: { schema: string; tables: number }[]; preselect: string | null },
  saved?: string
): string | undefined {
  if (saved) {
    const exact = list.schemas.find((x) => x.schema === saved) ?? list.schemas.find((x) => x.schema.toLowerCase() === saved.toLowerCase());
    if (exact && list.schemas.filter((x) => x.schema.toLowerCase() === saved.toLowerCase()).length === 1) return exact.schema;
    if (exact && exact.schema === saved) return saved;
  }
  return list.preselect ?? undefined;
}

// ------------------------------------------------------------------ n179: Create one output per request ------------

/** The outputs of a Create in the engine's order (the model before its report). A report with no model of its own is
 * built on the semantic model this Create makes: its id once created, else its name (the engine then says it is missing). */
export function createOrder(outputs: OutputRequest[]): OutputRequest[] {
  return [...outputs].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
}

export function requestFor(o: OutputRequest, all: OutputRequest[], created: CreatedRef[]): OutputRequest {
  if (o.kind !== "report" || o.model) return o;
  const modelName = all.find((x) => x.kind === "semantic_model")?.name;
  const made = created.find((c) => c.output === "semantic_model" && c.name === modelName && c.id);
  return { ...o, model: made?.id ?? modelName };
}

/** A card before its answer: waiting or running, with the permissions the dry run listed. */
export function pendingCard(o: OutputRequest, status: "waiting" | "running", before?: BuildCard): BuildCard {
  const k = kindInfo(o.kind);
  return {
    output: o.kind,
    label: k?.label ?? o.kind,
    type: k?.type ?? "",
    name: o.name,
    dry_run: false,
    would: before?.would ?? "create",
    updates_in_place: k?.updates ?? false,
    permissions: before?.permissions ?? { needs: k?.needs ?? [], missing: null, execute: "" },
    status,
  };
}

/** The card of an output whose request failed as a whole: the engine's own error, or no answer at all. */
export function failedCard(o: OutputRequest, e: unknown, before?: BuildCard): BuildCard {
  const err: EngineError = e instanceof EngineCallError ? e.answer : { error: String((e as Error)?.message ?? e), kind: "unexpected" };
  const c = pendingCard(o, "running", before);
  return { ...c, status: err.kind === "no_answer" ? "lost" : "done", refusal: err };
}

export interface CreateRun {
  cards: BuildCard[];
  created: CreatedRef[];
}

/** n207: the dry run's card for this output when the dry run refused it under the same name (an item of that name this
 * Model did not build, or a report that is never updated in place), as Create's card: status done, nothing written.
 * undefined when the dry run did not refuse it, or refused another name (the name was changed since). */
export function dryRunRefused(said: BuildCard | undefined, o: OutputRequest): BuildCard | undefined {
  if (!said?.refusal || said.output !== o.kind || said.name.toLowerCase() !== o.name.toLowerCase()) return undefined;
  return { ...said, status: "done", dry_run: false, created: [] };
}

/** Create, one output after another (n179): each its own request, so a slow output or a closed connection costs only
 * that output, never the answers of the others. `send` is the engine call; `onCard` shows each card as it changes.
 * `created` starts with outputs.json's list, so a re-run skips what is built and retries the rest. */
export async function createEach(
  outputs: OutputRequest[],
  created: CreatedRef[],
  send: (o: OutputRequest, created: CreatedRef[]) => Promise<ManyAnswer>,
  onCard: (cards: BuildCard[]) => void,
  preview?: ManyAnswer
): Promise<CreateRun> {
  const order = createOrder(outputs);
  const before = (k: OutputKind) => preview?.outputs.find((c) => c.output === k);
  let cards = order.map((o) => pendingCard(o, "waiting", before(o.kind)));
  let made = [...created];
  onCard(cards);
  for (let i = 0; i < order.length; i++) {
    const o = requestFor(order[i], order, made);
    let card: BuildCard;
    const refused = dryRunRefused(before(o.kind), o);
    if (refused) {
      // n207: the dry run refused this output (an item of its name that this Model did not build): it is never sent, so
      // its names are never recorded as pending and nothing of someone else's is adopted or overwritten
      card = refused;
      cards = cards.map((c, j) => (j === i ? card : c));
      onCard(cards);
      continue;
    }
    cards = cards.map((c, j) => (j === i ? pendingCard(o, "running", before(o.kind)) : c));
    onCard(cards);
    try {
      const a = await send(o, made);
      const got = a.outputs[0] ?? failedCard(o, new Error("the engine answered without a card"), before(o.kind));
      card = { ...got, status: got.after_run === "waiting" ? "waiting" : "done" };   // n197: held for the pipeline's run
      const drawn = before(o.kind)?.answer?.report;
      if (o.kind === "report" && drawn) card = { ...card, dry_run_visuals: visualCount(drawn) };   // n184: (d)
      made = mergeCreated(made as CreatedItem[], a.created ?? card.created ?? []);
    } catch (e) {
      card = failedCard(o, e, before(o.kind));
    }
    cards = cards.map((c, j) => (j === i ? card : c));
    onCard(cards);
  }
  return { cards, created: made };
}

/** Builder's line under the preview: how many outputs, how many would be refused. */
export function previewLine(a: ManyAnswer): string {
  const ok = a.outputs.length - a.refused;
  const total = a.outputs.length;
  const verbs = a.outputs.filter((c) => !c.refusal && !c.answer?.error);
  const skipped = verbs.filter((c) => c.already_built).length;    // n197: what Create skips, as Create says it
  // n209: a card built from another plan waits for a choice in Create (nothing written): never "updated in place" here
  const waits = verbs.filter((c) => !c.already_built && c.built_from && c.choices?.length).length;
  const upd = verbs.filter((c) => c.would === "update" && !c.already_built && !(c.built_from && c.choices?.length)).length;
  const place = a.build_in ? `${a.build_in.words} ` : "";      // n221: the first line says where the outputs go
  if (!ok) return `${place}Nothing can be built as it stands: each card below says why.`;
  const jobs = a.outputs.find((c) => c.output === "pipeline")?.jobs;
  const runs = jobs && jobs.permission?.granted !== false
    ? [jobs.run_once ? "runs the pipeline once" : "", jobs.schedule ? "sets its schedule" : ""].filter(Boolean)
    : [];
  return (
    place +
    `This is the dry run: nothing is written yet. Create makes ${ok - skipped - waits} of ${total}` +
    (upd ? ` (${upd} updated in place)` : "") +
    (skipped ? `; ${skipped} already built from this plan, will be skipped` : "") +
    (waits ? `; ${waits} built from another plan, Create will ask: Update or a new name` : "") +
    (runs.length ? `, then ${runs.join(" and ")}.` : ". Nothing is run or scheduled.")
  );
}

export function resultLine(a: ManyAnswer): string {
  if (running(a.outputs)) return progressLine(a.outputs);     // n184: "4 of 9 created, 1 creating, 4 waiting"
  const lost = a.outputs.filter((c) => c.status === "lost").length;
  if (lost)
    return `${lost} output(s) gave no answer yet; they may still be running in Fabric. Reopen this item in a minute and choose Create again: what is built is skipped.`;
  const made = (a.created ?? []).length;
  const choose = a.outputs.filter(needsChoice).length;
  if (choose)
    return (
      (made ? `${made} item(s) are in Fabric now. ` : "") +
      `${choose} output(s) were built earlier from another plan, or before Krusgraph recorded plans; nothing was written for them. ` +
      "Choose Update (a dry run first) or a new name on each card."
    );
  return made
    ? `${made} item(s) are in Fabric now. Open each one there; what is still to do is listed under it.`
    : "Nothing was created: each card below says why.";
}

/** The choices the outputs view starts from: what outputs.json saved (phase 1 saved the API for GraphQL), the rest off
 * with a default name. A new item starts with the API for GraphQL on, as before. */
export function choicesFor(
  saved: OutputChoice[],
  displayName: string,
  previous?: { displayName?: string; created?: CreatedItem[] }
): OutputChoice[] {
  // n184: every default is "<lakehouse>_<suffix>" (demo_lh_silver ... demo_lh_api ... demo_lh_app). A name still at the
  // default of the name used before (the Model item's own, before a lakehouse was chosen: "demo_api"; or the lakehouse
  // chosen before) follows the new lakehouse, unless an item of that name was already built. A name typed by hand stays.
  const built = new Set((previous?.created ?? []).map((c) => c.name.toLowerCase()));
  const old = previous?.displayName;
  return KINDS.map((k) => {
    const c = saved.find((x) => x.type === k.kind);
    if (!c) return { type: k.kind, name: defaultName(k.kind, displayName), enabled: k.kind === "graphql" && saved.length === 0 };
    const stale = old !== undefined && c.name === defaultName(k.kind, old) && !built.has(c.name.toLowerCase());
    return stale ? { ...c, name: defaultName(k.kind, displayName) } : c;
  });
}

/** The Create button's words: Create, or Create and update when an output is updated in place. */
export function createLabel(a: ManyAnswer | undefined): string {
  const upd = (a?.outputs ?? []).some((c) => !c.refusal && !c.answer?.error && c.would === "update");
  return upd ? "Create and update" : "Create";
}
