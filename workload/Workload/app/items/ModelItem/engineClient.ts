/**
 * Calls the Krusgraph engine API (fabric_backend/workload_api.py) with a token the Fabric host issues for the
 * workload's own Entra app. The engine exchanges it on-behalf-of the signed-in user, so every read and every created
 * item runs with the user's own Fabric permissions.
 *
 * Configuration (workload/Workload/.env.dev, see docs/WORKLOAD-DEV.md):
 *   KRUSGRAPH_ENGINE_URL    the engine's base URL; empty in development, where the dev server forwards /workload/v1
 *                           to the local Python server (devServer/webpack.dev.js)
 *   KRUSGRAPH_ENGINE_SCOPE  <the workload app's Application ID URI>/user_impersonation
 *
 * Hosted (n168, https://workload.krusgraph.com): the image is built with both empty. The editor then calls
 * /workload/v1 on its own host, and the scope comes from <meta name="krusgraph-engine-scope"> that the server writes
 * into index.html from its own KRUSGRAPH_WORKLOAD_APP_ID_URI (fabric_backend/workload_host.py), so a new Entra app needs
 * no new image.
 */
import { WorkloadClientAPI } from "@ms-fabric/workload-client";
import { PlanMark, ReviewFile } from "./ModelItemDefinition";
import { MapData } from "./cardMap";
import { CheckTotals } from "./modelWords";
import { getWorkloadName } from "../../controller/ConfigurationController";

export interface EngineError {
  error: string;
  kind: string;
  hint?: string;
}

export interface ReviewAnswer {
  review: ReviewFile;
  summary: string;
  attention: string[];
  counts: { keys: number; relationships: number; review: Record<string, number>; open_questions: number };
  /** n173: the MCP Apps cards' map of the review (workload_api.map_of) */
  map?: MapData;
  note: string;
  /** n175: the schema typed differed from the lakehouse's only by case ("Shop" typed, "shop" read); every query used `used`. */
  schema_used?: SchemaUsed;
}

export interface SchemaUsed {
  asked: string;
  used: string;
  note: string;
}

/** n173: /workload/v1/check, the review checked against the rows. */
export interface CheckAnswer extends ReviewAnswer {
  check: CheckTotals & {
    failed: { id: string; type: "key" | "relationship"; verdict: string; orphans?: number; duplicates?: number; nulls?: number }[];
  };
  questions: { about: string; question: string }[];
}

/** The person's own answers to Thinker's questions, sent with /review. */
export interface Corrections {
  keys?: Record<string, string[]>;
  confirmed?: { source: string; source_cols: string[]; target: string; target_cols: string[] }[];
}

export interface LeftOut {
  id: string;
  what: string;
  because: string;
}

export interface BuildAnswer {
  dry_run: boolean;
  output: "graphql";
  summary: string;
  name?: string;
  exists?: boolean;
  would?: "create" | "update";
  changes?: Record<string, unknown[]>;
  checks_passed?: string[];
  not_checked?: string;
  /** n173: the review's own check against the rows, so the dry run says what passed */
  row_check?: CheckTotals;
  skipped_relationships?: unknown[];
  left_out_by_review: LeftOut[];
  note?: string;
  created?: { type: string; id: string; name: string; workspace: string }[];
  endpoint?: string;
  portal_steps?: string[];
  result?: { status: string; id?: string };
}

// ------------------------------------------------------------------ n174: every output ---------------------------------

export type OutputKind =
  | "silver_notebook"
  | "gold_views"
  | "pipeline"
  | "semantic_model"
  | "report"
  | "graphql"
  | "ontology"
  | "data_agent";

/** One chosen output: its kind and the name of the item; a report may name an existing semantic model. */
export interface OutputRequest {
  kind: OutputKind;
  name: string;
  model?: string;
}

export interface CreatedRef {
  type: string;
  id: string;
  name: string;
  workspace: string;
  /** the output that made it (an OutputKind; a string so outputs.json's items fit) */
  output?: string;
  label?: string;
  /** n180: the plan it was built from; outputs.json keeps it */
  plan?: PlanMark;
}

