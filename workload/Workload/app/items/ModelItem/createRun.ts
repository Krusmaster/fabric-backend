/**
 * n197: a Create that runs in the background and survives a reload, a closed tab or a phone asleep. Pure functions, no
 * React and no Fabric client (createRun.test.ts).
 *
 * outputs.json keeps, besides the created ids:
 *   pending     every item a Create step sent, recorded before the step is sent (output, type, name). An item Fabric
 *               finishes after a wait is then adopted as built by this Model by the engine (workload_api._pending),
 *               not refused as "not built by this Krusgraph Model" (demo_lh_model4, 10 November 2026).
 *   create_run  the Create in progress: its id, its outputs and the engine's operation id per output, and whether it
 *               has finished. A reopened item reads the operations (POST /workload/v1/operation {item_id}) and shows
 *               the same run, going on where it is.
 */
import { BuildCard, CreatedRef, OperationState, OutputKind, OutputRequest, PendingItem } from "./engineClient";
import { OutputChoice } from "./ModelItemDefinition";
import { ORDER } from "./buildWords";

export interface CreateRunRecord {
  id: string;
  at: string;
  /** the outputs as Create sent them (their order is the engine's) */
  outputs: OutputRequest[];
  /** the engine's operation id per output */
  ops: Partial<Record<OutputKind, string>>;
  /** every step has its answer and what waited for the run is done */
  finished: boolean;
}

export function newCreateId(now = Date.now(), rnd = Math.random): string {
  return `c${now.toString(36)}${Math.floor(rnd() * 1e8).toString(36)}`;
}

/** The items one output writes, as the engine names them (workload_api._names): the pipeline writes its notebooks too. */
export function itemsOf(o: OutputRequest, all: OutputRequest[], schema: string): { type: string; name: string }[] {
  const type: Record<OutputKind, string> = {
    silver_notebook: "Notebook", gold_views: "Notebook", pipeline: "DataPipeline", semantic_model: "SemanticModel",
    report: "Report", graphql: "GraphQLApi", ontology: "Ontology", data_agent: "DataAgent", rayfin_app: "AppBackend",
  };
  if (o.kind !== "pipeline") return [{ type: type[o.kind], name: o.name }];
  const silver = all.find((x) => x.kind === "silver_notebook")?.name || `silver_${schema}`;
  const gold = all.find((x) => x.kind === "gold_views")?.name || `gold_${schema}`;
  return [
    { type: "DataPipeline", name: o.name },
    { type: "Notebook", name: silver },
    { type: "Notebook", name: gold },
    { type: "Notebook", name: `${o.name}_check` },
  ];
}

/** outputs.json's pending list with this output's items added (once each), before its step is sent. */
export function withPending(pending: PendingItem[] | undefined, o: OutputRequest, all: OutputRequest[], schema: string, at: string): PendingItem[] {
  const base = pending ?? [];
  const add = itemsOf(o, all, schema)
    .filter((i) => !base.some((p) => p.type === i.type && p.name.toLowerCase() === i.name.toLowerCase()))
    .map((i) => ({ output: o.kind, type: i.type, name: i.name, at }));
  return [...base, ...add];
}

/** The pending list once a step has its answer: what it created (or found built) is no longer pending. An answer that
 * says Fabric may still be making it (no answer, still running in Fabric) keeps the entries. */
export function settlePending(pending: PendingItem[] | undefined, card: BuildCard, created: CreatedRef[]): PendingItem[] {
  const base = pending ?? [];
  if (stillPending(card)) return base;
  const done = new Set(created.map((c) => `${c.type}:${c.name.toLowerCase()}`));
  return base.filter((p) => p.output !== card.output && !done.has(`${p.type}:${p.name.toLowerCase()}`));
}

/** The step may still finish in Fabric: no answer, the engine lost it, or Fabric was still making it at the end. */
export function stillPending(card: BuildCard): boolean {
  const kind = card.refusal?.kind ?? card.answer?.kind;
  return card.status === "lost" || kind === "no_answer" || kind === "timeout" || kind === "pending_fabric" || !!(card as any).pending_fabric;
}

/** The record of a new Create. */
export function startRun(id: string, outputs: OutputRequest[], at: string): CreateRunRecord {
  return { id, at, outputs, ops: {}, finished: false };
}

export function withOperation(run: CreateRunRecord, kind: OutputKind, opId: string): CreateRunRecord {
  return { ...run, ops: { ...run.ops, [kind]: opId } };
}

/** Reads a stored create_run, or undefined when missing or not of this shape. */
export function readRun(x: unknown): CreateRunRecord | undefined {
  const v = x as CreateRunRecord;
  if (!v || typeof v !== "object" || typeof v.id !== "string" || !Array.isArray(v.outputs) || typeof v.ops !== "object") return undefined;
  return { id: v.id, at: String(v.at ?? ""), outputs: v.outputs, ops: v.ops ?? {}, finished: !!v.finished };
}

/** What a reopened item knows of each output of its Create, from the engine's operations of the item: the answer of
 * a finished step, the operation of a running one (read again, never sent again), or nothing (sent now). A lost
 * operation counts as nothing: its step is sent again, and what it made is adopted through pending. */
