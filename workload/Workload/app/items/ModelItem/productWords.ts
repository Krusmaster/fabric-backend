/**
 * n198: the Data product page (docs/LIFECYCLE-DESIGN.md section 6, its first slice; docs/FABRIC-IQ-AT-SCALE.md
 * section 8). After Create, and on reopening an item with outputs, the item shows what Krusgraph built as one data
 * product: its name, its owner (picked from the workspace's people, kept in outputs.json), every item with its type and
 * state, Open in Fabric, the pipeline's last run, the plan id and, when n200's health route answers, its health.
 * From here: Check against the rows again (what is out of date, with the Update path), Retire (turn off what Krusgraph
 * scheduled, then Delete from Fabric with a dry run and the data product's name typed) and Clean up leftovers.
 *
 * Pure functions, no React, so productWords.test.ts runs them. The engine's side is fabric_backend/product_life.py.
 */
import { BuildCard } from "./engineClient";
import { CreatedItem, OutputsDefinition, ProductDefinition, RemovedItem } from "./ModelItemDefinition";
import { itemTypeLabel, readLastCreate } from "./createWords";

export type ItemState = "built" | "pending" | "failed" | "changed_outside" | "missing" | "removed";

/** The state in words, a mark that is not a colour, and the tone (colour is never the only signal). */
export const STATE: Record<ItemState, { label: string; mark: string; tone: "ok" | "wait" | "bad" | "warn" | "off" }> = {
  built: { label: "Built", mark: "✓", tone: "ok" },
  pending: { label: "Pending", mark: "…", tone: "wait" },
  failed: { label: "Failed", mark: "✕", tone: "bad" },
  changed_outside: { label: "Changed outside Krusgraph", mark: "!", tone: "warn" },
  missing: { label: "Missing", mark: "?", tone: "bad" },
  removed: { label: "Removed", mark: "–", tone: "off" },
};

export const NOT_CHECKED = "Health: not checked yet";
export const NO_OWNER = "Nobody is the owner yet. Pick a person or a group with a role in this workspace.";
export const KEEPS_DATA =
  "Krusgraph never deletes a lakehouse, a warehouse, a table or a view's data, and never an item this data product did not build.";

/** One item of the data product as the page shows it. */
export interface ProductRow {
  key: string;
  id?: string;
  type: string;
  typeLabel: string;
  name: string;
  workspace?: string;
  output?: string;
  state: ItemState;
  /** why it has this state, in plain words (empty for built) */
  why: string;
  /** removed: when and by whom */
  removed?: { at: string; by: string };
  /** an id Fabric can open */
  openable: boolean;
}

/** The engine's status answer (POST /workload/v1/product, action status). */
export interface StatusAnswer {
  items: { id: string | null; type: string; name: string; workspace?: string | null; output?: string | null; state: ItemState; why: string }[];
  you?: string;
  people?: Person[] | null;
}

export interface Person {
  name: string;
  type: "User" | "Group";
  role?: string;
  upn?: string;
}

/** The rows of the page: outputs.json alone (status undefined: Fabric not read yet), or with the engine's states. */
export function rowsOf(outputs: OutputsDefinition, status?: StatusAnswer): ProductRow[] {
  const rows: ProductRow[] = [];
  const removed = outputs.removed ?? [];
  const gone = new Set(removed.map((r) => r.id));
  const live = outputs.created.filter((c) => c.id && !gone.has(c.id));
  const said = new Map((status?.items ?? []).filter((s) => s.id).map((s) => [s.id as string, s]));
  for (const c of live) {
    const s = said.get(c.id);
    const state: ItemState = s?.state && s.state in STATE ? s.state : "built";
    rows.push({
      key: c.id, id: c.id, type: c.type, typeLabel: itemTypeLabel(c.type, c.output), name: c.name, workspace: c.workspace, output: c.output,
      state, why: s ? s.why : status ? "" : "As this item recorded it; Fabric has not been read yet.", openable: state !== "missing",
    });
  }
  const made = new Set(live.map((c) => `${c.type}:${c.name.toLowerCase()}`));
  for (const p of outputs.pending ?? []) {
    if (made.has(`${p.type}:${p.name.toLowerCase()}`)) continue;
    rows.push({ key: `pending:${p.type}:${p.name}`, type: p.type, typeLabel: itemTypeLabel(p.type, p.output), name: p.name, output: p.output,
      state: "pending", why: "A Create sent it and has not seen it finish. Reopening the item or Try again adopts it once Fabric has made it.",
      openable: false });
    made.add(`${p.type}:${p.name.toLowerCase()}`);
  }
  const last = readLastCreate(outputs.last_create);
  const builtOutputs = new Set(live.map((c) => c.output).filter(Boolean));
  for (const o of last?.outputs ?? []) {
    if ((o.state !== "failed" && o.state !== "lost") || builtOutputs.has(o.output)) continue;
    if (rows.some((r) => r.output === o.output && r.state === "pending")) continue;
    rows.push({ key: `failed:${o.output}`, type: "", typeLabel: o.label, name: o.name, output: o.output, state: "failed",
      why: o.reason ? o.reason : o.state === "lost" ? "The last Create got no answer for it." : "The last Create did not build it.", openable: false });
  }
  for (const r of removed) {
    rows.push({ key: `removed:${r.id}`, id: r.id, type: r.type, typeLabel: itemTypeLabel(r.type, r.output), name: r.name, workspace: r.workspace,
      output: r.output, state: "removed", why: `Deleted from Fabric on ${dayOf(r.removed_at)}${r.by ? ` by ${r.by}` : ""}.`,
      removed: { at: r.removed_at, by: r.by }, openable: false });
  }
  return rows;
}

