/**
 * The Krusgraph Model's item definition: what Fabric stores for the item (docs/WORKLOAD-FEASIBILITY.md section 3).
 *
 * Four text parts, each JSON with its own version so an older definition restored from Git can be read and migrated:
 *   review.json   the review file the engine wrote (fabric_backend/review.py): plan, each key and relationship with its
 *                 rule, review status and check status. Names, types, rules, decisions and counts only: never a row
 *                 value, a token or a secret. Its own format and version come from the engine.
 *   source.json   which lakehouse and schema the model reads
 *   outputs.json  what to build (n174: every output the MCP tools build), the ids of what was created, and the data
 *                 product that bundles them (name, items, owner not chosen yet, the plan's version)
 *   item.json     the definition format version and the editor's last view
 *
 * Pure functions, no React and no Fabric client, so they run in unit tests (ModelItemDefinition.test.ts).
 */

export const DEFINITION_VERSION = 1;
export const ITEM_FORMAT = "krusgraph-model";
export const PARTS = {
  review: "review.json",
  source: "source.json",
  outputs: "outputs.json",
  item: "item.json",
} as const;

export type ModelView = "empty" | "review" | "outputs" | "preview" | "result" | "product";
export type ReviewStatus = "proposed" | "accepted" | "rejected" | "open";

/** One key or relationship of the review file, as review.py writes it. */
export interface ReviewItem {
  id: string;
  type: "key" | "relationship";
  rule: string;
  columns: string[];
  table?: string;
  source?: string;
  target?: string;
  target_columns?: string[];
  review: ReviewStatus;
  reason?: string;
  check?: { status: string; verdict?: string; checked_at?: string; result?: Record<string, number> };
  proposed?: { columns: string[]; rule: string };
}

/** The review file (format "krusgraph-review"); only the fields the editor reads are typed. */
export interface ReviewFile {
  format: "krusgraph-review";
  version: number;
  plan_id: string;
  source: { platform?: string; source?: string; schema?: string };
  items: ReviewItem[];
  open_questions?: { about: string; question: string }[];
  [key: string]: unknown;
}

export interface SourceDefinition {
  version: number;
  platform: "fabric";
  workspaceId: string;
  itemId: string;
  itemType: string;
  displayName: string;
  schema: string;
  /** n201: for a read-only source, the lakehouse the build writes to; absent means the workspace's first (the default).
   * n221: also the lakehouse of the build's workspace when the source is in another one; workspaceId says which
   * workspace it is in (absent: the source's) */
  target?: { itemId: string; displayName: string; workspaceId?: string };
  /** n221: where the outputs are built: this item's workspace (absent, the default) or the source's */
  buildIn?: "item" | "source";
  /** n221: the lakehouse Create may make in the build's workspace for silver and gold (ticked by the person) */
  createLakehouse?: string;
}

export interface CreatedItem {
  type: string;
  id: string;
  name: string;
  workspace: string;
  /** n174: which output made it (silver_notebook, semantic_model, ...); absent in phase 1's API for GraphQL */
  output?: string;
  /** n180: the plan it was built from (absent for items built before n180: "plan unknown") */
  plan?: PlanMark;
  /** n185: a data agent Krusgraph published in Fabric */
  published?: boolean;
  /** n197: in the data product, an item an earlier Create of this item built */
  earlier?: boolean;
  /** n198: a leftover adopted on the Data product page: when and by whom */
  adopted_at?: string;
  adopted_by?: string;
}

/** n198: an item Retire deleted from Fabric (product_life.retire): out of created, kept here with when and by whom. */
export interface RemovedItem {
  id: string;
  type: string;
  name: string;
  workspace: string;
  output?: string;
  removed_at: string;
  by: string;
}

/** n180: what an output was built from (workload_api.plan_mark): the review's plan id and schema fingerprint, the exact
 * schema name and the number of links left after the review. */
export interface PlanMark {
  plan_id?: string;
  schema_fingerprint?: string;
  schema?: string;
  links?: number;
}