/** n180: an existing item was built from another plan, or by Krusgraph before plans were recorded. */
export interface BuiltFrom {
  status: "different" | "unknown";
  was: PlanMark | null;
  now: PlanMark;
  /** "built from a different plan (schema Shop, 6 links; now shop, 7 links)" or "built by Krusgraph, plan unknown (…)" */
  words: string;
}

/** n180: what an existing item holds, read from its definition; only what was read (an absent count is not zero). */
export interface ExistingCounts {
  cells?: number;
  views?: number;
  pages?: number;
  visuals?: number;
  tables?: number;
  relationships?: number;
  data_sources?: number;
  questions?: number;
}

/** An output the engine did not call its tool for (a name taken by someone else, a missing permission), or the
 * consent the dry run already sees: error, kind and, for consent, the scope and the Entra steps. */
export interface Refusal extends EngineError {
  scope?: string;
  missing?: string[];
  entra_steps?: string[];
  existing?: { type: string; id: string; name: string };
}

export interface BuildCard {
  output: OutputKind;
  /** n179, Create one output per request: waiting, running, done, or lost (the browser did not get the answer) */
  status?: "waiting" | "running" | "done" | "lost";
  /** n179: every item of the output was already in the workspace from an earlier Create; nothing was written */
  already_built?: boolean;
  label: string;
  type: string;
  name: string;
  dry_run: boolean;
  would: "create" | "update";
  updates_in_place: boolean;
  permissions: { needs: string[]; missing: string[] | null; execute: string };
  model?: string;
  refusal?: Refusal;
  consent?: Refusal;
  /** the MCP tool's own answer to the same arguments */
  answer?: Record<string, any> & { error?: string; kind?: string; hint?: string; entra_steps?: string[] };
  created?: CreatedRef[];
  portal_steps?: string[];
  /** n180: built from another plan or plan unknown; the person chooses (choices), nothing was written */
  built_from?: BuiltFrom;
  choices?: ("update" | "new_name")[];
  /** n180: the items already in the workspace (to open them); not counted as built from this plan */
  existing_items?: CreatedRef[];
  existing?: ExistingCounts;
  /** n180: an Update's dry run: what its Create sends back in `confirm` */
  confirm_update?: string;
}

export interface FlowNode {
  id: string;
  column: "bronze" | "silver" | "gold" | "built" | "pipeline";
  label: string;
  lines: string[];
  pills: string[];
  built: boolean;
  code: string | null;
  language?: string;
  code_title?: string;
  under?: "silver" | "gold" | "built";
  table?: string;
  notebook?: string;
  kind_label?: string;
  exists?: boolean;
}

export interface FlowEdge {
  from: string;
  to: string;
  label?: string;
  rule?: string;
  built: boolean;
}

export interface DataFlow {
  columns: { id: string; title: string }[];
  nodes: FlowNode[];
  edges: FlowEdge[];
  pipeline: { name: string; steps: string[] } | null;
  notes: string[];
  said: string;
}

export interface DataProduct {
  name: string;
  owner: string | null;
  owner_note: string;
  plan: { plan_id?: string; schema_fingerprint?: string; review_version?: number };
  source: { lakehouse: string; schema: string };
  items: (CreatedRef & { would?: "create" | "update" })[];
  domains: { name: string; tables: string[]; why: string }[];
  unassigned: string[];
  from: string;
}

export interface ManyAnswer {
  dry_run: boolean;
  outputs: BuildCard[];
  order: OutputKind[];
  left_out_by_review: LeftOut[];
  row_check?: CheckTotals;
  product?: DataProduct;
  flow?: DataFlow | null;
  refused: number;
  /** n180: outputs whose existing items wait for Update or a new name */
  to_decide?: number;
  note: string;
  created?: CreatedRef[];
}

export interface SourceRequest {
  workspace: string;
  source: string;
  source_name: string;
  schema: string;
}

export class EngineCallError extends Error {
  constructor(public readonly answer: EngineError, public readonly status: number) {
    super(answer.error);
  }
}

/** n179: the answer to a request that never came back. The browser says only "Failed to fetch" (a closed connection, a
 * network change, the server restarting) or the editor stopped waiting; the server may still have done the work. */
