/**
 * WB14 (issue #108; Gustav's approval of 18 Nov 2026): "Save to lakehouse Files" beside Download and Copy.
 *
 * A generated file (the draw.io map, a notebook, the handover files, the contracts, the App package, EDIT-WITH-AI.md) is
 * written to Files/krusgraph/<item name>/<file> in the lakehouse the Model item already targets, through OneLake's
 * ADLS Gen2-compatible DFS API, as the signed-in user. Sources (Microsoft Learn, read 20 Nov 2026):
 *  - "How do I connect to OneLake?" (fabric/onelake/onelake-access-api, ms.date 05/18/2026): the URI
 *    https://onelake.dfs.fabric.microsoft.com/<workspaceGUID>/<itemGUID>/<path>; "OneLake only supports tokens in the
 *    Storage audience"; Create file is PUT …?resource=file with the user's bearer token.
 *  - "Authentication JavaScript API reference" (fabric/extensibility-toolkit/authentication-javascript-api, ms.date
 *    12/15/2025): workloadClient.auth.acquireFrontendAccessToken({ scopes: ['https://storage.azure.com/user_impersonation'] }).
 *  - "Authentication guidelines" (…/authentication-guidelines, ms.date 12/15/2025): the scope is added on the workload
 *    app's API permissions tab. The workload manifest has no scope element ("Workload Manifest", …/manifest-workload).
 *  - "Path - Create" (rest/api/storageservices/datalakestoragegen2/path/create, ms.date 10/23/2026): the destination is
 *    overwritten by default; "To fail if the destination already exists, use a conditional request with
 *    If-None-Match: "*"" (409 PathAlreadyExists). The bytes go in with Path - Update action=append, then action=flush.
 *
 * Off unless the hosting server says so (KRUSGRAPH_ONELAKE_SAVE, fabric_backend/workload_host.py, the meta tag
 * krusgraph-onelake-save): no manifest change. Never overwrites without Replace. Logs the request id OneLake answers
 * (x-ms-request-id) and the status only: never the file or the token. docs/ONELAKE-SAVE-SETUP.md.
 */
import type { OfferedFile } from "./fileOffer";

export const STORAGE_SCOPE = "https://storage.azure.com/user_impersonation";
export const ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com";
export const FLAG_META = "krusgraph-onelake-save";
export const DFS_VERSION = "2023-08-03";
export const SAVE_TIMEOUT_MS = 30_000;

export const NO_ACCESS = "Your admin has not granted storage access yet; use Download instead.";
export const NO_ACCESS_ROLE = "If access was granted, your role in this workspace may not allow writing to the lakehouse.";
export const TIMED_OUT = "OneLake did not answer in time. The file may not be complete there; nothing was replaced without asking. Use Download instead, or try again.";

/** The lakehouse the item targets and the item's name: where Save writes. */
export interface LakehouseTarget {
  workspaceId: string;
  lakehouseId: string;
  lakehouseName: string;
  itemName: string;
}

export type SaveOutcome =
  | { kind: "saved"; status: number; activityId?: string }
  | { kind: "exists"; status: number; activityId?: string }
  | { kind: "no_access"; status?: number; activityId?: string }
  | { kind: "timeout" }
  | { kind: "failed"; status?: number; activityId?: string };

export type Fetch = (url: string, init: RequestInit) => Promise<Response>;

export interface SaveIO {
  /** a token in the Storage audience, asked of the Fabric host (STORAGE_SCOPE) */
  token: () => Promise<string>;
  fetch?: Fetch;
  timeoutMs?: number;
  log?: (fields: { status: number | string; activity_id?: string }) => void;
}

/** The switch: the hosting server's meta tag krusgraph-onelake-save="on". Off when absent. */
export function saveEnabled(doc?: { querySelector(selector: string): Element | null }): boolean {
  const v = (doc?.querySelector(`meta[name="${FLAG_META}"]`)?.getAttribute("content") || "").trim().toLowerCase();
  return v === "on";
}