export interface OutputChoice {
  /** phase 1: "graphql"; n174: every kind of engineClient.OutputKind */
  type: string;
  name: string;
  enabled: boolean;
  writable?: false;
  /** a report's existing semantic model; empty for the model this item builds */
  model?: string;
  /** n181: the App (Rayfin, preview)'s ticked key figures, list pages and charts (option ids); absent: the defaults.
   * n189: its filters, each chart's type, the order of the pages and the accent */
  app?: {
    kpis: string[]; tables: string[]; charts: string[]; filters?: string[];
    chart_types?: Record<string, "bar" | "line" | "table">; page_order?: string[]; accent?: string;
  };
  /** n209: the App's last package (dry run or Create): the choices it was made with, its pages, the package and the
   * one command (appWords.AppPackageRecord), so an App built earlier shows them on reopen; absent before n209 */
  app_package?: AppPackageStored;
  /** n185: the pipeline's Run once and Schedule (both off unless ticked) */
  jobs?: { run_once: boolean; schedule: { every: "day" | "hours"; at: string; hours?: number; time_zone: string; start?: string } | null };
  /** n185: the data agent's layer and its Publish / Microsoft 365 Copilot ticks (both off unless ticked) */
  agent?: { layer: "silver" | "gold" | "source"; publish: boolean; copilot: boolean };
}

/** n209: as appWords.AppPackageRecord; read through appWords.readAppRecord, which checks its shape. */
export interface AppPackageStored {
  name: string;
  at?: string;
  dry_run?: boolean;
  chosen: { kpis: string[]; tables: string[]; charts: string[]; filters?: string[]; chart_types?: Record<string, "bar" | "line" | "table">;
    page_order?: string[]; accent?: string };
  labels?: Record<string, string>;
  pages?: { id: string; title: string; shows: string[] }[];
  package?: { filename: string; zip_base64: string };
  one_command?: { command: string; steps: string[]; why?: string };
  commands?: { step: string; command: string }[];
}

/** n209: an App choice's ticks and package record, kept only when they have the shape the editor writes (an older or
 * hand-edited outputs.json with something else reads as no choices: the defaults, as before). */
export function cleanChoice(c: OutputChoice): OutputChoice {
  const lists = (x: unknown): boolean => !!x && typeof x === "object"
    && ["kpis", "tables", "charts"].every((k) => Array.isArray((x as Record<string, unknown>)[k]));
  const { app, app_package, ...rest } = c;
  return {
    ...rest,
    ...(app !== undefined && lists(app) ? { app } : {}),
    ...(app_package && typeof app_package === "object" && typeof app_package.name === "string" && lists(app_package.chosen) ? { app_package } : {}),
  };
}

/** n185: the runs Create started and the schedules it made, so a later cleanup can remove the schedule. */
export interface PipelineJobsRecord {
  runs: { run_id: string; pipeline_id: string; pipeline: string; workspace: string; started?: string; status: string; at: string }[];
  schedules: { id: string; pipeline_id: string; pipeline: string; workspace: string; every: string; at?: string; hours?: number;
    time_zone?: string; start?: string; next_run?: string; mode?: string; recorded: string }[];
}

/** n174: the data product that bundles what the item built: only what the engine answered (workload_api._product). */
export interface ProductDefinition {
  name: string;
  owner: string | null;
  owner_note?: string;
  /** n198: when and by whom the owner was chosen on the Data product page */
  owner_set?: { at: string; by: string };
  plan: { plan_id?: string; schema_fingerprint?: string; review_version?: number };
  items: CreatedItem[];
  domains: { name: string; tables: string[]; why?: string }[];
  built_at?: string;
}

export interface OutputsDefinition {
  version: number;
  outputs: OutputChoice[];
  created: CreatedItem[];
  /** n174: optional, so a version 1 file without it reads as before */
  product?: ProductDefinition;
  /** n184: the finish of the last Create (createWords.LastCreate), so reopening shows it with its date; optional */
  last_create?: LastCreateStored;
  /** n185: run ids and schedule ids of the pipeline (jobsWords.recordRun / recordSchedule); optional */
  pipeline_jobs?: PipelineJobsRecord;
  /** n197: items a Create step sent before its answer came (createRun.withPending); adopted when Fabric finishes them */
  pending?: { output: string; type: string; name: string; at?: string }[];
  /** n197: the Create in progress or last run: its id, outputs and operation ids (createRun.CreateRunRecord) */
  create_run?: unknown;
  /** n198: items Retire deleted from Fabric, with when and by whom (productWords.withRemoved) */
  removed?: RemovedItem[];
}

