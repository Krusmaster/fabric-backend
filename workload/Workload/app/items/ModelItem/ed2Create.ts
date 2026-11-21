/**
 * ED2 (Gustav's editor test of 21 November 2026, part 2: the Dry run step and two Creates). A Create either finishes or
 * explains once. Pure functions, no React and no Fabric client (ed2Create.test.ts), deterministic, no AI:
 *
 * - build order: lakehouse -> silver -> gold -> pipeline -> model -> report and agent (BUILT_ON). An output is sent
 *   only when what it is built on in this Create is built; when one fails, what is built on it is not sent and is
 *   listed once as "waiting for silver" (dependsOn, waitingCard);
 * - the dry run's blocker: Create stays off while a blocker the dry run already knew about remains, with one line why
 *   and one button that fixes it (createBlocker);
 * - after a partial result: one "Fix and finish" at the top builds only what is missing, reusing what exists
 *   (toFinish); Try again on a card only where a retry can work, else the reason (retryState);
 * - the same error is said once, not per output (sharedErrors);
 * - the review used is the freshest one, never an older saved one (freshestReview);
 * - the result card shows this build's items and puts earlier builds under one collapsed line (splitBuilds);
 * - one owner sentence and one plan sentence everywhere (ownerLine, planLine), never "Plan ?".
 */
import type { BuildCard, CreatedRef, ManyAnswer, OutputKind, OutputRequest } from "./engineClient";
import type { ReviewFile } from "./ModelItemDefinition";

// ------------------------------------------------------------------ build order ------------------------------------

/** What each output is built on, as ED1's "Built on" lines say it: the lakehouse flow first (silver, then gold, then
 * the pipeline over both), the semantic model on the tables the flow fills, its report on it, the data agent on the
 * filled tables, the ontology on silver, the App on its API. The API for GraphQL reads the source's tables: it waits for
 * nothing. Only outputs of this Create count. */
export const BUILT_ON: Record<OutputKind, OutputKind[]> = {
  silver_notebook: [],
  gold_views: ["silver_notebook"],
  pipeline: ["silver_notebook", "gold_views"],
  semantic_model: ["silver_notebook", "gold_views", "pipeline"],
  report: ["semantic_model"],
  data_agent: ["silver_notebook", "gold_views", "pipeline"],
  ontology: ["silver_notebook"],
  graphql: [],
  rayfin_app: ["graphql"],
};

/** The build order of the stages (for Fix and finish and the cards' order). */
export const STAGES: OutputKind[][] = [
  ["silver_notebook"],
  ["gold_views"],
  ["pipeline"],
  ["semantic_model", "graphql"],
  ["report", "data_agent", "ontology"],
  ["rayfin_app"],
];

export const SHORT: Record<OutputKind, string> = {
  silver_notebook: "silver",
  gold_views: "gold",
  pipeline: "the pipeline",
  semantic_model: "the semantic model",
  report: "the report",
  graphql: "the API for GraphQL",
  ontology: "the ontology",
  data_agent: "the data agent",
  rayfin_app: "the App",
};

export function stageOf(kind: OutputKind): number {
  return STAGES.findIndex((s) => s.includes(kind));
}

/** The outputs of this Create that `o` waits for (BUILT_ON). A report on an existing model of its own (o.model) does
 * not wait for this Create's semantic model. */
export function dependsOn(o: Pick<OutputRequest, "kind" | "model">, all: Pick<OutputRequest, "kind">[]): OutputKind[] {
  const have = new Set(all.map((x) => x.kind));
  return BUILT_ON[o.kind].filter((k) => have.has(k)).filter((k) => !(o.kind === "report" && o.model && k === "semantic_model"));
}

/** A card whose output is not in Fabric after its step: refused, an error, no answer, stopped, or waiting for another. */
export function notBuilt(c: BuildCard | undefined): boolean {
  if (!c) return true;
  if (c.status === "waiting" || c.status === "running") return false;
  if (c.already_built) return false;
  if (c.built_from && c.choices?.length) return true;
  return c.status === "lost" || !!c.refusal || !!c.answer?.error || c.after_run === "stopped";
}

/** The first output `o` waits for that is not built (undefined: it may be sent). */
export function blockedBy(o: Pick<OutputRequest, "kind" | "model">, all: Pick<OutputRequest, "kind">[],
  cardOf: (k: OutputKind) => BuildCard | undefined): OutputKind | undefined {
  return dependsOn(o, all).find((k) => notBuilt(cardOf(k)));
}

export const WAITING_KIND = "waiting_for";

