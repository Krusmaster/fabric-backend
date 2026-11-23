/**
 * W3 (Gustav's run of 23 November 2026): the data agent card's guidance and its "Make it available in Copilot" step, in
 * words and as data. Pure functions, no React (w3Copilot.test.tsx). The step calls POST /workload/v1/agent-publish
 * (workload_api.run_agent_publish, which reuses agent_publish.py): a dry run that shows what Microsoft requires and what
 * would be done, then publishing in Fabric only after the person ticks and chooses Publish as me. Publish to Agent Store
 * (Microsoft 365 Copilot) has no documented API: it stays the person's step in Fabric, said plainly.
 */
import type { BuildCard, CopilotRequirement, CreatedRef, PipelineRun } from "./engineClient";
import { Offer } from "./afterRun";
import { agentReady } from "./cheer";

export const COPILOT_BUTTON = "Make it available in Copilot";
export const PUBLISH_BUTTON = "Publish as me";

/** The engine's answer (workload_api.run_agent_publish). */
export interface CopilotAnswer {
  name: string;
  workspace: string;
  agent_id: string;
  requirements: CopilotRequirement[];
  missing: number;
  unverified: number;
  preflight_words: string;
  plan: { step: string; by: string; how: string; scope: string | null }[];
  copilot_step: string;
  published: boolean;
  confirm?: string | null;
  words?: string;
  note?: string;
}

/** The data agent item the card made (its id, name and workspace), if any. */
export function agentItem(card: BuildCard | undefined): CreatedRef | undefined {
  const made = card?.created ?? [];
  return made.find((c) => c.type === "DataAgent") ?? made[0];
}

/**
 * Thinker, when the agent this Create made has no tables selected: what to do, with the real count and layer. Nothing
 * while the pipeline's run has not succeeded (the card already says the tables are selected after it).
 */
export function agentNoTablesLine(card: BuildCard | undefined, offer: Offer, run?: PipelineRun): string | undefined {
  const sel = card?.agent?.selection;
  if (!card || card.output !== "data_agent" || card.dry_run || !card.created?.length || !sel || sel.selected !== 0) return undefined;
  if (sel.layer === "source" || (run && run.status !== "Succeeded")) return undefined;
  const total = sel.total ?? (sel.missing?.length || undefined);
  const what = total ? `the ${total} ${sel.layer} table${total === 1 ? "" : "s"}` : `the ${sel.layer} tables`;
  const skip = sel.layer === "silver" ? " (not krusgraph_quarantine)" : "";
  return offer.offer
    ? `The agent has no tables yet. Choose Select tables now, or tick ${what} in the agent${skip}.`
    : `The agent has no tables yet. Tick ${what} in the agent in Fabric${skip}.`;
}

/** Builder, once the agent has its tables and valid examples: publish it, then Microsoft 365 Copilot. */
export function publishAdvice(card: BuildCard | undefined): string | undefined {
  if (!agentReady(card)) return undefined;
  const name = agentItem(card)?.name ?? "the agent";
  const first = card!.agent?.published ? `${name} is published in Fabric. Next: make it available in Microsoft 365 Copilot.`
    : `Next: publish ${name}, then make it available in Microsoft 365 Copilot.`;
  return `${first} ${COPILOT_BUTTON} shows what Microsoft requires and what would be done; nothing is published until you choose.`;
}

/** One requirement as a line: its state in a word, what it is, and what was found. */
export function requirementLine(r: CopilotRequirement): string {
  const st = r.status === "ok" ? "OK" : r.status === "missing" ? "Missing" : "Unverified";
  return `${st}: ${r.requirement} (${r.detail}).`;
}

/** The steps in order, with who does each. */
export function planLines(a: CopilotAnswer): string[] {
  return a.plan.map((p, i) => `${i + 1}. ${p.step}. ${p.by === "Krusgraph, as you" ? "Krusgraph does it, as you" : "You do it, in Fabric"}: ${p.how.replace(/\.$/, "")}.`);
}

/** The Publish as me button's state and the words beside it while it cannot be used. */
export function publishGate(a: CopilotAnswer | undefined, ticked: boolean): { ok: boolean; why: string } {
  if (!a) return { ok: false, why: `Choose ${COPILOT_BUTTON} first: you see what is needed and what would be done before anything is.` };
  if (a.published) return { ok: false, why: "Published already." };
  if (!a.confirm) return { ok: false, why: "Nothing for Krusgraph to publish." };
  if (!ticked) return { ok: false, why: `Tick that you want Krusgraph to publish ${a.name} in Fabric.` };
  return { ok: true, why: "" };
}

/** After publishing: what was done, and the last step, the person's own. */
export function publishedLines(a: CopilotAnswer): string[] {
  return [a.words ?? `Published ${a.name} in Fabric.`, `Last step, yours: ${a.copilot_step}`];
}

/** The request body of the step (dry run, or the publish with the dry run's confirm). */
export function publishBody(card: BuildCard, source: string | undefined, dryRun: boolean, confirm?: string | null): object | undefined {
  const it = agentItem(card);
  if (!it?.id || !it.workspace) return undefined;
  return { workspace: it.workspace, agent_id: it.id, name: it.name, ...(source ? { source_name: source } : {}), dry_run: dryRun,
    confirm: dryRun ? null : confirm ?? null };
}
