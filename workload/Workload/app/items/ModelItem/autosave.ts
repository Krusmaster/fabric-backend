/**
 * W14: autosave in the Model editor. W13 found that review decisions were lost when the item was closed before Save
 * (the founder's "B: Ja", 17 November 2026). Now:
 *
 *   - every change the editor marks as unsaved is saved to the item's definition after a short pause (AUTOSAVE_DELAY_MS),
 *     and at once when the tab is hidden or closed;
 *   - until Fabric confirms the save, the definition is also kept in this browser (a draft per item), so a reload or a
 *     closed tab recovers it on the next opening and saves it then;
 *   - each save carries a revision in item.json (`saved`: number, time, which editor session). Before an autosave the
 *     editor reads the revision Fabric has; when another session saved in the meantime, the two are merged: a decision
 *     the other session made on an item this session did not touch is kept, and where both changed the same item this
 *     session's decision wins (last write wins) and a warning says how many;
 *   - one line says Saving, Saved or Not saved, with a mark that is not only a colour (SaveIndicator.tsx).
 *
 * Pure functions, no React and no Fabric client (autosave.test.ts). The draft holds what item.json and review.json hold:
 * names, rules and decisions, never a row value, a token or a secret.
 */
import type { ModelDefinition, ReviewFile, ReviewStatus, SavedMark } from "./ModelItemDefinition";

export type { SavedMark };

/** The pause after the last change before the autosave is sent. */
export const AUTOSAVE_DELAY_MS = 1200;
/** Drafts older than this are not recovered (and are removed). */
export const DRAFT_MAX_AGE_MS = 7 * 24 * 3600 * 1000;
/** The browser storage key prefix of a draft; the key is the prefix and the item's id. */
export const DRAFT_PREFIX = "krusgraph-model-draft:";

export type Decision = { review: ReviewStatus; reason: string };
export type Decisions = Record<string, Decision>;

export function revisionOf(def: ModelDefinition | undefined): number {
  const r = def?.item?.saved?.rev;
  return typeof r === "number" && Number.isFinite(r) && r >= 0 ? Math.floor(r) : 0;
}

/** The definition with the next revision stamped in item.json. */
export function stamp(def: ModelDefinition, baseRev: number, session: string, now: Date = new Date()): ModelDefinition {
  const rev = Math.max(baseRev, revisionOf(def)) + 1;
  return { ...def, item: { ...def.item, saved: { rev, at: now.toISOString(), session } } };
}

export function decisionsOf(review: ReviewFile | undefined): Decisions {
  const out: Decisions = {};
  for (const it of review?.items ?? []) out[it.id] = { review: it.review, reason: it.reason ?? "" };
  return out;
}

const same = (a: Decision | undefined, b: Decision | undefined) =>
  (a?.review ?? null) === (b?.review ?? null) && (a?.reason ?? "") === (b?.reason ?? "");

export interface MergeResult {
  review: ReviewFile | undefined;
  /** items whose decision came from the other session (this session had not changed them) */
  kept: string[];
  /** items both sessions changed differently; this session's decision was kept (last write wins) */
  overwritten: string[];
}

/**
 * Three-way merge of the review decisions. `base` is what this session last read or saved, `local` what it shows now,
 * `remote` what Fabric has now. The review itself (its items, rules and checks) is this session's; only decisions move.
 */
export function mergeDecisions(base: Decisions, local: ReviewFile | undefined, remote: ReviewFile | undefined): MergeResult {
  if (!local) return { review: remote, kept: [], overwritten: [] };
  const theirs = decisionsOf(remote);
  const kept: string[] = [];
  const overwritten: string[] = [];
  const items = local.items.map((it) => {
    const b = base[it.id];
    const r = theirs[it.id];
    const l: Decision = { review: it.review, reason: it.reason ?? "" };
    if (!r || same(r, b)) return it;                    // the other session did not change it
    if (same(l, b) || !b) {                             // only they changed it (or this session never saw it)
      if (same(l, r)) return it;
      kept.push(it.id);
      return { ...it, review: r.review, reason: r.reason };
    }
    if (!same(l, r)) overwritten.push(it.id);           // both changed it: this session's decision wins
    return it;
  });
  return { review: { ...local, items }, kept, overwritten };
}

/** Thinker's answers ("keep") from both sides; this session's answer wins where both answered. */
export function mergeAnswers(local?: Record<string, string>, remote?: Record<string, string>): Record<string, string> | undefined {
  if (!local && !remote) return undefined;
  return { ...(remote ?? {}), ...(local ?? {}) };
}

export interface ConflictNote {
  at: string;
  kept: number;
  overwritten: number;
}

/**
 * What to save when Fabric's revision is newer than the one this session started from: this session's definition with
 * the other session's decisions merged in. Everything else (source, outputs, view) is this session's (last write wins).
 */
export function resolve(local: ModelDefinition, base: Decisions, baseRev: number, remote: ModelDefinition | undefined,
  now: Date = new Date()): { def: ModelDefinition; baseRev: number; conflict?: ConflictNote } {
  const remoteRev = revisionOf(remote);
  if (!remote || remoteRev <= baseRev) return { def: local, baseRev };
  const m = mergeDecisions(base, local.review, remote.review);
  const answers = mergeAnswers(local.item.answers, remote.item?.answers);
  const def: ModelDefinition = { ...local, review: m.review, item: { ...local.item, ...(answers ? { answers } : {}) } };
  return { def, baseRev: remoteRev,
    conflict: { at: remote.item?.saved?.at ?? now.toISOString(), kept: m.kept.length, overwritten: m.overwritten.length } };
}