/** The card of an output not sent because what it builds on is not built: one line, no error of its own. */
export function waitingCard(card: BuildCard, dep: OutputKind): BuildCard {
  return {
    ...card,
    status: "done",
    refusal: {
      error: `Waiting for ${SHORT[dep]}: not sent, because ${SHORT[dep]} was not built.`,
      kind: WAITING_KIND,
      hint: "Fix and finish builds it once that is fixed.",
      waiting_for: dep,
    } as BuildCard["refusal"] & { waiting_for: OutputKind },
  };
}

export function isWaiting(c: BuildCard): boolean {
  return c.refusal?.kind === WAITING_KIND;
}

// ------------------------------------------------------------------ the same error once ----------------------------

export interface SharedError {
  error: string;
  hint?: string;
  outputs: OutputKind[];
  labels: string[];
}

function errorOf(c: BuildCard): { error: string; hint?: string } | undefined {
  if (isWaiting(c)) return undefined;
  const e = c.refusal ?? (c.answer?.error ? { error: c.answer.error, hint: c.answer.hint } : undefined);
  return e?.error ? { error: e.error, hint: e.hint } : undefined;
}

/** Errors that more than one card has, word for word (names of the output itself aside): said once, above the cards. */
export function sharedErrors(cards: BuildCard[]): SharedError[] {
  const by = new Map<string, SharedError>();
  for (const c of cards) {
    const e = errorOf(c);
    if (!e) continue;
    const key = e.error.split(c.name).join("<name>");
    const got = by.get(key) ?? { error: e.error, hint: e.hint, outputs: [], labels: [] };
    got.outputs.push(c.output);
    got.labels.push(c.label);
    by.set(key, got);
  }
  return [...by.values()].filter((x) => x.outputs.length > 1);
}

/** The card's own line when its error is said once above. */
export function sameErrorLine(c: BuildCard, shared: SharedError[]): string | undefined {
  return shared.some((s) => s.outputs.includes(c.output)) ? "Not built: the error is said once, above." : undefined;
}

// ------------------------------------------------------------------ Create's blocker --------------------------------

export type BlockerFix = "free_names" | "leave_out";

export interface Blocker {
  line: string;
  fix: BlockerFix;
  button: string;
  outputs: OutputKind[];
}

/** A blocker the dry run already knows about: a card Create would refuse (a name taken, a missing permission, an
 * error) or one waiting for a choice. Create stays off; the one button fixes it: free names for a taken name or a
 * choice, else leave those outputs out. undefined: Create may start. */
export function createBlocker(a: ManyAnswer | undefined): Blocker | undefined {
  if (!a) return undefined;
  const stop = a.outputs.filter((c) => c.refusal || c.answer?.error || (c.built_from && c.choices?.length));
  if (!stop.length) return undefined;
  const named = stop.filter((c) => c.refusal?.kind === "already_exists" || (c.built_from && c.choices?.length));
  const first = stop[0];
  const why = first.refusal?.error ?? first.answer?.error ?? first.decision?.words ?? `${first.label} ${first.name} cannot be built.`;
  const more = stop.length > 1 ? ` (and ${stop.length - 1} more output${stop.length > 2 ? "s" : ""})` : "";
  if (named.length === stop.length) {
    return { line: `Create is off: ${why}${more}`, fix: "free_names", button: "Use free names", outputs: stop.map((c) => c.output) };
  }
  return {
    line: `Create is off: ${why}${more}`,
    fix: "leave_out",
    button: stop.length === 1 ? `Leave out the ${inSentence(first.label)}` : `Leave out these ${stop.length} outputs`,
    outputs: stop.map((c) => c.output),
  };
}

/** A label inside a sentence: "silver notebook", "semantic model", but "API for GraphQL" keeps its case. */
export function inSentence(label: string): string {
  return label.length > 1 && label[1] === label[1].toLowerCase() ? label.charAt(0).toLowerCase() + label.slice(1) : label;
}

// ------------------------------------------------------------------ after a partial result -------------------------

/** The outputs Fix and finish sends again, in build order: every card not built, waiting ones included. */
export function toFinish(cards: BuildCard[]): BuildCard[] {
  return [...cards].filter((c) => notBuilt(c) && !(c.built_from && c.choices?.length))
    .sort((x, y) => stageOf(x.output) - stageOf(y.output));
}

export function finishLabel(n: number): string {
  return `Fix and finish (${n} not built)`;
}

