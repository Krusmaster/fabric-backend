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
  | "data_agent"
  | "rayfin_app";

/** One chosen output: its kind and the name of the item; a report may name an existing semantic model. */
export interface OutputRequest {
  kind: OutputKind;
  name: string;
  model?: string;
  /** n181: the App's ticked options (ids from its dry run); absent: the defaults */
  app?: AppChoices;
  /** n185: the pipeline's Run once and Schedule, both off unless ticked */
  jobs?: PipelineJobs;
  /** n185: the data agent's layer and its Publish / Microsoft 365 Copilot ticks, both off unless ticked */
  agent?: AgentOptions;
}

/** n185: a schedule as the engine takes it (pipeline_jobs.schedule_spec). */
export interface ScheduleChoice {
  every: "day" | "hours";
  at: string;
  hours?: number;
  time_zone: string;
  /** YYYY-MM-DD; absent: tomorrow */
  start?: string;
}

export interface PipelineJobs {
  run_once: boolean;
  schedule: ScheduleChoice | null;
}

export interface AgentOptions {
  layer: "silver" | "gold" | "source";
  publish: boolean;
  copilot: boolean;
}

/** n185: one activity of a pipeline run (pipeline_jobs.activities). */
export interface RunActivity {
  activity: string;
  status: "Succeeded" | "Failed" | "Running";
  seconds?: number | null;
  duration?: string;
  error?: string;
}

/** n185: a pipeline run as the card shows it (pipeline_jobs.read_run / wait_run / start_run). */
export interface PipelineRun {
  status: "Running" | "Succeeded" | "Failed" | "NotStarted" | "Unknown";
  /** Fabric's own status of the job instance (NotStarted: queued, InProgress, Completed, Failed, ...) */
  fabric_status?: string;
  run_id?: string;
  started?: string;
  duration?: string;
  why?: string;
  note?: string;
  still_running?: boolean;
  links?: { run?: string; pipeline?: string };
  activities?: RunActivity[];
  kind?: string;
  scope?: string;
  manual?: string[];
}

export interface ScheduleResult {
  status: "Succeeded" | "Failed";
  mode?: "created" | "updated";
  id?: string;
  next_run?: string;
  next_run_words?: string;
  words?: string;
  note?: string;
  why?: string;
  kind?: string;
  others_untouched?: number;
}

/** n185: the pipeline card's Run once and Schedule (workload_api._jobs_card). */
export interface JobsCard {
  run_once: boolean;
  schedule: ScheduleChoice | null;
  permission: { granted: boolean | null; scope: string; or: string; why?: string; entra_steps?: string[]; az?: string; consent_note?: string; manual?: string[] };
  words: string[];
  run?: PipelineRun;
  schedule_result?: ScheduleResult;
}

export interface CopilotRequirement {
  requirement: string;
  status: "ok" | "missing" | "unverified";
  detail: string;
  doc: string;
}

/** n185: the data agent card's layer, examples and publishing (workload_api.agent_card). */
export interface AgentCard {
  layer: AgentOptions["layer"];
  layer_words?: string;
  publish: boolean;
  copilot: boolean;
  where_examples: string;
  selection?: { layer: string; schema: string; selected: number | null; deselected: number; one_layer: boolean; words: string };
  examples?: { status: string; count?: number; valid?: number; invalid?: number; validating?: number; invalid_examples?: { question: string; reason?: string }[];
    /** n197: not_checked: why (the run writes the tables) */
    words?: string; rechecked?: number };
  words?: string[];
  decision?: { publish: boolean; state: "draft" | "waiting" | "publish"; why: string };
  published?: boolean;
  copilot_preflight?: { requirements: CopilotRequirement[]; missing: number; unverified: number; words: string; step: string };
  copilot_step?: string;
}

/** n181: what the App (Rayfin, preview) shows, as option ids (rayfin_app.options). n189: which filters, each chart's
 * type, the order of the pages and the accent; absent: the defaults. */
export interface AppChoices {
  kpis: string[];
  tables: string[];
  charts: string[];
  filters?: string[];
  chart_types?: Record<string, AppChartType>;
  page_order?: string[];
  accent?: string;
}