export function lostAnswer(route: string, seconds: number, aborted: boolean): EngineError {
  return {
    error: aborted
      ? `No answer from the Krusgraph engine after ${seconds} s; the editor stopped waiting.`
      : `The connection to the Krusgraph engine closed after ${seconds} s without an answer ("Failed to fetch").`,
    kind: "no_answer",
    hint:
      route === "build"
        ? "It may still be running in Fabric. Reopen the item in a minute and choose Create again: what is already built is shown as built and skipped, and only the rest is tried."
        : "Check the connection and try again. If Krusgraph Model keeps loading, ask IT to allow workload.krusgraph.com and krusgraph.com (krusgraph.com/it#network).",
  };
}

/** One output's Create can take minutes (an ontology makes an eventhouse); the ingress cuts a request at 240 s
 * (Azure Container Apps, "Request time out is 240 seconds"), so the editor waits a little less than that. */
export const BUILD_WAIT_MS = 230_000;

/** n176: of several scopes, the one whose URI names this workload as a whole path part, else the first. */
export function pickScope(scopes: string[], workloadName?: string): string {
  const list = scopes.map((s) => s.trim()).filter((s) => s.length > 0);
  if (workloadName) {
    const mine = list.find((s) => s.split("/").includes(workloadName));
    if (mine) {
      return mine;
    }
  }
  return list[0] ?? "";
}

/**
 * The scope to ask the Fabric host for: the build's KRUSGRAPH_ENGINE_SCOPE, else the hosting server's meta tags. While
 * Org.Krusgraph and Krusgraph.Modeler both run (n176) the server lists every scope in krusgraph-engine-scopes and the
 * editor takes the one of its own workload; krusgraph-engine-scope (one value) is the older form.
 */
export function engineScope(
  built: string | undefined,
  doc?: { querySelector(selector: string): Element | null },
  workloadName?: string
): string {
  if (built) {
    return built;
  }
  const many = (doc?.querySelector('meta[name="krusgraph-engine-scopes"]')?.getAttribute("content") || "").split(/\s+/);
  const picked = pickScope(many, workloadName);
  if (picked) {
    return picked;
  }
  const meta = doc?.querySelector('meta[name="krusgraph-engine-scope"]');
  return (meta?.getAttribute("content") || "").trim();
}

export type Fetch = (url: string, init: RequestInit) => Promise<Response>;