export function dayOf(iso: string | undefined): string {
  if (!iso) return "an unknown day";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

/** "3 built, 1 missing, 1 changed outside Krusgraph": the counts in words, in a fixed order. */
export function summary(rows: ProductRow[]): string {
  const order: ItemState[] = ["built", "pending", "failed", "changed_outside", "missing", "removed"];
  const parts = order.map((s) => [s, rows.filter((r) => r.state === s).length] as const).filter(([, n]) => n > 0)
    .map(([s, n]) => `${n} ${STATE[s].label.charAt(0).toLowerCase()}${STATE[s].label.slice(1)}`);
  return parts.length ? parts.join(", ") : "No items yet: Create builds them.";
}

/** The pipeline's last run, from outputs.json's pipeline_jobs (n185/n197 job polling). */
export function lastRunWords(outputs: OutputsDefinition): string {
  const runs = outputs.pipeline_jobs?.runs ?? [];
  const r = runs[runs.length - 1];
  if (!r) return "Last pipeline run: none recorded. Run once on the pipeline, or its schedule, starts one.";
  const st = r.status === "Succeeded" ? "succeeded" : r.status === "Failed" ? "failed" : r.status === "Running" ? "still running when last read"
    : r.status === "NotStarted" ? "did not start" : `status ${r.status}`;
  return `Last pipeline run: ${st}, ${r.pipeline}, started ${dayOf(r.started ?? r.at)}.`;
}

export function ownerWords(p: ProductDefinition | undefined): string {
  if (!p?.owner) return NO_OWNER;
  return `Owner: ${p.owner}` + (p.owner_set ? ` (chosen on ${dayOf(p.owner_set.at)}${p.owner_set.by ? ` by ${p.owner_set.by}` : ""})` : "") + ".";
}

/** n200's health answer, when that route exists; anything else is "not checked yet". */
export function healthWords(h: { word?: string; status?: string; words?: string; checked_at?: string } | undefined | null): string {
  const word = h?.word ?? h?.status;
  if (!h || !word) return NOT_CHECKED;
  return `Health: ${word}` + (h.words ? `. ${h.words}` : "") + (h.checked_at ? ` (checked ${dayOf(h.checked_at)})` : "");
}

// ------------------------------------------------------------------ owner, removals, adoptions into outputs.json -------

export function withOwner(outputs: OutputsDefinition, owner: string, by: string, at: string, fallbackName: string): OutputsDefinition {
  const p: ProductDefinition = outputs.product ?? { name: fallbackName, owner: null, plan: {}, items: [], domains: [] };
  const name = owner.trim().slice(0, 200);
  return { ...outputs, product: { ...p, owner: name || null, owner_note: name ? undefined : p.owner_note, owner_set: name ? { at, by } : undefined } };
}

/** The removals the engine reported, recorded: out of created and the product's items, into removed (when, by whom). */
export function withRemoved(outputs: OutputsDefinition, removed: RemovedItem[]): OutputsDefinition {
  if (!removed.length) return outputs;
  const ids = new Set(removed.map((r) => r.id));
  const was = outputs.removed ?? [];
  return {
    ...outputs,
    created: outputs.created.filter((c) => !ids.has(c.id)),
    removed: [...was.filter((r) => !ids.has(r.id)), ...removed],
    ...(outputs.product ? { product: { ...outputs.product, items: outputs.product.items.filter((c) => !ids.has(c.id)) } } : {}),
  };
}

/** Adopted leftovers into created (and the product's items), each with when and by whom. */
export function withAdopted(outputs: OutputsDefinition, adopted: CreatedItem[]): OutputsDefinition {
  const have = new Set(outputs.created.map((c) => c.id));
  const add = adopted.filter((a) => a.id && !have.has(a.id));
  if (!add.length) return outputs;
  return {
    ...outputs,
    created: [...outputs.created, ...add],
    ...(outputs.product ? { product: { ...outputs.product, items: [...outputs.product.items, ...add] } } : {}),
  };
}

// ------------------------------------------------------------------ Update: what is out of date --------------------

export interface OutOfDate {
  output: string;
  label: string;
  name: string;
  /** up_to_date: built from this plan; differs: built from another plan; missing: Create would build it; stopped: the
   * dry run refused it */
  kind: "up_to_date" | "differs" | "missing" | "stopped";
  words: string;
  /** what the person can do: Update (a dry run, then confirm_update) or a new name (an App, a report) */
  actions: ("update" | "confirm_update" | "new_name")[];
  card: BuildCard;
}

/** The dry run's cards after Check against the rows again, as the page lists them. */
export function outOfDate(cards: BuildCard[]): OutOfDate[] {
  return cards.map((c): OutOfDate => {
    const base = { output: c.output, label: c.label, name: c.name, card: c };
    if (c.refusal || c.answer?.error) {
      const r = c.refusal ?? c.answer;
      return { ...base, kind: "stopped", words: [r?.error, r?.hint].filter(Boolean).join(" "), actions: [] };
    }
    if (c.confirm_update) {
      return { ...base, kind: "differs", words: `${c.built_from?.words ?? "built from another plan"}. The Update's dry run is above; nothing was written yet.`,
        actions: ["confirm_update"] };
    }
    if (c.built_from && c.choices?.length) {
      const inPlace = c.choices.includes("update");
      return { ...base, kind: "differs", words: `Out of date: ${c.built_from.words}.` + (inPlace ? "" :
        c.output === "rayfin_app" ? " An App is never updated in place: choose a new name to build a new one." :
          " It is never updated in place: choose a new name."), actions: inPlace ? ["update", "new_name"] : ["new_name"] };
    }
    if (c.already_built) return { ...base, kind: "up_to_date", words: "Up to date: built from this plan.", actions: [] };
    return { ...base, kind: "missing", words: "Not in the workspace: Create builds it again.", actions: [] };
  });
}

export function outOfDateSummary(list: OutOfDate[]): string {
  const n = (k: OutOfDate["kind"]) => list.filter((x) => x.kind === k).length;
  if (!list.length) return "";
  const parts = [`${n("up_to_date")} up to date`, `${n("differs")} out of date`];
  if (n("missing")) parts.push(`${n("missing")} not in the workspace`);
  if (n("stopped")) parts.push(`${n("stopped")} could not be checked`);
  return parts.join(", ") + ".";
}

// ------------------------------------------------------------------ Retire and leftovers ----------------------------

/** The typed confirmation: exactly the data product's name (spaces around it do not count). */
export function typedNameOk(typed: string, productName: string): boolean {
  return typed.trim() === productName.trim() && productName.trim() !== "";
}

export interface RetireAnswer {
  scope: "soft" | "delete";
  leftovers: boolean;
  dry_run: boolean;
  product: string;
  words: string;
  keeps: string;
  confirm?: string | null;
  items?: { id: string; type: string; name: string; workspace: string; output?: string | null }[];
  steps?: { id: string; name: string; type: string; action: "remove_schedule" | "manual"; words: string; result?: string; why?: string }[];
  refused: { id: string; name?: string; type?: string; why: string; gone?: boolean }[];
  results?: { id: string; name: string; type: string; result: "deleted" | "already_gone" | "failed"; why?: string }[];
  removed?: RemovedItem[];
}

export function resultWords(r: { result: string; why?: string }): string {
  if (r.result === "deleted") return "Deleted from Fabric";
  if (r.result === "already_gone") return "Already gone from Fabric";
  if (r.result === "done") return "Done";
  if (r.result === "manual") return "A step for you in Fabric";
  return `Not deleted: ${r.why ?? "Fabric refused"}`;
}

export interface Leftover {
  id: string;
  type: string;
  name: string;
  workspace: string;
  plan_id: string;
  same_plan: boolean;
  adopt_ok: boolean;
  adopt_why: string;
  delete_ok: boolean;
  why: string;
}

export interface LeftoversAnswer {
  leftovers: Leftover[];
  unread_models: string[];
}

export function leftoverWords(x: Leftover): string {
  const plan = x.same_plan ? "built from this data product's plan" : `built from another plan (${x.plan_id})`;
  return `${itemTypeLabel(x.type)} ${x.name}: carries Krusgraph's plan marker, ${plan}, and no Krusgraph Model lists it.`;
}