// ------------------------------------------------------------------ the draft in this browser --------------------------

export interface Draft {
  v: 1;
  itemId: string;
  at: string;
  /** the revision the draft was made on, and the decisions of that revision (the merge base) */
  baseRev: number;
  base: Decisions;
  def: ModelDefinition;
}

/** The part of the Web Storage API a draft needs; a stand-in in tests. Any call may throw (storage blocked). */
export interface DraftStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export function browserStore(): DraftStore | undefined {
  try {
    return typeof window !== "undefined" && window.localStorage ? window.localStorage : undefined;
  } catch {
    return undefined;   // storage blocked in the frame: autosave still works, recovery after a reload does not
  }
}

export function writeDraft(store: DraftStore | undefined, itemId: string, def: ModelDefinition, baseRev: number, base: Decisions,
  now: Date = new Date()): boolean {
  if (!store || !itemId) return false;
  const d: Draft = { v: 1, itemId, at: now.toISOString(), baseRev, base, def };
  try {
    store.setItem(DRAFT_PREFIX + itemId, JSON.stringify(d));
    return true;
  } catch {
    return false;
  }
}

export function clearDraft(store: DraftStore | undefined, itemId: string): void {
  try {
    store?.removeItem(DRAFT_PREFIX + itemId);
  } catch {
    /* blocked storage: nothing to clear */
  }
}

export function readDraft(store: DraftStore | undefined, itemId: string, now: Date = new Date()): Draft | undefined {
  if (!store || !itemId) return undefined;
  let raw: string | null = null;
  try {
    raw = store.getItem(DRAFT_PREFIX + itemId);
  } catch {
    return undefined;
  }
  if (!raw) return undefined;
  try {
    const d = JSON.parse(raw) as Draft;
    const at = Date.parse(d?.at);
    if (d?.v !== 1 || d.itemId !== itemId || !d.def?.item || !d.def?.outputs || Number.isNaN(at) || now.getTime() - at > DRAFT_MAX_AGE_MS) {
      clearDraft(store, itemId);
      return undefined;
    }
    return d;
  } catch {
    clearDraft(store, itemId);
    return undefined;
  }
}

/** The definition without what changes on every save (the revision stamp), for comparing two copies. */
function content(def: ModelDefinition): string {
  const { saved: _saved, ...item } = def.item;
  return JSON.stringify({ ...def, item });
}

export interface Recovery {
  def: ModelDefinition;
  /** the revision to save on top of (what Fabric has) */
  baseRev: number;
  at: string;
  conflict?: ConflictNote;
}

/**
 * On opening: whether this browser holds changes Fabric does not have. None when there is no draft or it equals what
 * was loaded. A draft made on the revision Fabric still has is taken as it is; one made on an older revision is merged
 * with what Fabric has now (the same rule as an autosave).
 */
export function recover(draft: Draft | undefined, loaded: ModelDefinition): Recovery | undefined {
  if (!draft) return undefined;
  if (content(draft.def) === content(loaded)) return undefined;
  const loadedRev = revisionOf(loaded);
  if (draft.baseRev >= loadedRev) {
    return { def: draft.def, baseRev: Math.max(loadedRev, draft.baseRev), at: draft.at };
  }
  const r = resolve(draft.def, draft.base, draft.baseRev, loaded);
  return { def: r.def, baseRev: r.baseRev, at: draft.at, conflict: r.conflict };
}

// ------------------------------------------------------------------ the words ------------------------------------------

export function hhmm(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().slice(11, 16) + " UTC";
}

export function recoveredWords(r: Recovery): string {
  return `Recovered changes from ${hhmm(r.at)} that were not saved in Fabric yet; they are being saved now.`;
}

export function conflictWords(c: ConflictNote): string {
  const parts: string[] = [`Someone else saved this item at ${hhmm(c.at)}.`];
  if (c.kept) parts.push(`Their decision on ${c.kept} ${c.kept === 1 ? "item" : "items"} you had not changed was kept.`);
  if (c.overwritten) parts.push(`On ${c.overwritten} ${c.overwritten === 1 ? "item" : "items"} you both changed, your decision was saved over theirs.`);
  if (!c.kept && !c.overwritten) parts.push("None of your decisions differ from theirs.");
  return parts.join(" ");
}

export type AutosaveState = "idle" | "pending" | "saving" | "saved" | "failed";

/** One short line for the indicator: a mark that is not a colour, a tone and the words. */
export function indicatorWords(state: AutosaveState, at?: string, tries?: number):
  { mark: string; tone: "ok" | "wait" | "bad"; words: string } {
  if (state === "pending") return { mark: "•", tone: "wait", words: "Unsaved changes: saving in a moment…" };
  if (state === "saving") return { mark: "…", tone: "wait", words: "Saving…" };
  if (state === "saved") return { mark: "✓", tone: "ok", words: at ? `Saved ${hhmm(at)}` : "Saved" };
  if (state === "failed") {
    return { mark: "✕", tone: "bad",
      words: `Not saved: Fabric did not confirm${tries ? ` after ${tries} ${tries === 1 ? "try" : "tries"}` : ""}. Your changes are kept in this browser; Save again.` };
  }
  return { mark: "✓", tone: "ok", words: "Saved" };
}

/** A random id for this editor session (which session saved; not a person). */
export function newSession(): string {
  try {
    const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
    if (c?.randomUUID) return c.randomUUID().slice(0, 8);
  } catch {
    /* fall through */
  }
  return Math.random().toString(36).slice(2, 10);
}