async function call<T>(
  workloadClient: WorkloadClientAPI,
  route: "review" | "check" | "build" | "schemas",
  body: object,
  waitMs = 0,
  fetchImpl: Fetch = (u, i) => fetch(u, i)
): Promise<T> {
  const scope = engineScope(process.env.KRUSGRAPH_ENGINE_SCOPE, typeof document === "undefined" ? undefined : document,
    getWorkloadName());
  if (!scope) {
    throw new EngineCallError({ error: "No engine scope: set KRUSGRAPH_ENGINE_SCOPE in the workload's .env file, or KRUSGRAPH_WORKLOAD_APP_ID_URI on the hosting server", kind: "server_config" }, 0);
  }
  const { token } = await workloadClient.auth.acquireFrontendAccessToken({ scopes: [scope] });
  const base = (process.env.KRUSGRAPH_ENGINE_URL || "").replace(/\/$/, "");
  const started = Date.now();
  const abort = typeof AbortController === "undefined" ? undefined : new AbortController();
  const timer = waitMs && abort ? setTimeout(() => abort.abort(), waitMs) : undefined;
  let response: Response;
  try {
    response = await fetchImpl(`${base}/workload/v1/${route}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      ...(abort ? { signal: abort.signal } : {}),
    });
  } catch (e) {
    // n179: "Failed to fetch" carries no reason; say what it means for this request instead
    throw new EngineCallError(lostAnswer(route, Math.round((Date.now() - started) / 1000), !!abort?.signal.aborted), 0);
  } finally {
    if (timer) clearTimeout(timer);
  }
  let answer: unknown;
  try {
    answer = await response.json();
  } catch {
    answer = { error: `The engine answered ${response.status} without JSON`, kind: "unexpected" };
  }
  if (!response.ok || (answer as EngineError).error) {
    throw new EngineCallError(answer as EngineError, response.status);
  }
  return answer as T;
}

export function review(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  previous?: ReviewFile,
  corrections: Corrections = {}
): Promise<ReviewAnswer> {
  return call<ReviewAnswer>(workloadClient, "review", { ...source, previous: previous ?? null, ...corrections });
}

/** Counts the review's keys and relationships in the rows (validate_plan's queries). Read-only; changes nothing. */
export function check(workloadClient: WorkloadClientAPI, source: SourceRequest, reviewFile: ReviewFile): Promise<CheckAnswer> {
  return call<CheckAnswer>(workloadClient, "check", { ...source, review: reviewFile });
}

export function build(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  name: string,
  reviewFile: ReviewFile,
  dryRun: boolean
): Promise<BuildAnswer> {
  return call<BuildAnswer>(workloadClient, "build", {
    ...source,
    name,
    review: reviewFile,
    outputs: ["graphql"],
    dry_run: dryRun,
  });
}

/** n179: the source's schemas with their table counts, to choose from (the schema is never typed). */
export interface SchemasAnswer {
  schemas: { schema: string; tables: number }[];
  preselect: string | null;
  note: string;
}

export function schemas(
  workloadClient: WorkloadClientAPI,
  source: { workspace: string; source: string; source_name: string }
): Promise<SchemasAnswer> {
  return call<SchemasAnswer>(workloadClient, "schemas", source);
}

/** n179: Create of one output (only: [its kind]; skip_built: already built is shown as built, not written again). */
export function buildOne(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  output: OutputRequest,
  all: OutputRequest[],
  reviewFile: ReviewFile,
  created: CreatedRef[],
  fetchImpl?: Fetch
): Promise<ManyAnswer> {
  // every chosen output goes along (the pipeline runs the silver and gold notebooks chosen with it); `only` is built
  const outputs = all.map((o) => (o.kind === output.kind ? output : o));
  return call<ManyAnswer>(
    workloadClient,
    "build",
    { ...source, outputs, only: [output.kind], review: reviewFile, dry_run: false, product: null, created, skip_built: true },
    BUILD_WAIT_MS,
    fetchImpl
  );
}

/** n180: Update of one output built from another plan: dryRun true first (nothing is written; the card gives
 * confirm_update), then dryRun false with that confirmation, which the engine requires before it writes. */
export function updateOne(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  output: OutputRequest,
  all: OutputRequest[],
  reviewFile: ReviewFile,
  created: CreatedRef[],
  dryRun: boolean,
  confirm?: string,
  fetchImpl?: Fetch
): Promise<ManyAnswer> {
  return call<ManyAnswer>(workloadClient, "build", updateBody(source, output, all, reviewFile, created, dryRun, confirm), BUILD_WAIT_MS, fetchImpl);
}

export function updateBody(
  source: SourceRequest,
  output: OutputRequest,
  all: OutputRequest[],
  reviewFile: ReviewFile,
  created: CreatedRef[],
  dryRun: boolean,
  confirm?: string
): Record<string, unknown> {
  if (!dryRun && !confirm) throw new Error("An update is sent only after its dry run: confirm_update is missing.");
  const outputs = all.map((o) => (o.kind === output.kind ? output : o));
  return {
    ...source, outputs, only: [output.kind], review: reviewFile, dry_run: dryRun, product: null, created,
    update: [output.kind], ...(dryRun ? {} : { confirm: { [output.kind]: confirm } }),
  };
}

/** n179: after the outputs, the data product and the data flow of the whole Create, from the created ids (no tool runs). */
export function finish(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  outputs: OutputRequest[],
  reviewFile: ReviewFile,
  product: { name: string } | null,
  created: CreatedRef[]
): Promise<ManyAnswer> {
  return call<ManyAnswer>(workloadClient, "build", { ...source, outputs, review: reviewFile, dry_run: false, product, created, finish: true });
}

/** n174: several outputs in one call, each through its MCP tool (workload_api.run_build_many). `created` is
 * outputs.json's list: the items this Model built and may update in place; anything else of the same name is refused. */
export function buildMany(
  workloadClient: WorkloadClientAPI,
  source: SourceRequest,
  outputs: OutputRequest[],
  reviewFile: ReviewFile,
  dryRun: boolean,
  product: { name: string } | null,
  created: CreatedRef[]
): Promise<ManyAnswer> {
  return call<ManyAnswer>(workloadClient, "build", {
    ...source,
    outputs,
    review: reviewFile,
    dry_run: dryRun,
    product,
    created,
  });
}