/** n184: as createWords.LastCreate; read through createWords.readLastCreate, which checks its shape. */
export interface LastCreateStored {
  at: string;
  item: string;
  outputs: { output: string; label: string; name: string; state: string; reason?: string; refresh?: string }[];
}

export interface ItemSettings {
  version: number;
  format: typeof ITEM_FORMAT;
  view: ModelView;
  /** n173: Thinker's questions the person answered by keeping things as they are ({about: "keep"}). Optional, so a
   * version 1 definition without it reads as before. */
  answers?: Record<string, string>;
}

export interface ModelDefinition {
  item: ItemSettings;
  source?: SourceDefinition;
  outputs: OutputsDefinition;
  review?: ReviewFile;
}

/** The parts as the workload client sends and receives them (ItemDefinitionPart). */
export interface DefinitionPart {
  path: string;
  payload: string;
  payloadType: string;
}

export class DefinitionError extends Error {}

export function emptyDefinition(): ModelDefinition {
  return {
    item: { version: DEFINITION_VERSION, format: ITEM_FORMAT, view: "empty" },
    outputs: { version: DEFINITION_VERSION, outputs: [], created: [] },
  };
}

/** The default API name for a source: the lakehouse name plus _api, in the characters Fabric item names allow (the same
 * pattern as buildWords.defaultName, n184). */
export function defaultApiName(displayName: string): string {
  const base = (displayName || "model").replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "") || "model";
  return `${base}_api`.slice(0, 123);
}

// ------------------------------------------------------------------ base64 that keeps non-ASCII names intact ------

export function encodeJson(value: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(value, null, 2));
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin);
}

export function decodeJson<T = unknown>(payload: string): T {
  const bin = atob(payload);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}

// ------------------------------------------------------------------ save -----------------------------------------------

/** The definition as parts to save. A part is left out until it has content (no review before a source is chosen). */
export function toParts(def: ModelDefinition): DefinitionPart[] {
  const part = (path: string, value: unknown): DefinitionPart => ({ path, payload: encodeJson(value), payloadType: "InlineBase64" });
  const parts = [part(PARTS.item, { ...def.item, version: DEFINITION_VERSION, format: ITEM_FORMAT })];
  if (def.source) parts.push(part(PARTS.source, { ...def.source, version: DEFINITION_VERSION }));
  parts.push(part(PARTS.outputs, { ...def.outputs, version: DEFINITION_VERSION }));
  if (def.review) parts.push(part(PARTS.review, def.review));
  return parts;
}

// ------------------------------------------------------------------ load and migrate -----------------------------------

function versionOf(obj: { version?: unknown } | undefined, part: string): number {
  if (!obj) return DEFINITION_VERSION;
  const v = obj.version;
  if (v === undefined) return 1; // written before the field existed: read as version 1
  if (typeof v !== "number" || !Number.isInteger(v) || v < 1) {
    throw new DefinitionError(`${part} has an invalid version: ${JSON.stringify(v)}`);
  }
  if (v > DEFINITION_VERSION) {
    throw new DefinitionError(`${part} was saved by a newer Krusgraph (version ${v}); this editor reads version ${DEFINITION_VERSION}.`);
  }
  return v;
}

/** n185: outputs.json's pipeline_jobs, kept only when it has the shape the editor writes. */
export function isJobsRecord(x: unknown): x is PipelineJobsRecord {
  const v = x as PipelineJobsRecord;
  return !!v && typeof v === "object" && Array.isArray(v.runs) && Array.isArray(v.schedules)
    && v.schedules.every((s) => s && typeof s.id === "string") && v.runs.every((r) => r && typeof r.run_id === "string");
}

