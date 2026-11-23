/**
 * BL58: the row-level security roles the semantic model's dry run proposes (BL46: create_semantic_model's
 * role_candidates, the model card's `roles` from workload_api.role_card), as tick boxes on the model's card. Off by
 * default: a role is sent only when the person ticks it, as `roles` on the semantic_model output (by the column it
 * filters on), the way a key or a link is accepted. Without a tick the request is exactly as before. Names only: the
 * role, its column, its rule and the tables it filters; never a row value. Pure functions, no React (roleWords.test.ts).
 */
import type { BuildCard } from "./engineClient";
import type { OutputChoice } from "./ModelItemDefinition";

/** One proposed role, as workload_api.role_card gives it. */
export interface RoleCandidate {
  role: string;
  column: string;
  rule: string;
  /** the tables the role filters directly (they carry the column) */
  filters: string[];
  why?: string;
  /** every table it filters is in this model */
  fits: boolean;
  /** this answer's model has the role (it was sent in roles) */
  added: boolean;
  /** why it does not fit, in plain words */
  why_not?: string;
}

export interface RolesCard {
  proposed: RoleCandidate[];
  how?: string;
  map_table?: string;
  written?: boolean;
}

/** The same shape workload_api._roles_request accepts: a column name, as a rule proposes it. */
const COLUMN = /^\$?[A-Za-z][A-Za-z0-9_]{0,63}$/;
const MAX = 20;

export const ROLES_TITLE = "Row-level security roles (proposed, off by default)";
export const ROLES_UNCHANGED = "Nothing is added unless you tick it. A tick is saved in this item and sent with Create.";
export const ROLES_AGAIN = "Your ticks are saved in this item; Create adds the ticked roles. Choose Dry run again to see the model with them.";

export function mapTableLine(map?: string): string {
  const t = map || "security_user_map";
  return `A ticked role also adds the table ${t} to the model. You fill it in the lakehouse: one row per user and value they may see. ` +
    "Krusgraph does not create, fill or read it; a user with no row there sees no rows of a filtered table.";
}

/** The roles of a model card, when the dry run proposed any and each has the shape the engine writes. */
export function rolesOf(c: BuildCard | undefined): RolesCard | undefined {
  const r = c?.output === "semantic_model" ? c.roles : undefined;
  if (!r || !Array.isArray(r.proposed) || !r.proposed.length) return undefined;
  const ok = r.proposed.every((x) => x && typeof x.column === "string" && typeof x.role === "string" && Array.isArray(x.filters));
  return ok ? r : undefined;
}

/** The roles kept on the semantic model's choice: only column names, at most twenty, no repeats; else none. */
export function cleanRoles(x: unknown): string[] | undefined {
  if (!Array.isArray(x) || x.length > MAX || !x.every((r) => typeof r === "string" && COLUMN.test(r))) return undefined;
  const out = [...new Set(x as string[])];
  return out.length ? out : undefined;
}

/** The build's semantic model reads the gold views (workload_api.model_on_gold, DPM1): the pipeline or the gold views are
 * chosen with it. Such a model takes no role yet (BL46): the ticks are not sent, and its dry run, which offers none, clears them. */
export function modelOnGold(choices: OutputChoice[]): boolean {
  const on = (t: string) => choices.some((c) => c.type === t && c.enabled);
  return on("semantic_model") && (on("pipeline") || on("gold_views"));
}

/** The roles ticked on the semantic model's choice (empty: none, the default). */
export function chosenRoles(choices: OutputChoice[]): string[] {
  return cleanRoles(choices.find((c) => c.type === "semantic_model")?.roles) ?? [];
}

/** The choices with these roles on the semantic model; with none the key is left out, as before BL58. */
export function withRoles(choices: OutputChoice[], roles: string[]): OutputChoice[] {
  const kept = cleanRoles(roles);
  return choices.map((c) => {
    if (c.type !== "semantic_model") return c;
    const { roles: _old, ...rest } = c;
    return kept ? { ...rest, roles: kept } : rest;
  });
}

/** Tick or untick one role; a role that does not fit cannot be ticked. In the order the dry run lists them. */
export function toggleRole(card: RolesCard, now: string[], column: string, on: boolean): string[] {
  const fits = new Set(card.proposed.filter((r) => r.fits).map((r) => r.column));
  const next = new Set(now);
  if (on && fits.has(column)) next.add(column);
  else next.delete(column);
  return card.proposed.map((r) => r.column).filter((col) => next.has(col));
}

/** What the boxes show: the saved ticks when the item has them, else what this answer's model has (nothing by default). */
export function tickedRoles(card: RolesCard, saved: string[] | undefined): string[] {
  const offered = new Set(card.proposed.filter((r) => r.fits).map((r) => r.column));
  return (saved ?? card.proposed.filter((r) => r.added).map((r) => r.column)).filter((c) => offered.has(c));
}

/** The ticks differ from what this dry run's model has: Create would add (or leave out) a role the dry run did not show. */
export function ticksDiffer(card: RolesCard, saved: string[] | undefined): boolean {
  if (saved === undefined) return false;
  const shown = card.proposed.filter((r) => r.added).map((r) => r.column).sort();
  return JSON.stringify(tickedRoles(card, saved).slice().sort()) !== JSON.stringify(shown);
}

/** The line under a role's name: its column, its rule, the tables it filters and whether it fits this model. */
export function roleLine(r: RoleCandidate): string {
  const tables = r.filters.length ? r.filters.join(", ") : "no table";
  const fit = r.fits ? "Fits this model's tables." : `Cannot be added: ${r.why_not ?? "its tables are not all in this model"}.`;
  return `Filters on ${r.column} (rule ${r.rule}) in ${tables}. ${fit}`;
}

/** After a dry run: keep only the ticks the model's card offers and that fit. A model refused because of its roles (an
 * answer whose error starts with "roles:") loses them, so the next dry run is the plain one again. No model card (not
 * chosen, or still waiting): the ticks stay. Returns the same array when nothing changes. */
export function keepOffered(choices: OutputChoice[], cards: BuildCard[]): OutputChoice[] {
  const now = chosenRoles(choices);
  if (!now.length) return choices;
  const card = cards.find((c) => c.output === "semantic_model");
  if (!card) return choices;
  const err = card.answer?.error ?? card.refusal?.error;
  if (err) return /^roles:/.test(String(err)) ? withRoles(choices, []) : choices;
  if (!card.answer) return choices;
  const r = rolesOf(card);
  const keep = r ? tickedRoles(r, now) : [];
  return keep.length === now.length ? choices : withRoles(choices, keep);
}
