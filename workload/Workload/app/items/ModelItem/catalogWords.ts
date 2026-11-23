/**
 * CA1: the words and shapes of "Publish to OneLake catalog" (CatalogPanel.tsx), kept apart from the component so they are
 * tested without a browser. The engine (fabric_backend/catalog_publish) decides what is written; these only say it.
 */

export interface CatalogRule {
  id: string;
  kind: "unique_key" | "no_orphans" | "rows_kept_after_join";
  says: string;
  status: "proven" | "proposed" | "not counted";
  sql: string;
}

export interface CatalogCard {
  name: string;
  slug: string;
  tables: string[];
  description: string;
  owner: string;
  domain: { proposed: string; why: string; note: string };
  tags: string[];
  contract: { format: string; status: string; file: string; yaml?: string };
  glossary: { term: string; definition: string }[];
  evidence: { counted: boolean; line: string };
  quality_rules: CatalogRule[];
}

export interface CatalogDiffRow {
  item: string;
  /** WB10: an optional row's item id, sent back in `include` when the person ticks it */
  item_id?: string;
  /** WB11: the item's Fabric type (Lakehouse, Notebook, GraphQLApi, ...), for its icon and its word */
  type?: string | null;
  /** W3: the Krusgraph Model item itself (its own description) */
  model_item?: boolean;
  /** "description", "tags", or for an optional row what would be written ("description and tags") */
  field: string;
  before: string | string[] | null;
  after: string | string[] | null;
  /** WB10: "optional" is an item Krusgraph did not build: nothing is written to it unless the person ticks it */
  action: "write" | "kept" | "optional";
  why?: string;
}

export interface CatalogRequest {
  step: string;
  by: string;
  method: string | null;
  url: string | null;
  why?: string;
}

export interface CatalogAnswer {
  summary: string;
  products: CatalogCard[];
  diff: CatalogDiffRow[];
  confirm: string | null;
  writable?: boolean;
  handover: { requests: CatalogRequest[]; approvals: string[]; files: Record<string, string> };
  note: string;
  results?: { item: string; field: string; ok: boolean; status?: number; hint?: string }[];
  /** W3: the workspace the items were written in (where Open the workspace goes) */
  workspace?: string;
}

export const STEP_TITLE = "Publish to OneLake catalog";
export const STEP_INTRO =
  "Krusgraph fills the catalog for the data products it has checked: a description, tags, an owner, glossary terms and the " +
  "row-check evidence. First you see exactly what would be written as you; nothing is written until you choose Write.";
export const ENDORSE_LINE = "Endorsement (Promoted, Certified) stays a person's decision: Krusgraph never sets or asks for it.";

/** Who, in plain words, for a request's `by` (the engine's apis.WHO, shortened for a phone). */
export const WHO_SHORT: Record<string, string> = {
  you: "You",
  fabric_admin: "Fabric administrator",
  workspace_admin: "Workspace admin",
  reviewer: "A reviewer (a person)",
  purview_domain_creator: "Purview domain creator",
  purview_steward: "Purview data steward",
  purview_dq_steward: "Purview data quality steward",
};

export function who(by: string): string {
  return WHO_SHORT[by] ?? by;
}

export function shown(v: string | string[] | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "(no tags)";
  return v.trim() ? v : "(empty)";
}

/** One line of the diff as a screen reader and a phone read it: item, field, what changes. */
export function diffLine(r: CatalogDiffRow): string {
  const what = r.field;
  if (r.action === "optional") return `${r.item}: not written unless you tick it (${r.why ?? "Krusgraph did not build it"})`;
  return r.action === "write"
    ? `${r.item}: ${what} will change from ${shown(r.before)} to ${shown(r.after)}`
    : `${r.item}: ${what} kept as it is (${r.why ?? "not Krusgraph's to change"})`;
}

export function writeCount(a: CatalogAnswer): number {
  return a.diff.filter((r) => r.action === "write").length;
}

/** ED3: next to the disabled button, in plain words; no checkbox is shown then. */
export const WRITING_OFF = "Writing is off in this workspace while Krusgraph is in test; use the handover files.";

/** The write button's state and why: only after a dry run, with something to write, in an allowed workspace. */
export function canWrite(a: CatalogAnswer | undefined, checked: boolean): { ok: boolean; why: string } {
  if (!a) return { ok: false, why: "Prepare first: you see what would be written before anything is." };
  if (!a.confirm || writeCount(a) === 0) return { ok: false, why: "Nothing for you to write: the rest is in the handover files." };
  if (a.writable === false) return { ok: false, why: WRITING_OFF };
  if (!checked) return { ok: false, why: "Tick that you checked the changes." };
  return { ok: true, why: "" };
}

/** The others who must act, grouped: who, then their steps. Endorsement last. */
export function approvals(a: CatalogAnswer): { who: string; steps: string[] }[] {
  const order = ["fabric_admin", "workspace_admin", "purview_domain_creator", "purview_steward", "purview_dq_steward", "reviewer"];
  const by = new Map<string, string[]>();
  for (const r of a.handover.requests) {
    if (r.by === "you") continue;
    by.set(r.by, [...(by.get(r.by) ?? []), r.step]);
  }
  return [...by.entries()]
    .sort((x, y) => order.indexOf(x[0]) - order.indexOf(y[0]))
    .map(([b, steps]) => ({ who: who(b), steps }));
}

export function ruleCounts(c: CatalogCard): string {
  const proven = c.quality_rules.filter((r) => r.status === "proven").length;
  const notCounted = c.quality_rules.filter((r) => r.status === "not counted").length;
  // ED3: the rules the check did not reach are said once, with why
  return `${proven} of ${c.quality_rules.length} quality rules proven by the row check` +
    (notCounted ? `; ${notCounted} not counted: the check did not reach ${notCounted === 1 ? "it" : "them"} (Check against the rows again counts them)` : "");
}

