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
  note: string;
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
  skipped_relationships?: unknown[];
  left_out_by_review: LeftOut[];
  note?: string;
  created?: { type: string; id: string; name: string; workspace: string }[];
  endpoint?: string;
  portal_steps?: string[];
  result?: { status: string; id?: string };
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

async function call<T>(workloadClient: WorkloadClientAPI, route: "review" | "build", body: object): Promise<T> {
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
  previous?: ReviewFile
): Promise<ReviewAnswer> {
  return call<ReviewAnswer>(workloadClient, "review", { ...source, previous: previous ?? null });
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
