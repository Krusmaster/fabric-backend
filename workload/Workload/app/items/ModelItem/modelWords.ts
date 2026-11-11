/**
 * Krusgraph (n173): what the Model editor says, in plain English, and what Onto, Thinker and Builder say in their
 * bubbles. Pure functions over the review file and the check's answer, so they run in unit tests (modelWords.test.ts).
 *
 * The roles are the site's and the MCP Apps cards' (fabric_backend/static/mascots.js, mcp_apps_words.py):
 *   Onto     green   says the numbers: tables, keys, links, how many passed the check
 *   Thinker  violet  checks against the rows and asks the questions (an open question comes with its choices)
 *   Builder  coral   says what can be built, and that a dry run comes first
 * No bubble reads out a call: no name=value, no "run <tool> with", no tool names (WORDS_WITH_ARGUMENTS, the cards' own
 * pattern; the tests assert it never matches). Rule codes stay as pills with a tooltip (ruleMeaning).
 */
import { ReviewFile, ReviewItem, ReviewStatus } from "./ModelItemDefinition";

// The same pattern as fabric_backend/mcp_apps_words.WORDS_WITH_ARGUMENTS (the cards' "never argument syntax" rule),
// plus the engine's tool names, which mean nothing to a person in Fabric.
const ARGS_SAID = /\b[a-z_]+=(?:"|'|\[|\{|true\b|false\b|\d)|\brun [a-z]+_[a-z_]+\b|\b[a-z]+_[a-z_]+\(/i;
const TOOL_NAMES = /\b(validate_plan|plan_backend|review_plan|create_backend)\b|\bwith (keys|confirmed)\b/;

export function hasArgumentSyntax(text: string): boolean {
  return ARGS_SAID.test(text) || TOOL_NAMES.test(text);
}

export type CheckState = "passed" | "failed" | "stale" | "not_checked";

/** What each rule means, for the pill's tooltip (fabric_backend/infer.py, the rules' own definitions). */
export const RULE_MEANING: Record<string, string> = {
  K0: "Key declared in the lakehouse.",
  K1: "Key you chose.",
  K2: "Key found from the column name: id, or the table's name with _id, _key, _code or _no.",
  K3: "No key found. The table can be queried, but nothing can point to it.",
  K4: "Key of a link table: its two or more reference columns together.",
  K5: "Key of a line table: the reference to its header plus a line number.",
  R0: "Link declared in the lakehouse.",
  R1: "Link found from the name: the column is the other table's name with _id, _key, _code or _no.",
  R2: "Link found from the name: the column has the same name as the other table's key.",
  R3: "Link found from the name: every column of the other table's key appears in this table.",
  R4: "Link found from a weaker name match, through synonyms.",
  R5: "Link found from the values: every value in the column exists in the other table.",
  confirmed: "Link you confirmed.",
  "SAP pack": "Link from the SAP knowledge pack.",
};

export function ruleMeaning(rule: string): string {
  return RULE_MEANING[rule] ?? `Rule ${rule}.`;
}

function plural(n: number, one: string, many?: string): string {
  return `${n} ${n === 1 ? one : many ?? one + "s"}`;
}

function listed(xs: string[], max = 3): string {
  if (xs.length > max) return `${xs.slice(0, max).join(", ")} and ${xs.length - max} more`;
  return xs.length <= 1 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

export function checkState(item: ReviewItem): CheckState {
  const s = item.check?.status;
  return s === "passed" || s === "failed" || s === "stale" ? s : "not_checked";
}

/** One row's text: "orders → customers (customer_id)" or "Key of orders: order_id". */
export function itemText(item: ReviewItem): string {
  if (item.type === "key") return `Key of ${item.table}: ${item.columns.join(" + ")}`;
  const s = item.columns.join(" + ");
  const t = (item.target_columns ?? []).join(" + ");
  return `${item.source} → ${item.target} (${s === t || !t ? s : `${s} → ${t}`})`;
}

/** What the check found for one row, in words: "Passed.", "3 orders point at nothing.", "2 duplicates." */
export function checkText(item: ReviewItem): string {
  const c = (item.check ?? {}) as { status?: string; result?: Record<string, number>; was?: string };
  const r = c.result ?? {};
  switch (checkState(item)) {
    case "passed":
      return "Passed the check.";
    case "failed":
      if (item.type === "key") {
        const dup = Math.max((r.rows ?? 0) - (r.nulls ?? 0) - (r.distinct ?? 0), 0);
        const parts = [dup ? plural(dup, "duplicate") : "", r.nulls ? `${plural(r.nulls, "empty value")}` : ""].filter(Boolean);
        return `Failed: ${parts.length ? parts.join(" and ") : "not unique"}.`;
      }
      if (r.orphans) return `Failed: ${plural(r.orphans, "row points", "rows point")} at nothing.`;
      return "Failed: the key it points at is not unique.";
    case "stale":
      return "Checked before the data changed; check again.";
    default:
      return "Not checked yet.";
  }
}

// ------------------------------------------------------------------ n209: links that hold in the rows ----------------
// The founder's live test of 10 November 2026: two links the rows held (0 orphans) were rejected, and the semantic model,
// the API and the ontology had 5 relationships instead of 7. A link that holds now says so next to Reject, and rejecting
// it says plainly what the outputs lose. Only a counted check is shown: a link not checked yet says nothing here.

/** The rows a passed link was counted on, when the check counted it with 0 orphans; undefined otherwise. */
export function holdingRows(item: ReviewItem): number | undefined {
  if (item.type !== "relationship" || checkState(item) !== "passed") return undefined;
  const r = ((item.check ?? {}) as { result?: Record<string, number> }).result ?? {};
  if (r.orphans !== 0 || typeof r.rows_with_value !== "number") return undefined;
  return r.rows_with_value;
}

/** "This link holds in the rows: 0 of 9 rows point at nothing." for a link the check counted with 0 orphans. */
export function holdsText(item: ReviewItem): string | undefined {
  const n = holdingRows(item);
  return n === undefined ? undefined : `This link holds in the rows: 0 of ${n} ${n === 1 ? "row points" : "rows point"} at nothing.`;
}

/** The links the outputs will have: every relationship that is not rejected (the build leaves rejected ones out). */
export function keptLinks(review: ReviewFile | undefined): number {
  return (review?.items ?? []).filter((it) => it.type === "relationship" && it.review !== "rejected").length;
}

/** Rejected links that hold in the rows. */
export function rejectedHolding(review: ReviewFile | undefined): ReviewItem[] {
  return (review?.items ?? []).filter((it) => it.review === "rejected" && holdingRows(it) !== undefined);
}

/** What rejecting a holding link costs, in plain words; undefined when no rejected link holds. */
export function rejectedHoldingText(review: ReviewFile | undefined): string | undefined {
  const lost = rejectedHolding(review).length;
  if (!lost) return undefined;
  const kept = keptLinks(review);
  return `You rejected ${lost === 1 ? "a link that holds" : `${lost} links that hold`} in the rows. The semantic model, the API ` +
    `and the ontology will have ${lost === 1 ? "one relationship" : `${lost} relationships`} fewer: ${plural(kept, "relationship")} ` +
    `instead of ${kept + lost}. Accept ${lost === 1 ? "it" : "them"} to keep ${lost === 1 ? "it" : "them"}.`;
}

/** The same for one rejected row. */
export function rejectedRowText(item: ReviewItem): string | undefined {
  if (item.review !== "rejected" || holdingRows(item) === undefined) return undefined;
  return "Rejected, though it holds in the rows: the semantic model, the API and the ontology will have one relationship fewer.";
}

// ------------------------------------------------------------------ Accept all ---------------------------------------

/** Which items Accept all changes: every one still proposed or open; with onlyPassed, only those that passed the check.
 * A rejection is a person's decision and is never overturned by Accept all. */
export function acceptAllTargets(review: ReviewFile | undefined, onlyPassed = false): string[] {
  return (review?.items ?? [])
    .filter((it) => it.review === "proposed" || it.review === "open")
    .filter((it) => !onlyPassed || checkState(it) === "passed")
    .map((it) => it.id);
}

export function acceptAll(review: ReviewFile, onlyPassed = false): ReviewFile {
  const ids = new Set(acceptAllTargets(review, onlyPassed));
  return { ...review, items: review.items.map((it) => (ids.has(it.id) ? { ...it, review: "accepted" as ReviewStatus, reason: "" } : it)) };
}

// ------------------------------------------------------------------ the summary and the bubbles ----------------------

export interface CheckTotals {
  checked: number;
  checked_at?: string | null;
  keys: Record<CheckState, number>;
  relationships: Record<CheckState, number>;
}

/** The check's totals from the review file itself (so a re-opened item shows its last check). */
export function totalsOf(review: ReviewFile | undefined): CheckTotals {
  const zero = (): Record<CheckState, number> => ({ passed: 0, failed: 0, stale: 0, not_checked: 0 });
  const out: CheckTotals = { checked: 0, checked_at: null, keys: zero(), relationships: zero() };
  for (const it of review?.items ?? []) {
    const s = checkState(it);
    (it.type === "key" ? out.keys : out.relationships)[s] += 1;
    if (s === "passed" || s === "failed") {
      out.checked += 1;
      const at = (it.check as { checked_at?: string })?.checked_at;
      if (at && (!out.checked_at || at > out.checked_at)) out.checked_at = at;
    }
  }
  return out;
}

/** The review's state as short sentences (Onto's words, also shown when the mascots are off). */
export function summaryLines(review: ReviewFile | undefined): string[] {
  const items = review?.items ?? [];
  const keys = items.filter((it) => it.type === "key").length;
  const links = items.length - keys;
  const by = (s: ReviewStatus) => items.filter((it) => it.review === s).length;
  const tables = Object.keys(((review?.snapshot as { tables?: object }) ?? {}).tables ?? {}).length;
  const out: string[] = [];
  out.push(tables ? `${plural(tables, "table")}, ${keys} with a key, and ${plural(links, "link")} between them.`
    : `${plural(keys, "key")} and ${plural(links, "link")}.`);
  const waiting = by("proposed") + by("open");
  if (!items.length) out.push("Nothing to decide yet.");
  else if (!waiting) out.push(`You have decided all ${items.length}: ${by("accepted")} accepted, ${by("rejected")} rejected.`);
  else if (waiting === items.length) out.push(`All ${items.length} are suggestions waiting for you to accept or reject.`);
  else out.push(`${waiting} still ${waiting === 1 ? "waits" : "wait"} for you; ${by("accepted")} accepted, ${by("rejected")} rejected.`);
  if (by("rejected")) out.push("What you reject is left out of what you build.");
  return out;
}

/** What the check found, as sentences. */
export function checkLines(review: ReviewFile | undefined): string[] {
  const t = totalsOf(review);
  if (!t.checked) return [];
  const out: string[] = [];
  const k = t.keys, r = t.relationships;
  if (k.passed + k.failed) out.push(`${k.passed} of ${plural(k.passed + k.failed, "key")} ${k.passed === 1 ? "is" : "are"} unique in the rows.`);
  if (r.passed + r.failed)
    out.push(`${r.passed} of ${plural(r.passed + r.failed, "link")} ${r.passed === 1 ? "holds" : "hold"}` +
      (r.failed ? `; ${r.failed} ${r.failed === 1 ? "has" : "have"} rows that point at nothing.` : ", with no row pointing at nothing."));
  const left = k.not_checked + r.not_checked + k.stale + r.stale;
  if (left) out.push(`${plural(left, "item was", "items were")} not checked.`);
  return out;
}

export interface Choice {
  label: string;
  /** what the editor does: give a key, link a column to a table, or keep the table as it is */
  action: { kind: "key"; table: string; columns: string[] } | { kind: "link"; source: string; column: string; target: string; targetColumns: string[] } | { kind: "keep"; about: string };
}

export interface Question {
  about: string;
  text: string;
  choices: Choice[];
}

type Snapshot = { tables?: Record<string, { columns?: Record<string, string>; key?: string[] }> };

/** Thinker's questions in plain words, each with its choices inline. The engine's own question text names arguments
 * ("give one with keys"); here the same question is asked as a person would, and the choices do the rest. */
export function questions(review: ReviewFile | undefined, answered: Record<string, string> = {}): Question[] {
  const snap = ((review?.snapshot as Snapshot) ?? {}).tables ?? {};
  const out: Question[] = [];
  for (const q of review?.open_questions ?? []) {
    if (answered[q.about]) continue;
    if (q.about.startsWith("key:")) {
      const table = q.about.slice(4);
      const cols = Object.keys(snap[table]?.columns ?? {});
      out.push({
        about: q.about,
        text: `${table} has no key that I could find, so nothing can point to it. Is that right?`,
        choices: [
          { label: "Yes, keep it without a key", action: { kind: "keep", about: q.about } },
          ...cols.map((c) => ({ label: `Its key is ${c}`, action: { kind: "key" as const, table, columns: [c] } })),
        ],
      });
      continue;
    }
    const m = /^Which table does ([^.]+)\.(\S+) refer to: (.+)\?/.exec(q.question);
    if (m) {
      const [, source, column, targets] = m;
      const choices: Choice[] = targets.split(" or ").map((t) => t.trim()).filter((t) => (snap[t]?.key ?? []).length === 1)
        .map((t) => ({ label: `It points to ${t}`, action: { kind: "link" as const, source, column, target: t, targetColumns: snap[t].key } }));
      choices.push({ label: "Leave it unlinked", action: { kind: "keep", about: q.about } });
      out.push({ about: q.about, text: `${source}.${column} could point to ${listed(targets.split(" or "))}. Which one?`, choices });
      continue;
    }
    const plain = q.question.replace(/\s*\(?\b(?:with|use) (?:keys|confirmed)\b\)?/g, "");
    out.push({ about: q.about, text: hasArgumentSyntax(plain) ? `Something about ${q.about} needs your decision.` : plain,
      choices: [{ label: "Noted", action: { kind: "keep", about: q.about } }] });
  }
  return out;
}

export interface Sayings {
  onto?: string;
  thinker?: string;
  builder?: string;
  /** true only when a check ran and nothing failed: the only time a mascot may look glad */
  glad: boolean;
}

/** The three bubbles for the review step. Each is a sentence or nothing; never argument syntax. */
export function sayings(review: ReviewFile | undefined, answered: Record<string, string> = {}): Sayings {
  const t = totalsOf(review);
  const lines = [...summaryLines(review), ...checkLines(review)];
  const qs = questions(review, answered);
  const failed = t.keys.failed + t.relationships.failed;
  let thinker: string;
  if (!t.checked) thinker = "Shall I check these against the rows? I count, I never show a value, and nothing in Fabric changes.";
  else if (failed) thinker = `${plural(failed, "item", "items")} failed the check. I would reject ${failed === 1 ? "it" : "them"} or fix the data before building.`;
  else if (qs.length) thinker = `Everything I checked holds. ${qs.length === 1 ? "One question is" : `${qs.length} questions are`} left for you, below.`;
  else thinker = "Everything I checked holds in the rows.";
  if (t.checked && qs.length && failed) thinker += ` ${qs.length === 1 ? "One question is" : `${qs.length} questions are`} also left for you.`;
  const waiting = acceptAllTargets(review).length;
  const builder = waiting
    ? "When you have decided, choose Next. I show a dry run before anything is created."
    : "Ready when you are: choose Next for the dry run. Nothing is created until you choose Create.";
  const clean = (s: string) => (s && !hasArgumentSyntax(s) ? s : undefined);
  return { onto: clean(lines.join(" ")), thinker: clean(thinker), builder: clean(builder), glad: t.checked > 0 && failed === 0 };
}

/** The dry run's line about the check: what passed, or that nothing was checked yet. */
export function dryRunCheckLine(rowCheck: CheckTotals | undefined): string {
  if (!rowCheck || !rowCheck.checked) return "Not checked against the rows yet. Use Check against the rows in the review to count them.";
  const k = rowCheck.keys, r = rowCheck.relationships;
  const when = rowCheck.checked_at ? ` (${rowCheck.checked_at.replace("T", " ").replace("Z", " UTC")})` : "";
  const failed = k.failed + r.failed;
  return `Checked against the rows${when}: ${k.passed} of ${plural(k.passed + k.failed, "key")} and ${r.passed} of ` +
    `${plural(r.passed + r.failed, "link")} passed` + (failed ? `; ${failed} failed.` : ".");
}
