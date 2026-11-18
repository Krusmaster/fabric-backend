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

/** The write button's state and why: only after a dry run, with something to write, in an allowed workspace. */
export function canWrite(a: CatalogAnswer | undefined, checked: boolean): { ok: boolean; why: string } {
  if (!a) return { ok: false, why: "Prepare first: you see what would be written before anything is." };
  if (!a.confirm || writeCount(a) === 0) return { ok: false, why: "Nothing for you to write: the rest is in the handover files." };
  if (a.writable === false)
    return { ok: false, why: "Writing is switched on only in the workspaces the Krusgraph operator lists (its demo workspace while this is tested). Use the handover files." };
  if (!checked) return { ok: false, why: "Tick that you checked the changes above." };
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
  return `${proven} of ${c.quality_rules.length} quality rules proven by the row check`;
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
