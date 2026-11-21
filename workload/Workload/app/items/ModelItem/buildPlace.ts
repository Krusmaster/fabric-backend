/**
 * n221: where a Krusgraph Model builds. The founder's live test of 11 November 2026: a new Model item in a new workspace
 * (demo_Sandvik) read the lakehouse demo_lh of the workspace demo, and the dry run linked to demo_lh_silver ...
 * demo_lh_api in demo, "already built from this plan": the outputs went to the source's workspace. Now the Model builds in
 * its own workspace by default, so a new workspace gets its own data product, and the person can choose the source's
 * workspace instead ("Build in"). The engine reads the source across workspaces through OneLake and writes silver and
 * gold to a lakehouse of the build's workspace: one the person chooses, one Krusgraph makes when ticked (Create makes it,
 * with Lakehouse schemas, after the dry run named it), or the first of that workspace (fabric_backend/mirroring.py).
 * "Already built from this plan" is per build workspace: the engine looks for the items there.
 *
 * Pure functions, no React and no Fabric client (buildPlace.test.ts).
 */
import type { CreatedItem, SourceDefinition } from "./ModelItemDefinition";

export type BuildIn = "item" | "source";

export const BUILD_IN_WORDS: Record<BuildIn, string> = {
  item: "This item's workspace (default)",
  source: "The source's workspace",
};

/** The choice as saved (absent: this item's workspace, the default). */
export function buildIn(source?: Pick<SourceDefinition, "buildIn">): BuildIn {
  return source?.buildIn === "source" ? "source" : "item";
}

/** The workspace the outputs go to: the Model item's own unless the person chose the source's. Without the item's
 * workspace (not read yet) the source's, as before n221. */
export function buildWorkspace(source: Pick<SourceDefinition, "workspaceId" | "buildIn">, itemWorkspaceId?: string): string {
  return buildIn(source) === "item" && itemWorkspaceId ? itemWorkspaceId : source.workspaceId;
}

/** True when the build's workspace is not the source's: the source is read across workspaces. */
export function crossWorkspace(source: Pick<SourceDefinition, "workspaceId" | "buildIn">, itemWorkspaceId?: string): boolean {
  return buildWorkspace(source, itemWorkspaceId).toLowerCase() !== source.workspaceId.toLowerCase();
}

/** The lakehouse Krusgraph offers to make. ED2 (Gustav, 21 November 2026: "shop_lh_krusgraph_test" was taken): named
 * after the data product or the Model item (`named`) with _lh, the same rule as the engine's
 * workload_api.default_lakehouse_name; without one, the source's name with _krusgraph. Letters, digits, underscores.
 * The engine checks the name against the workspace before Create and moves it to the next free one, said once. */
export function defaultLakehouseName(sourceName: string, named?: string): string {
  const slug = (x: string) => x.replace(/[^A-Za-z0-9_]/g, "_").replace(/_+/g, "_").replace(/^[^A-Za-z]+/, "").replace(/_+$/, "").slice(0, 100);
  const own = named ? slug(named) : "";
  if (own) return own.toLowerCase().endsWith("_lh") ? own : `${own}_lh`;
  return `${slug(sourceName) || "lakehouse"}_krusgraph`;
}

export function validLakehouseName(name: string): boolean {
  return /^[A-Za-z][A-Za-z0-9_]{0,122}$/.test(name.trim());
}

export interface TargetRequest {
  lakehouse: string | null;
  workspace: string;
  where: BuildIn;
  create_lakehouse?: string;
}

/** What every engine request carries as `target`. A chosen lakehouse counts only in the workspace it was chosen in (a
 * read-only source's target from n201 has no workspace: the source's). Create a lakehouse counts only when no lakehouse
 * is chosen there. */
export function targetRequest(source: SourceDefinition, itemWorkspaceId?: string, productName?: string): TargetRequest {
  const ws = buildWorkspace(source, itemWorkspaceId);
  const t = source.target;
  const chosen = t && (t.workspaceId ?? source.workspaceId).toLowerCase() === ws.toLowerCase() ? t.itemId : null;
  // ED1: in another workspace than the source's, with no lakehouse chosen, Create makes (or reuses) one named after the
  // source by default: a visible default under Change, no checkbox to tick
  const cross = ws.toLowerCase() !== source.workspaceId.toLowerCase();
  const named = source.createLakehouse !== undefined ? source.createLakehouse : cross ? defaultLakehouseName(source.displayName, productName) : undefined;
  const make = !chosen && named && validLakehouseName(named) ? named.trim() : undefined;
  return { lakehouse: chosen, workspace: ws, where: buildIn(source), ...(make ? { create_lakehouse: make } : {}) };
}

