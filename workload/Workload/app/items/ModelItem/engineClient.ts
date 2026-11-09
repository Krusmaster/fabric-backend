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
import { ReviewFile } from "./ModelItemDefinition";
import { MapData } from "./cardMap";
import { CheckTotals } from "./modelWords";

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

/** The scope to ask the Fabric host for: the build's KRUSGRAPH_ENGINE_SCOPE, else the hosting server's meta tag. */
export function engineScope(built: string | undefined, doc?: { querySelector(selector: string): Element | null }): string {
  if (built) {
    return built;
  }
  const meta = doc?.querySelector('meta[name="krusgraph-engine-scope"]');
  return (meta?.getAttribute("content") || "").trim();
}

async function call<T>(workloadClient: WorkloadClientAPI, route: "review" | "check" | "build", body: object): Promise<T> {
  const scope = engineScope(process.env.KRUSGRAPH_ENGINE_SCOPE, typeof document === "undefined" ? undefined : document);
  if (!scope) {
    throw new EngineCallError({ error: "No engine scope: set KRUSGRAPH_ENGINE_SCOPE in the workload's .env file, or KRUSGRAPH_WORKLOAD_APP_ID_URI on the hosting server", kind: "server_config" }, 0);
  }
  const { token } = await workloadClient.auth.acquireFrontendAccessToken({ scopes: [scope] });
  const base = (process.env.KRUSGRAPH_ENGINE_URL || "").replace(/\/$/, "");
  const response = await fetch(`${base}/workload/v1/${route}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
