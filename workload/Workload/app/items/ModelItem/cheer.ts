/**
 * W3 (Gustav's run of 23 November 2026 in a real tenant): the happy mascot line at three milestones, kept rare. Pure
 * functions, no React (w3Cheer.test.tsx):
 *
 * - catalog_written: "Publish to OneLake catalog" wrote every description it showed;
 * - pipeline_succeeded: the pipeline's run that Create started succeeded;
 * - agent_ready: the data agent this Create made has its tables selected and its example queries are valid.
 *
 * One line each, Onto in the celebrate pose (MASCOT_GLAD), and no repeats: a milestone cheers once per Create
 * (outputs.json `cheered` keeps which ones did, so reopening the item does not cheer again). The "Mascots: on/off"
 * toggle decides whether a figure is drawn at all.
 */
import type { BuildCard, PipelineRun } from "./engineClient";
import { tablesNotSelected } from "./afterRun";

export type Milestone = "catalog_written" | "pipeline_succeeded" | "agent_ready";
export const MILESTONES: Milestone[] = ["catalog_written", "pipeline_succeeded", "agent_ready"];

/** outputs.json's record: the Create (create_run id) and the milestones it has cheered. */
export interface CheeredRecord {
  create: string;
  said: Milestone[];
}

/** outputs.json's `cheered`, read safely: only known milestones, only with a Create id. */
export function readCheered(x: unknown): CheeredRecord | undefined {
  const r = x as CheeredRecord | undefined;
  if (!r || typeof r !== "object" || typeof r.create !== "string" || !Array.isArray(r.said)) return undefined;
  return { create: r.create, said: r.said.filter((m): m is Milestone => MILESTONES.includes(m as Milestone)) };
}

/** Whether `m` has cheered already in Create `create` (a record of another Create says nothing about this one). */
export function cheeredBefore(rec: CheeredRecord | undefined, create: string, m: Milestone): boolean {
  return !!rec && rec.create === create && rec.said.includes(m);
}

/** The record with `m` added for Create `create` (a new Create starts a new record). */
export function withCheer(rec: CheeredRecord | undefined, create: string, m: Milestone): CheeredRecord {
  const said = rec && rec.create === create ? rec.said : [];
  return { create, said: said.includes(m) ? said : [...said, m] };
}

/**
 * The cheers of this editor session. A milestone shown here stays shown where it was first claimed (a re-render, or
 * React's double render, claims it again for the same place); another place, or a milestone outputs.json says was
 * cheered in this Create already, gets nothing.
 */
export class CheerBook {
  private places = new Map<string, string>();

  claim(m: Milestone, create: string, place: string, before?: CheeredRecord): boolean {
    const key = `${create}:${m}`;
    const had = this.places.get(key);
    if (had !== undefined) return had === place;
    if (cheeredBefore(before, create, m)) return false;
    this.places.set(key, place);
    return true;
  }
}

// ------------------------------------------------------------------ the words ------------------------------------

/** "Done! 6 descriptions are in the OneLake catalog. ..." after a write where every description went through. */
export function catalogCheer(results: { field: string; ok: boolean }[] | undefined): string | undefined {
  const desc = (results ?? []).filter((r) => r.field === "description");
  if (!results?.length || results.some((r) => !r.ok) || !desc.length) return undefined;
  return `Done! ${desc.length} description${desc.length === 1 ? " is" : "s are"} in the OneLake catalog. People can now find this ` +
    "data product, with the row-check evidence next to it.";
}

export const PIPELINE_CHEER = "The pipeline's run succeeded: silver and gold are filled with real rows.";

/** The pipeline card's run, started by this Create, that succeeded. */
export function pipelineCheer(card: Pick<BuildCard, "output" | "dry_run"> & { jobs?: { run?: PipelineRun } }): string | undefined {
  if (card.output !== "pipeline" || card.dry_run) return undefined;
  return card.jobs?.run?.status === "Succeeded" && card.jobs.run.run_id ? PIPELINE_CHEER : undefined;
}

/** The agent's example queries all valid: read from Fabric, at least one valid, none invalid, none still checked or
 * not checked yet. */
export function examplesValid(card: BuildCard | undefined): boolean {
  const ex = card?.agent?.examples;
  return !!ex && ex.status === "read" && (ex.valid ?? 0) > 0 && (ex.invalid ?? 0) === 0 && (ex.validating ?? 0) === 0
    && !(ex.not_checked ?? 0) && !(ex.not_checked_examples?.length) && !(ex.invalid_examples?.length);
}

/** A data agent this Create made, with every table of its layer selected and valid example queries. */
export function agentReady(card: BuildCard | undefined): boolean {
  const s = card?.agent?.selection;
  if (!card || card.output !== "data_agent" || card.dry_run || !card.created?.length || !s) return false;
  return (s.selected ?? 0) > 0 && tablesNotSelected(card) === 0 && examplesValid(card);
}

export function agentCheer(card: BuildCard | undefined): string | undefined {
  if (!agentReady(card)) return undefined;
  const s = card!.agent!.selection!;
  const n = card!.agent!.examples!.valid ?? 0;
  return `The agent is ready: ${s.selected} ${s.layer} table${s.selected === 1 ? "" : "s"} selected and ${n} valid example ` +
    `quer${n === 1 ? "y" : "ies"}.`;
}