/** Version 1 is the first format, so migrating means filling defaults. Later versions add a step here per version. */
export function migrate(def: ModelDefinition): ModelDefinition {
  return {
    item: {
      version: DEFINITION_VERSION,
      format: ITEM_FORMAT,
      view: def.item?.view ?? (def.review ? "review" : "empty"),
      ...(def.item?.answers && typeof def.item.answers === "object" ? { answers: def.item.answers } : {}),
    },
    source: def.source ? { ...def.source, version: DEFINITION_VERSION, schema: def.source.schema || "dbo" } : undefined,
    outputs: {
      version: DEFINITION_VERSION,
      outputs: (def.outputs?.outputs ?? []).filter((c) => c && typeof c === "object").map(cleanChoice),   // n209
      created: def.outputs?.created ?? [],
      ...(def.outputs?.product && typeof def.outputs.product === "object" ? { product: def.outputs.product } : {}),
      ...(def.outputs?.last_create && typeof def.outputs.last_create === "object" ? { last_create: def.outputs.last_create } : {}),
      ...(isJobsRecord(def.outputs?.pipeline_jobs) ? { pipeline_jobs: def.outputs.pipeline_jobs } : {}),   // n185
      ...(Array.isArray(def.outputs?.pending) ? { pending: def.outputs.pending.filter((x) => x && typeof x.name === "string" && typeof x.type === "string") } : {}),   // n197
      ...(def.outputs?.create_run && typeof def.outputs.create_run === "object" ? { create_run: def.outputs.create_run } : {}),   // n197
      ...(Array.isArray(def.outputs?.removed) ? { removed: def.outputs.removed.filter((x) => x && typeof x.id === "string" && typeof x.removed_at === "string") } : {}),   // n198
    },
    review: def.review,
  };
}

/** The parts Fabric returned (getItemDefinition) as a definition. Unknown parts (.platform and others) are ignored. */
export function fromParts(parts: DefinitionPart[] | undefined): ModelDefinition {
  if (!parts || parts.length === 0) return emptyDefinition();
  const read = <T>(path: string): T | undefined => {
    const p = parts.find((x) => x.path === path);
    if (!p) return undefined;
    try {
      return decodeJson<T>(p.payload);
    } catch {
      throw new DefinitionError(`${path} is not valid JSON`);
    }
  };
  const item = read<ItemSettings>(PARTS.item);
  const source = read<SourceDefinition>(PARTS.source);
  const outputs = read<OutputsDefinition>(PARTS.outputs);
  const review = read<ReviewFile>(PARTS.review);
  versionOf(item, PARTS.item);
  versionOf(source, PARTS.source);
  versionOf(outputs, PARTS.outputs);
  if (item && item.format !== undefined && item.format !== ITEM_FORMAT) {
    throw new DefinitionError(`item.json is not a ${ITEM_FORMAT} definition`);
  }
  if (review && review.format !== "krusgraph-review") {
    throw new DefinitionError("review.json is not a Krusgraph review file");
  }
  return migrate({ item: item as ItemSettings, source, outputs: outputs as OutputsDefinition, review });
}

// ------------------------------------------------------------------ review helpers ------------------------------------

const ORDER: Record<ReviewStatus, number> = { open: 0, proposed: 1, accepted: 2, rejected: 3 };

/** List-first review: open items first, then what is still only proposed, then decided ones; keys before relationships. */
export function sortForReview(items: ReviewItem[]): ReviewItem[] {
  return [...items].sort(
    (a, b) =>
      ORDER[a.review] - ORDER[b.review] ||
      (a.type === b.type ? 0 : a.type === "key" ? -1 : 1) ||
      a.id.localeCompare(b.id)
  );
}

/** The rule pill: K for a key rule (K0-K5), R for a relationship rule (R0-R5, confirmed). */
export function rulePill(item: ReviewItem): "K" | "R" {
  return item.type === "key" ? "K" : "R";
}

export function describe(item: ReviewItem): string {
  if (item.type === "key") return `${item.table}: ${item.columns.join(" + ")}`;
  return `${item.source}.${item.columns.join("+")} → ${item.target}.${(item.target_columns ?? []).join("+")}`;
}

/** The review with one item's decision changed; the engine re-reads the decisions when the item is re-opened or built. */
export function decide(review: ReviewFile, id: string, status: ReviewStatus, reason = ""): ReviewFile {
  if (!review.items.some((it) => it.id === id)) throw new DefinitionError(`no item ${id} in the review`);
  return { ...review, items: review.items.map((it) => (it.id === id ? { ...it, review: status, reason } : it)) };
}

export function counts(review: ReviewFile | undefined): Record<ReviewStatus, number> & { keys: number; relationships: number } {
  const c = { open: 0, proposed: 0, accepted: 0, rejected: 0, keys: 0, relationships: 0 };
  for (const it of review?.items ?? []) {
    c[it.review] += 1;
    if (it.type === "key") c.keys += 1;
    else c.relationships += 1;
  }
  return c;
}