export interface Known {
  answers: Partial<Record<OutputKind, any>>;
  running: Partial<Record<OutputKind, string>>;
  progress: Partial<Record<OutputKind, OperationState>>;
}

export function knownOf(run: CreateRunRecord, ops: OperationState[]): Known {
  const out: Known = { answers: {}, running: {}, progress: {} };
  for (const o of run.outputs) {
    const id = run.ops[o.kind];
    const op = ops.find((x) => (id ? x.operation_id === id || x.id === id : false) || (!id && x.output === o.kind && x.create === run.id));
    if (!op || op.status === "lost") continue;
    if (op.status === "done") {
      if ((op.http ?? 200) < 400 && op.answer && !op.answer.error) out.answers[o.kind] = op.answer;
      continue;
    }
    out.running[o.kind] = op.operation_id ?? op.id;
    out.progress[o.kind] = op;
  }
  return out;
}

/** n197 (item 3): with Run once ticked on the pipeline, the report waits for the run's success (its model is refreshed
 * first). Without Run once nothing waits. */
export function waitsForRun(outputs: OutputRequest[]): OutputKind[] {
  const pipe = outputs.find((o) => o.kind === "pipeline");
  if (!pipe?.jobs?.run_once) return [];
  return outputs.some((o) => o.kind === "report") ? ["report"] : [];
}

export const WAIT_FOR_RUN_WORDS = "Built when the pipeline's run has succeeded: its semantic model is refreshed first, then the report is made.";

export function heldCard(card: BuildCard): BuildCard {
  return { ...card, status: "waiting", after_run: "waiting", after_run_words: WAIT_FOR_RUN_WORDS };
}

export function stoppedCard(card: BuildCard, why: string): BuildCard {
  return {
    ...card, status: "done", after_run: "stopped",
    after_run_words: `Not built: the pipeline's run did not succeed${why ? ` (${why})` : ""}. Fix what its card says, run it again, then choose Try again here.`,
    refusal: { error: `Not built: the pipeline's run did not succeed${why ? ` (${why})` : ""}.`, kind: "run_failed",
      hint: "Fix what the pipeline's card says, then choose Try again." },
  };
}

/** The card while its operation runs: waiting for capacity or still running in Fabric, in words. */
export function withProgress(card: BuildCard, state: OperationState): BuildCard {
  const s = state.status === "waiting_capacity" || state.status === "pending_fabric" ? state.status : "running";
  return {
    ...card,
    status: "running",
    operation_id: state.operation_id ?? state.id,
    progress: { state: s, words: state.progress?.words, capacity_app: state.progress?.capacity_app },
  };
}

/** Cards that "Create the rest" sends again: failed, no answer, or stopped after a failed run. A refusal the person
 * must answer (a name taken by someone else, a choice between Update and a new name) is not sent again blindly. */
export function toRetry(cards: BuildCard[]): BuildCard[] {
  return cards.filter((c) => {
    if (c.status === "waiting" || c.status === "running") return false;
    if (c.built_from && c.choices?.length) return false;
    const kind = c.refusal?.kind ?? c.answer?.kind;
    if (kind === "already_exists" || kind === "consent" || kind === "bad_request") return false;
    return c.status === "lost" || !!c.refusal || !!c.answer?.error || c.after_run === "stopped";
  });
}

/** n197 (item 4): one name suffix per Create. When a new name is needed, every output of the Create gets the same
 * free suffix (demo_lh_model_3 and demo_lh_report_3), never one suffix each. */
export function stripSuffix(name: string): string {
  return name.replace(/_\d{1,3}$/, "");
}

export function namesWithOneSuffix(choices: OutputChoice[], taken: string[]): OutputChoice[] {
  const lower = new Set(taken.map((t) => t.toLowerCase()));
  const on = choices.filter((c) => c.enabled);
  for (let i = 2; i < 1000; i++) {
    const names = on.map((c) => `${stripSuffix(c.name).slice(0, 118)}_${i}`);
    if (names.every((n) => !lower.has(n.toLowerCase()))) {
      return choices.map((c) => (c.enabled ? { ...c, name: `${stripSuffix(c.name).slice(0, 118)}_${i}` } : c));
    }
  }
  return choices;
}

/** n197 (item 4): the data product lists the items of this item's Creates; those not built by the latest Create are
 * marked earlier. */
export function markEarlier<T extends { id: string }>(items: T[], latest: CreatedRef[]): (T & { earlier?: boolean })[] {
  const now = new Set(latest.map((c) => c.id));
  return items.map((x) => (now.has(x.id) ? { ...x } : { ...x, earlier: true }));
}

export function inOrder<T extends { kind: OutputKind }>(xs: T[]): T[] {
  return [...xs].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));
}

export function canRetry(c: BuildCard): boolean {
  return toRetry([c]).length > 0;
}

/** The spinner's words while a step runs. */
export function progressLabel(c: BuildCard): string {
  if (c.progress?.state === "waiting_capacity") return "Waiting for capacity…";
  if (c.progress?.state === "pending_fabric") return "Still running in Fabric…";
  return "Creating in Fabric…";
}