/** A lakehouse picked under "Lakehouse for silver and gold" must be a lakehouse of the build's workspace. */
export function lakehouseProblem(buildWs: string, picked: { workspaceId: string; type?: string }): string | undefined {
  if (picked.type && picked.type !== "Lakehouse") return "Choose a lakehouse for the silver tables and the gold views.";
  if (picked.workspaceId.toLowerCase() !== buildWs.toLowerCase())
    return "Choose a lakehouse in the workspace the outputs are built in (Build in).";
  return undefined;
}

/** The line under the choice, before any dry run. */
export function buildInLine(source: SourceDefinition, itemWorkspaceId?: string): string {
  const cross = crossWorkspace(source, itemWorkspaceId);
  if (buildIn(source) === "source")
    return `The outputs are built in the workspace of ${source.displayName}, beside it.`;
  if (!cross) return `The outputs are built in this item's workspace, which is also ${source.displayName}'s.`;
  return (
    `The outputs are built in this item's workspace, so it gets its own data product. ${source.displayName} stays in its own ` +
    "workspace and is only read: the silver notebook reads its tables through OneLake, and the silver tables and gold views " +
    "are written to a lakehouse of this workspace."
  );
}

/** The lakehouse line when the build is in another workspace than the source's. */
export function lakehouseLine(source: SourceDefinition, itemWorkspaceId?: string, named?: string): string {
  const t = targetRequest(source, itemWorkspaceId, named);
  if (t.lakehouse) return `Silver and gold go to the lakehouse ${source.target?.displayName ?? t.lakehouse}.`;
  if (t.create_lakehouse)
    return `Create makes the lakehouse ${t.create_lakehouse} here first (with Lakehouse schemas), unless one of that name is there; the dry run makes nothing.`;
  return "Silver and gold go to the first lakehouse of this workspace by name.";
}

/** ED1 (Gustav, 21 November 2026): the one line the Choose step shows for where the build goes, a visible default that
 * Change opens. It never contradicts what the dry run does: it reads the same targetRequest. */
export function placeLine(source: SourceDefinition, itemWorkspaceId?: string, named?: string): string {
  const t = targetRequest(source, itemWorkspaceId, named);
  const here = buildIn(source) === "source" ? "the source's workspace" : "this workspace";
  if (t.lakehouse) return `Silver and gold go to ${source.target?.displayName ?? t.lakehouse} in ${here}.`;
  if (t.create_lakehouse)
    return `Silver and gold go to a lakehouse ${t.create_lakehouse} in ${here}. Create makes it if it is not there yet.`;
  if (source.itemType === "Lakehouse" || /lakehouse/i.test(source.itemType)) return `Silver and gold go to ${source.displayName} in ${here}.`;
  return `Silver and gold go to the first lakehouse of ${here}.`;
}

/** The data product's workspace (n198, n210: Delete only there): where its items were built, else where it builds. */
export function productWorkspace(source: SourceDefinition | undefined, created: CreatedItem[], itemWorkspaceId?: string): string | undefined {
  const last = [...created].reverse().find((c) => c.workspace);
  if (last) return last.workspace;
  return source ? buildWorkspace(source, itemWorkspaceId) : itemWorkspaceId;
}

/** The build answer's lakehouse, as source.json keeps it after a Create (n200: the health table is read there). The
 * dry run's planned lakehouse has no id yet and is not kept. */
export function keptTarget(
  answerTarget: { lakehouse?: string; id?: string; workspace_id?: string } | undefined,
  buildWs: string
): { itemId: string; displayName: string; workspaceId: string } | undefined {
  if (!answerTarget?.id || !/^[0-9a-fA-F-]{36}$/.test(answerTarget.id)) return undefined;
  return { itemId: answerTarget.id, displayName: answerTarget.lakehouse ?? answerTarget.id, workspaceId: answerTarget.workspace_id ?? buildWs };
}