export function fileMime(path: string): string {
  return path.endsWith(".json") ? "application/json" : path.endsWith(".yaml") ? "application/yaml" : "text/markdown";
}

export function fileHref(content: string, path: string): string {
  return `data:${fileMime(path)};charset=utf-8,${encodeURIComponent(content)}`;
}

export function fileName(path: string): string {
  return path.replace(/\//g, "-");
}

// ------------------------------------------------------------------ WB10: the owner is a person or a group ----------

export interface OwnerPerson {
  name: string;
  type: "User" | "Group";
  role?: string;
  upn?: string;
}

/** How a person is offered in the picker and saved: "Name (upn)" for a user with one, else the name (the Data product
 * page's Owner offers the same). */
export function personValue(p: OwnerPerson): string {
  return p.upn ? `${p.name} (${p.upn})` : p.name;
}

/**
 * WB10 (Gustav's live test, 18 Nov 2026): the field showed 'demo_lh_api9', an API for GraphQL item's name. The owner
 * is a person or group: a value that names an item (an output this Model built) is refused, and where the workspace's
 * people are known, so is anything that is not one of them or the signed-in person (Me). The engine checks the same
 * (catalog_publish/owner.py). Empty: no owner, which is allowed. Returns the sentence that says why not, or "".
 */
export function ownerProblem(value: string, people: OwnerPerson[] | null | undefined, you?: string | null, itemNames: string[] = []): string {
  const v = value.trim().replace(/\s+/g, " ");
  if (!v) return "";
  const low = v.toLowerCase();
  if (you && low === you.trim().toLowerCase()) return "";
  const known = (people ?? []).flatMap((p) => [p.name, p.upn, personValue(p)]).filter(Boolean).map((x) => String(x).toLowerCase());
  if (known.includes(low)) return "";
  if (itemNames.some((n) => n.trim().toLowerCase() === low))
    return `'${v}' is an item in this workspace, not a person or group. Pick a person or group, or choose Me.`;
  if (people && people.length) return `'${v}' is not a person or group with a role in this workspace. Pick one from the list, or choose Me.`;
  return "";
}

/** The optional rows: items Krusgraph did not build, offered unticked. */
export function optionalRows(a: CatalogAnswer | undefined): CatalogDiffRow[] {
  return (a?.diff ?? []).filter((r) => r.action === "optional");
}

// ------------------------------------------------------------------ W3: the write beside Prepare, and after it ------

/** The anchor of the diff list, which "See the N changes" scrolls to. */
export const DIFF_ID = "kg-catalog-diff";

/** "See the 6 changes": the link above the box, so the changes are seen before writing. */
export function seeChangesLabel(a: CatalogAnswer): string {
  const n = writeCount(a);
  return `See the ${n} change${n === 1 ? "" : "s"}`;
}

/** The short line above the box: what would be written as you, counted from the diff ("" when nothing is: the words
 * beside the Write button say so, once). */
export function gateSummary(a: CatalogAnswer): string {
  const rows = a.diff.filter((r) => r.action === "write");
  const desc = rows.filter((r) => r.field === "description").length;
  const tags = rows.filter((r) => r.field === "tags").length;
  if (!rows.length) return "";
  const parts = [desc ? `${desc} description${desc === 1 ? "" : "s"}` : "", tags ? `tags on ${tags} item${tags === 1 ? "" : "s"}` : ""].filter(Boolean);
  return `As you: ${parts.join(" and ")}, ${rows.some((r) => r.model_item) ? "this Krusgraph Model item's own description included, " : ""}` +
    "each shown below with what is there now and what would be there.";
}

/**
 * W3: where to look after a write. Microsoft documents no address that opens the OneLake catalog at an item (the only
 * OneLake catalog address the docs cite is the admin's Govern page, docs/WORKLOAD-PACKAGE-UPDATES.md), so the button
 * opens the workspace's item list, /groups/<workspace>/list (the address the engine's cards use, mcp_apps_build), and
 * says to find it in OneLake catalog.
 */
export function catalogPlace(workspace: string | undefined, portal: string): { url: string; label: string; line: string } | undefined {
  if (!workspace || !/^[0-9a-f-]{36}$/i.test(workspace)) return undefined;
  return { url: `${portal}/groups/${workspace}/list`, label: "Open the workspace",
    line: "Find it in OneLake catalog: in Fabric, choose OneLake catalog and search for the data product's name. No documented "
      + "address opens the catalog at an item, so this button opens the workspace's list." };
}

/** The receipt under the cheer, compactly: what was written, then what was not and why. */
export function receiptLines(results: CatalogAnswer["results"]): string[] {
  const ok = (results ?? []).filter((r) => r.ok).map((r) => `${r.item} (${r.field})`);
  const bad = (results ?? []).filter((r) => !r.ok).map((r) => `${r.item} (${r.field}${r.hint ? `: ${r.hint}` : ""})`);
  return [ok.length ? `Written: ${ok.join(", ")}.` : "", bad.length ? `Not written: ${bad.join("; ")}.` : ""].filter(Boolean);
}

/** The line when not every change went through (no cheer then). */
export function partialLine(results: CatalogAnswer["results"]): string {
  const all = results ?? [];
  const ok = all.filter((r) => r.ok).length;
  return `${ok} of ${all.length} change${all.length === 1 ? "" : "s"} written. The rest are listed below with why; Prepare again shows what is there now.`;
}