/** Whether Try again on this card can work, and if not, why (shown instead of the button). */
export function retryState(c: BuildCard): { can: boolean; why?: string } {
  if (c.status === "waiting" || c.status === "running" || !notBuilt(c)) return { can: false };
  if (isWaiting(c)) return { can: false, why: `Built by Fix and finish once ${SHORT[(c.refusal as { waiting_for?: OutputKind }).waiting_for ?? "silver_notebook"]} is built.` };
  const kind = c.refusal?.kind ?? c.answer?.kind;
  if (kind === "already_exists") return { can: false, why: "Its name is taken by an item this Model did not build: choose another name on the Choose step." };
  if (kind === "consent") return { can: false, why: "It needs a permission first (the steps are on this card); Try again after that." };
  if (kind === "bad_request") return { can: false, why: "Change the choice this card names on the Choose step; then Fix and finish." };
  if (c.built_from && c.choices?.length) return { can: false };
  return { can: true };
}

// ------------------------------------------------------------------ the result's items -----------------------------

export interface BuildSplit<T> {
  now: T[];
  earlier: T[];
}

/** This build's items and the items of earlier Creates (kept, listed under "Earlier builds (N)"). */
export function splitBuilds<T extends { id?: string; earlier?: boolean }>(items: T[], thisRun?: CreatedRef[]): BuildSplit<T> {
  const ids = thisRun ? new Set(thisRun.map((c) => c.id)) : undefined;
  const isEarlier = (x: T) => (ids ? !(x.id && ids.has(x.id)) : !!x.earlier);
  return { now: items.filter((x) => !isEarlier(x)), earlier: items.filter(isEarlier) };
}

export function earlierLabel(n: number): string {
  return `Earlier builds (${n})`;
}

/** One line per item of this build: its status in one word or two. */
export function itemStatus(c: BuildCard): string {
  if (c.status === "running") return "creating";
  if (c.status === "waiting") return c.after_run === "waiting" ? "waiting for the pipeline's run" : "waiting";
  if (isWaiting(c)) return `waiting for ${SHORT[(c.refusal as { waiting_for?: OutputKind }).waiting_for ?? "silver_notebook"]}`;
  if (c.already_built) return "already built";
  if (notBuilt(c)) return "not built";
  return c.would === "update" ? "updated" : "created";
}

// ------------------------------------------------------------------ one owner, one plan ----------------------------

/** The same sentence on Choose, the dry run and the result (workload_api.owner_words). */
export function ownerLine(owner: string | null | undefined): string {
  return owner ? `Owner: ${owner}. Change it on the Choose step.` : "Owner: not set. Choose one on the Choose step.";
}

/** The plan sentence; nothing when the plan is not known (never "Plan ?"). */
export function planLine(plan: { plan_id?: string | null; schema_fingerprint?: string | null } | undefined): string {
  if (!plan?.plan_id) return "";
  return `Plan ${plan.plan_id}${plan.schema_fingerprint ? `, schema ${plan.schema_fingerprint}` : ""}.`;
}

// ------------------------------------------------------------------ the freshest review ----------------------------

/** When a review was last made or checked: its newest check (checked_at), else its own time if it carries one. */
export function reviewStamp(r: ReviewFile | undefined): string {
  if (!r) return "";
  let best = typeof r.reviewed_at === "string" ? (r.reviewed_at as string) : "";
  for (const it of r.items ?? []) {
    const at = (it as { check?: { checked_at?: string } }).check?.checked_at;
    if (at && at > best) best = at;
  }
  return best;
}

/** Of the review in view and one that arrives later (a re-read of the saved review on reopening, started before the
 * person checked the rows again), the fresher: an older answer never replaces a newer check. `replaced` says whether
 * the incoming one was kept out, for one line. */
export function freshestReview(current: ReviewFile | undefined, incoming: ReviewFile | undefined): { review: ReviewFile | undefined; kept: "current" | "incoming" } {
  if (!incoming) return { review: current, kept: "current" };
  if (!current) return { review: incoming, kept: "incoming" };
  return reviewStamp(current) > reviewStamp(incoming) ? { review: current, kept: "current" } : { review: incoming, kept: "incoming" };
}

export const OLDER_REVIEW_LINE = "The saved review was older than the check you just ran; the dry run uses the newer one.";

/** The line under the dry run's check line, once, when the item's saved review is older than the one used. */
export function staleLine(saved: ReviewFile | undefined, used: ReviewFile | undefined): string | undefined {
  const s = reviewStamp(saved), u = reviewStamp(used);
  return s && u && s < u ? OLDER_REVIEW_LINE : undefined;
}