export type AppChartType = "bar" | "line" | "table";

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
  /** n185: a data agent Krusgraph published in Fabric */
  published?: boolean;
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
  /** n179, Create one output per request: waiting, running, done, or lost (the browser did not get the answer).
   * n197: running carries the operation's own state while Fabric makes it wait (`progress`). */
  status?: "waiting" | "running" | "done" | "lost";
  /** n197: while running: waiting for capacity (Fabric throttles) or still running in Fabric, in words */
  progress?: { state: "running" | "waiting_capacity" | "pending_fabric"; words?: string; capacity_app?: string };
  /** n197: the operation of this step (a reopened item reads it again) */
  operation_id?: string;
  /** n197: held back until the pipeline's run has succeeded (the report, with Run once ticked) */
  after_run?: "waiting" | "stopped";
  /** n197: why it was held back or stopped, in plain words */
  after_run_words?: string;
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
  /** n180: the one refresh of a semantic model this Create made (planned in the dry run) */
  refresh?: ModelRefresh;
  /** n184: the report's visuals in the dry run this Create followed (createWords.visualCount), set by createEach */
  dry_run_visuals?: number;
  /** n185: the pipeline's Run once and Schedule */
  jobs?: JobsCard;
  /** n185: the data agent's layer and publishing */
  agent?: AgentCard;
}

/** n180 (workload_api.refresh_new_model): planned in the dry run; refreshed, refreshing (still running when the wait
 * ended), failed with Fabric's reason, or not_run (the permission it needs, with the Entra steps). */
