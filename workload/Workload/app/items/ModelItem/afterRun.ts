/**
 * W2 (Gustav's Create of 23 November 2026 in another workspace than the source). Pure functions, no React and no Fabric
 * client (afterRun.test.ts):
 *
 * - the data agent's tables: at Create the pipeline has not written the silver tables yet, so none can be selected; after
 *   the run the engine waits a bounded while for the lakehouse's SQL analytics endpoint to list them (data_agent.
 *   TABLE_WAITS). When it still has not, the agent card offers "Select tables now", at most MAX_SELECT_TRIES times
 *   (selectTablesOffer); never a loop.
 * - the semantic model's refresh: it waits for the pipeline's run (workload_api._runs_first); when it failed or did not
 *   run, the card offers "Refresh now" (refreshOffer), which sends the same refresh_only step the run's success sends.
 */
import type { BuildCard, PipelineRun } from "./engineClient";

export const MAX_SELECT_TRIES = 3;
export const SELECT_TABLES_LABEL = "Select tables now";
export const REFRESH_NOW_LABEL = "Refresh now";

export interface Offer {
  offer: boolean;
  label: string;
  /** one line under the button, or why there is none */
  line?: string;
}

/** The agent's tables that are not selected: what the engine says is missing, else the count's difference. */
export function tablesNotSelected(card: BuildCard | undefined): number {
  const s = card?.agent?.selection;
  if (!s || s.selected === null || s.selected === undefined) return 0;
  const total = s.total ?? (s.missing ? s.selected + s.missing.length : s.selected);
  return Math.max(0, total - s.selected);
}

/** "Select tables now" on a created data agent's card whose tables are not all selected, `tries` times at most. Only
 * after the pipeline's run succeeded when this Create ran it (the tables exist only then). */
export function selectTablesOffer(card: BuildCard | undefined, tries: number, run?: PipelineRun): Offer {
  const label = SELECT_TABLES_LABEL;
  if (!card || card.output !== "data_agent" || card.dry_run || !card.created?.length || card.agent?.selection?.layer === "source") {
    return { offer: false, label };
  }
  const left = tablesNotSelected(card);
  if (!left) return { offer: false, label };
  if (run && run.status !== "Succeeded") {
    return { offer: false, label, line: "The tables are selected once the pipeline's run has succeeded." };
  }
  if (tries >= MAX_SELECT_TRIES) {
    return { offer: false, label, line: `Tried ${tries} times: select the tables in the agent in Fabric (Explorer, tick the tables), `
      + "or open the lakehouse's SQL analytics endpoint and choose Refresh, then try again later." };
  }
  return { offer: true, label, line: `${left} table${left === 1 ? "" : "s"} not selected yet: Fabric's SQL analytics endpoint lists new `
    + "tables some time after the run writes them. Krusgraph selects them by name once it does." };
}

/** "Refresh now" on a semantic model this Create made whose refresh failed or did not run. */
export function refreshOffer(card: BuildCard | undefined, run?: PipelineRun): Offer {
  const label = REFRESH_NOW_LABEL;
  if (!card || card.output !== "semantic_model" || card.dry_run || !card.created?.length) return { offer: false, label };
  const st = card.refresh?.status;
  if (st === "planned") {
    return { offer: false, label, line: run && run.status !== "Succeeded" && run.status !== "Running"
      ? "Not refreshed: the pipeline's run did not succeed." : "Refreshed after the pipeline's run has succeeded." };
  }
  if (st !== "failed" && st !== "not_run") return { offer: false, label };
  if (run && run.status === "Running") return { offer: false, label, line: "Refreshed after the pipeline's run has succeeded." };
  return { offer: true, label };
}

/** The request extra of "Select tables now": the run's end when known, so the engine treats the tables as written. */
export function selectTablesExtra(run?: PipelineRun): { select_tables: true; after_run?: { status: string } } {
  return { select_tables: true, ...(run?.status ? { after_run: { status: run.status } } : {}) };
}