/** One path segment from a name: no slashes, no control characters, no leading or trailing dots and spaces. */
export function safeSegment(name: string, fallback = "model"): string {
  // eslint-disable-next-line no-control-regex
  const s = (name || "").replace(/[\u0000-\u001f\u007f/\\:*?"<>|]+/g, "_").replace(/^[\s.]+|[\s.]+$/g, "").slice(0, 120);
  return s || fallback;
}

/** Files/krusgraph/<item>/<file>, as the person sees it. */
export function filesPath(target: LakehouseTarget, filename: string): string {
  return `Files/krusgraph/${safeSegment(target.itemName)}/${safeSegment(filename, "file")}`;
}

/** The full path shown before saving: the lakehouse, then the path inside it. */
export function shownPath(target: LakehouseTarget, filename: string): string {
  return `${target.lakehouseName} › ${filesPath(target, filename)}`;
}

/** The DFS URL, by GUIDs (names can change and may hold spaces; GUIDs do not). */
export function onelakeUrl(target: LakehouseTarget, filename: string): string {
  const enc = (s: string) => encodeURIComponent(s);
  return `${ONELAKE_DFS}/${enc(target.workspaceId)}/${enc(target.lakehouseId)}/Files/krusgraph/` +
    `${enc(safeSegment(target.itemName))}/${enc(safeSegment(filename, "file"))}`;
}

export function fileBytes(file: OfferedFile): Uint8Array {
  if (file.base64 !== undefined) {
    const bin = typeof atob === "function" ? atob(file.base64) : Buffer.from(file.base64, "base64").toString("binary");
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  return new TextEncoder().encode(file.text ?? "");
}

export function sizeWords(n: number): string {
  return n < 1024 ? `${n} bytes` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** The dry run's words: what Save would do, before anything is written. */
export function dryRunWords(target: LakehouseTarget, file: OfferedFile): string {
  return `Dry run: Save would write ${safeSegment(file.filename, "file")} (${sizeWords(fileBytes(file).length)}) to ` +
    `${shownPath(target, file.filename)}, as you. Nothing is written until you choose Save, and a file already there is ` +
    "never replaced without asking.";
}

class TimedOut extends Error {}

async function send(io: SaveIO, url: string, init: RequestInit): Promise<Response> {
  const f = io.fetch ?? ((u: string, i: RequestInit) => fetch(u, i));
  const ctl = typeof AbortController === "function" ? new AbortController() : undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const limit = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { ctl?.abort(); reject(new TimedOut()); }, io.timeoutMs ?? SAVE_TIMEOUT_MS);
  });
  try {
    return await Promise.race([f(url, { ...init, signal: ctl?.signal }), limit]);
  } catch (e) {
    if (e instanceof TimedOut || (e as { name?: string })?.name === "AbortError") throw new TimedOut();
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function defaultLog(fields: { status: number | string; activity_id?: string }): void {
  // the status and OneLake's request id only: never the file, the path's contents or the token
  console.info("krusgraph.onelake_save", fields);
}

/**
 * Write one file. Without `replace` the create is conditional (If-None-Match: "*"), so a file already there answers
 * "exists" and is left as it is; with `replace` (the person chose Replace) the create overwrites it.
 */
export async function saveToOneLake(io: SaveIO, target: LakehouseTarget, file: OfferedFile, opts: { replace?: boolean } = {}): Promise<SaveOutcome> {
  const log = io.log ?? defaultLog;
  let token: string;
  try {
    token = await io.token();
    if (!token) throw new Error("no token");
  } catch {
    log({ status: "no_token" });
    return { kind: "no_access" };
  }
  const url = onelakeUrl(target, file.filename);
  const auth = { Authorization: `Bearer ${token}`, "x-ms-version": DFS_VERSION };
  const bytes = fileBytes(file);
  const idOf = (r: Response) => r.headers?.get?.("x-ms-request-id") ?? undefined;
  try {
    const created = await send(io, `${url}?resource=file`, {
      method: "PUT",
      headers: opts.replace ? auth : { ...auth, "If-None-Match": "*" },
    });
    const activityId = idOf(created);
    log({ status: created.status, activity_id: activityId });
    if (created.status === 409 || created.status === 412) return { kind: "exists", status: created.status, activityId };
    if (created.status === 401 || created.status === 403) return { kind: "no_access", status: created.status, activityId };
    if (created.status !== 201 && created.status !== 200) return { kind: "failed", status: created.status, activityId };
    if (bytes.length > 0) {
      const appended = await send(io, `${url}?action=append&position=0`, {
        method: "PATCH", headers: { ...auth, "Content-Type": "application/octet-stream" }, body: bytes as unknown as BodyInit,
      });
      log({ status: appended.status, activity_id: idOf(appended) });
      if (!appended.ok) return { kind: appended.status === 403 ? "no_access" : "failed", status: appended.status, activityId: idOf(appended) };
      const flushed = await send(io, `${url}?action=flush&position=${bytes.length}`, { method: "PATCH", headers: auth });
      log({ status: flushed.status, activity_id: idOf(flushed) });
      if (!flushed.ok) return { kind: flushed.status === 403 ? "no_access" : "failed", status: flushed.status, activityId: idOf(flushed) };
      return { kind: "saved", status: flushed.status, activityId: idOf(flushed) ?? activityId };
    }
    return { kind: "saved", status: created.status, activityId };
  } catch (e) {
    if (e instanceof TimedOut) {
      log({ status: "timeout" });
      return { kind: "timeout" };
    }
    log({ status: "network" });
    return { kind: "failed" };
  }
}