export interface ModelRefresh {
  status: "planned" | "refreshed" | "refreshing" | "failed" | "not_run";
  reason?: string;
  note?: string;
  scope?: string;
  entra_steps?: string[];
  hint?: string;
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

/** n197: no request to the engine is held open longer than this. The founder's live Create of 10 November 2026 met the
 * old 230 s wait (set under Azure Container Apps' 240 s ingress timeout) on the report and "Failed to fetch" on a phone:
 * now each request answers at once (202 and an operation id, `Prefer: respond-async`) and the editor reads the
 * operation (POST /workload/v1/operation) until it ends, each read a short request of its own. */
export const REQUEST_WAIT_MS = 30_000;
/** kept for the callers that name it: every request now waits at most REQUEST_WAIT_MS */
export const BUILD_WAIT_MS = REQUEST_WAIT_MS;
/** between two reads of an operation: quick at first, then every few seconds */
export const OPERATION_POLL_MS = [1_000, 2_000, 2_000, 3_000, 5_000];
/** how long the editor reads one operation before it says "still working; reopen the item": a Create step may wait
 * for capacity (about twenty minutes) and for Fabric's long-running operations (twenty more) */
export const OPERATION_MAX_MS = 50 * 60_000;

/** n197: a background operation as POST /workload/v1/operation answers it (fabric_backend/operations.py). */
export interface OperationState {
  operation_id: string;
  id: string;
  route: string;
  status: "running" | "waiting_capacity" | "pending_fabric" | "done" | "lost";
  started?: string;
  updated?: string;
  output?: OutputKind;
  item?: string;
  create?: string;
  http?: number;
  progress?: { words?: string; capacity_app?: string; attempt?: number; wait?: number };
  lost?: string;
  answer?: any;
}

export interface CallOptions {
  /** called once with the operation's id, as soon as the engine has it (to keep it in the item) */
  onStarted?: (operationId: string) => void;
  /** called with each state read while it runs (waiting for capacity, still running in Fabric) */
  onProgress?: (state: OperationState) => void;
  /** read this operation instead of sending the request again (a reopened item resumes its Create) */
  resume?: string;
  maxWaitMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

/** n197: the answer of an operation the engine lost (its replica stopped): like a lost request, the step is tried again. */
export function lostOperation(state: OperationState): EngineError {
  return {
    error: state.lost || "The Krusgraph engine stopped working on this step.",
    kind: "no_answer",
    hint: "It may still have been made in Fabric. Try again: an item this Create sent is adopted when it is there, and only the rest is made.",
  };
}

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

type Route = "review" | "check" | "build" | "schemas" | "pipeline-run" | "operation";

/** n197: send the request in the background (202 and an operation id) and read the operation until it ends; an engine
 * that answers at once (200, an older server, or no store for operations) is taken as it answers. */
async function call<T>(
  workloadClient: WorkloadClientAPI,
  route: Route,
  body: object,
  waitMs = REQUEST_WAIT_MS,
  fetchImpl: Fetch = (u, i) => fetch(u, i),
  opts: CallOptions = {}
): Promise<T> {
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  let first: any;
  if (opts.resume) {
    first = { operation_id: opts.resume, status: "running" };
  } else {
    first = await callOnce<any>(workloadClient, route, body, Math.min(waitMs || REQUEST_WAIT_MS, REQUEST_WAIT_MS), fetchImpl,
      route !== "operation" && route !== "pipeline-run");
    if (!first || first.__status !== 202) {
      if (first) delete first.__status;
      return first as T;
    }
  }
  const id: string = first.operation_id;
  opts.onStarted?.(id);
  const until = Date.now() + (opts.maxWaitMs ?? OPERATION_MAX_MS);
  let n = 0;
  let misses = 0;
  while (Date.now() < until) {
    await sleep(OPERATION_POLL_MS[Math.min(n++, OPERATION_POLL_MS.length - 1)]);
    let state: OperationState;
    try {
      state = await callOnce<OperationState>(workloadClient, "operation", { operation_id: id }, REQUEST_WAIT_MS, fetchImpl, false);
    } catch (e) {
      // a phone asleep, a network change, a busy engine: reading again is always safe; a missing operation is not
      if (e instanceof EngineCallError && e.status === 404) throw e;
      misses++;
      continue;
    }
    misses = 0;
    if (state.status === "done") {
      const http = state.http ?? 200;
      if (http >= 400 || state.answer?.error) throw new EngineCallError(state.answer as EngineError, http);
      return state.answer as T;
    }
    if (state.status === "lost") throw new EngineCallError(lostOperation(state), 0);
    opts.onProgress?.(state);
  }
  throw new EngineCallError({
    error: `The Krusgraph engine is still working on this ${route === "build" ? "step" : "request"}` + (misses ? " (the last reads did not get through)" : "") + ".",
    kind: "no_answer",
    hint: "Nothing is lost: reopen the item later and it shows where it is, or choose Try again.",
  }, 0);
}

async function callOnce<T>(
  workloadClient: WorkloadClientAPI,
  route: Route,
  body: object,
  waitMs: number,
  fetchImpl: Fetch,
  background: boolean
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
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(background ? { Prefer: "respond-async" } : {}) },
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
  if (background) (answer as any).__status = response.status;
  return answer as T;
}

/** n197: the operations of the item's latest Create, each with its state and, once done, its answer (a reopened item
 * shows the same run and goes on with it). */
export function itemOperations(
  workloadClient: WorkloadClientAPI,
  itemId: string,
  fetchImpl?: Fetch
): Promise<{ item: string; create: string | null; operations: OperationState[] }> {
  return call(workloadClient, "operation", { item_id: itemId }, REQUEST_WAIT_MS, fetchImpl);
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
  fetchImpl?: Fetch,
  extra: StepExtra = {},
  opts: CallOptions = {}
): Promise<ManyAnswer> {
  // every chosen output goes along (the pipeline runs the silver and gold notebooks chosen with it); `only` is built
  const outputs = all.map((o) => (o.kind === output.kind ? output : o));
  return call<ManyAnswer>(
    workloadClient,
    "build",
    { ...source, outputs, only: [output.kind], review: reviewFile, dry_run: false, product: null, created,
      skip_built: !extra.after_run, ...extra },
    BUILD_WAIT_MS,
    fetchImpl,
    opts
  );
}

/** n197: what a Create step sends besides its output: the pipeline's schedules, the run's end (agent, report), the item
 * and the Create it belongs to, and outputs.json's pending items (adopted when Fabric finished them after a wait). */
export interface StepExtra {
  schedule_ids?: string[];
  after_run?: { status: string };
  item_id?: string;
  create_id?: string;
  pending?: PendingItem[];
  refresh_only?: boolean;
}

/** n197: an item a Create sent to Fabric, recorded before its answer (outputs.json pending). */
export interface PendingItem {
  output: string;
  type: string;
  name: string;
  at?: string;
}

/** n185: the pipeline run Create started, read once (POST /workload/v1/pipeline-run); the editor asks again until it ends. */
export function pipelineRun(
  workloadClient: WorkloadClientAPI,
  run: { workspace: string; pipeline_id: string; pipeline_name: string; run_id: string; started?: string },
  fetchImpl?: Fetch
): Promise<PipelineRun> {
  return call<PipelineRun>(workloadClient, "pipeline-run", run, REQUEST_WAIT_MS, fetchImpl);
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
