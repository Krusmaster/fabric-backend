/**
 * n184, the founder's live Create of 9 November 2026 (package 1.0.913, all nine outputs created): what Create says while
 * it runs and when it is done. Pure functions, no React, so createWords.test.ts runs them.
 *
 * - While it runs, Builder's line counts what has happened so far ("4 of 9 created, 1 creating, 4 waiting"), never
 *   "Nothing was created" while outputs are still being made.
 * - Each card has a state: created (green), created with a step still to do (amber), failed (red), waiting for a choice.
 * - When every chosen output is done: a banner ("Done: 9 of 9 created in demo", or "Done with problems: ..."), a short
 *   Next list and how to keep it up to date. The summary is kept in outputs.json (last_create), so reopening the item
 *   shows the same finish with the date of the last Create.
 */
import { scheduleWords } from "./jobsWords";
import { CreatedItem } from "./ModelItemDefinition";
import { BuildCard, OutputKind } from "./engineClient";
import { kindInfo } from "./buildWords";

// ------------------------------------------------------------------ a card's state ------------------------------------

export type CardState = "waiting" | "creating" | "created" | "todo" | "failed" | "choose" | "lost";

/** green, amber, red: the mark left of a card's title once Create has answered for it */
export const STATE_MARK: Record<CardState, { tone: "success" | "warning" | "danger" | "neutral"; label: string }> = {
  waiting: { tone: "neutral", label: "Waiting" },
  creating: { tone: "neutral", label: "Creating" },
  created: { tone: "success", label: "Created" },
  todo: { tone: "warning", label: "Created, still to do" },
  failed: { tone: "danger", label: "Failed" },
  choose: { tone: "warning", label: "Waiting for your choice" },
  lost: { tone: "warning", label: "No answer yet" },
};

const REFRESH_PENDING = ["failed", "not_run", "refreshing"];

/** The state of a Create card; undefined for a dry run's card (nothing was written, nothing to mark). */
export function cardState(c: BuildCard): CardState | undefined {
  if (c.status === "waiting") return "waiting";
  if (c.status === "running") return "creating";
  if (c.status === "lost") return "lost";
  if (c.dry_run) return undefined;
  if (c.built_from && c.choices?.length) return "choose";
  if (c.refusal || c.answer?.error) return "failed";
  if (c.already_built) return "created";
  if (stillToDo(c)) return "todo";
  return "created";
}

/** Created, but the item needs one more step before it works: the App's pages (package and commands), a model Create
 * could not refresh, a report on such a model. Running the notebooks or the pipeline is in Next, for every Create. */
export function stillToDo(c: BuildCard): boolean {
  if (c.output === "rayfin_app") return true;
  if (c.output === "semantic_model") return REFRESH_PENDING.includes(c.refresh?.status ?? "");
  if (c.output === "report") return (c.portal_steps ?? []).some((s) => s.startsWith("If the model was just created, refresh it once"));
  return false;
}

export function reasonOf(c: BuildCard): string | undefined {
  const r = c.refusal ?? (c.answer?.error ? c.answer : undefined);
  if (r) return [r.error, r.hint].filter(Boolean).join(" ");
  if (c.built_from && c.choices?.length) return `${c.built_from.words}: choose Update or a new name on its card.`;
  if (c.status === "lost") return "no answer yet; it may still be running in Fabric.";
  if (c.output === "rayfin_app") return "its pages and connector come from the package and the commands on its card.";
  if (c.output === "semantic_model" && c.refresh && REFRESH_PENDING.includes(c.refresh.status))
    return `not refreshed yet${c.refresh.reason ? ` (${c.refresh.reason})` : ""}: refresh it once in Fabric.`;
  if (c.output === "report" && stillToDo(c)) return "refresh its semantic model once before you open it.";
  return undefined;
}

// ------------------------------------------------------------------ (a) while Create runs ----------------------------

export interface Counts {
  total: number;
  created: number;
  todo: number;
  creating: number;
  waiting: number;
  failed: number;
  choose: number;
  lost: number;
}

export function countStates(cards: BuildCard[]): Counts {
  const n: Counts = { total: cards.length, created: 0, todo: 0, creating: 0, waiting: 0, failed: 0, choose: 0, lost: 0 };
  for (const c of cards) {
    const s = cardState(c);
    if (s) n[s] += 1;
  }
  return n;
}

export function running(cards: BuildCard[]): boolean {
  return cards.some((c) => c.status === "waiting" || c.status === "running");
}

/** Builder's line while Create runs: "4 of 9 created, 1 creating, 4 waiting" (and failed ones, as they come). */
export function progressLine(cards: BuildCard[]): string {
  const n = countStates(cards);
  const parts = [`${n.created + n.todo} of ${n.total} created`];
  if (n.creating) parts.push(`${n.creating} creating`);
  if (n.waiting) parts.push(`${n.waiting} waiting`);
  if (n.failed) parts.push(`${n.failed} failed`);
  if (n.choose) parts.push(`${n.choose} waiting for your choice`);
  if (n.lost) parts.push(`${n.lost} with no answer yet`);
  return parts.join(", ") + ".";
}

// ------------------------------------------------------------------ (b) the item's own type ---------------------------

const TYPE_LABEL: Record<string, string> = {
  Notebook: "Notebook",
  DataPipeline: "Pipeline",
  SemanticModel: "Semantic model",
  Report: "Report",
  GraphQLApi: "API for GraphQL",
  Ontology: "Ontology",
  DataAgent: "Data agent",
  AppBackend: "App",
};

/** The word for an item's own Fabric type: the pipeline's output holds notebooks too, which are notebooks. */
export function itemTypeLabel(type: string, output?: string): string {
  return TYPE_LABEL[type] ?? kindInfo(output ?? "")?.label ?? type;
}

// ------------------------------------------------------------------ (d) the report's visuals -------------------------

interface ReportAnswer {
  visuals?: { type: string; title?: string }[];
  not_drawn?: { visual?: string; measure?: string; why: string }[];
  bound_to?: { semantic_model?: string };
}

/** The visuals of the report's page as both cards count them: charts, cards, the table and slicers; the page's title
 * and footnote text boxes are not counted. */
export function visualCount(r: ReportAnswer | undefined): number {
  return (r?.visuals ?? []).filter((v) => v.type !== "textbox").length;
}

const VISUAL_WORD: Record<string, string> = {
  card: "a card", clusteredColumnChart: "the chart by month", clusteredBarChart: "the bar chart", tableEx: "the table", slicer: "a slicer",
};

export function reportFacts(c: BuildCard): string[] {
  const r = (c.answer?.report ?? {}) as ReportAnswer;
  const n = visualCount(r);
  const on = r.bound_to?.semantic_model ? ` on ${r.bound_to.semantic_model}` : "";
  const out = [`One page with ${n} visual${n === 1 ? "" : "s"}${on}, plus its title and footnote`];
  const before = c.dry_run_visuals;
  if (!c.dry_run && typeof before === "number" && before !== n) {
    out.push(
      `The dry run drew ${before} from this build's draft of the semantic model; Create drew ${n} from the model as Fabric ` +
        "returned it after creating it. What was not drawn, and why:"
    );
  }
  for (const x of r.not_drawn ?? []) out.push(`Not drawn: ${VISUAL_WORD[x.visual ?? ""] ?? x.visual ?? x.measure}: ${x.why}`);
  return out;
}

// ------------------------------------------------------------------ (f) the App ---------------------------------------

export const APP_STEPS_TITLE = "Still to do (in a terminal with Node, e.g. Azure Cloud Shell)";
export const PORTAL_STEPS_TITLE = "Still to do in the Fabric portal";

export function stepsTitle(kind: OutputKind): string {
  return kind === "rayfin_app" ? APP_STEPS_TITLE : PORTAL_STEPS_TITLE;
}

export function appFacts(c: BuildCard): string[] {
  if (c.answer?.error || c.refusal) return [];
  return c.dry_run
    ? ["Create makes an empty App item; its pages and connector come from the package and commands below."]
    : ["Empty App item created; its pages and connector come from the package and commands below."];
}

// ------------------------------------------------------------------ Addition 2: the finish ----------------------------

export interface FinishedOutput {
  output: OutputKind;
  label: string;
  name: string;
  state: CardState;
  reason?: string;
  /** the semantic model's refresh, so Next can say whether it needs one */
  refresh?: string;
  /** n185: the pipeline run Create started (Running, Succeeded, Failed), so Next drops "run the pipeline" once it ran */
  run?: string;
  /** n185: the pipeline's schedule, in words ("daily at 06:00 Europe/Stockholm"), when Create set one */
  schedule?: string;
  /** n185: the data agent was published in Fabric */
  published?: boolean;
}

/** What outputs.json keeps of the last Create (n184), so reopening the item shows the same finish. */
export interface LastCreate {
  at: string;
  item: string;
  outputs: FinishedOutput[];
}

function entry(c: BuildCard): FinishedOutput {
  const reason = reasonOf(c);
  return {
    output: c.output,
    label: c.label,
    name: c.name,
    state: cardState(c) ?? "created",
    ...(reason ? { reason } : {}),
    ...(c.refresh?.status ? { refresh: c.refresh.status } : {}),
    ...(c.jobs?.run?.status ? { run: c.jobs.run.status } : {}),
    ...(c.jobs?.schedule_result?.status === "Succeeded" && c.jobs.schedule ? { schedule: scheduleWords(c.jobs.schedule) } : {}),
    ...(c.agent?.published ? { published: true } : {}),
  };
}

/** n185: the stored finish with the pipeline run's end (read after Create) and, when the agent was sent again, its state. */
export function withRunEnd(lc: LastCreate | undefined, run: string, published?: boolean): LastCreate | undefined {
  if (!lc) return lc;
  return { ...lc, outputs: lc.outputs.map((o) => (o.output === "pipeline" ? { ...o, run }
    : o.output === "data_agent" && published !== undefined ? { ...o, published } : o)) };
}

export function lastCreateOf(cards: BuildCard[], item: string, at: string): LastCreate {
  return { at, item, outputs: cards.map(entry) };
}

/** After an Update (n180) on one card: that output's line of the stored finish, once the update has written (its dry
 * run changes nothing), with the date of that write. */
export function withCard(lc: LastCreate | undefined, c: BuildCard, at: string): LastCreate | undefined {
  const s = cardState(c);
  if (!lc || !s || s === "waiting" || s === "creating") return lc;
  return { ...lc, at, outputs: lc.outputs.map((o) => (o.output === c.output ? entry(c) : o)) };
}

/** Reads a stored last_create, or undefined when it is missing or not of this shape. */
export function readLastCreate(x: unknown): LastCreate | undefined {
  const v = x as LastCreate;
  if (!v || typeof v !== "object" || typeof v.at !== "string" || !Array.isArray(v.outputs)) return undefined;
  if (!v.outputs.every((o) => o && typeof o.output === "string" && typeof o.name === "string" && o.state in STATE_MARK)) return undefined;
  return { at: v.at, item: String(v.item ?? ""), outputs: v.outputs };
}

export interface Banner {
  tone: "success" | "warning" | "danger";
  title: string;
  /** one line per output that failed, waits for a choice or still needs a step */
  reasons: string[];
  when: string;
  glad: boolean;
}

/** "9 November 2026, 19:20" in the person's own time zone (the editor runs in their browser). */
export function whenWords(at: string, timeZone?: string): string {
  const d = new Date(at);
  if (isNaN(d.getTime())) return at;
  const day = d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone });
  return `${day}, ${time}`;
}

export function banner(lc: LastCreate, timeZone?: string): Banner {
  const count = (s: CardState[]) => lc.outputs.filter((o) => s.includes(o.state)).length;
  const total = lc.outputs.length;
  const made = count(["created", "todo"]);
  const failed = count(["failed"]);
  const choose = count(["choose"]);
  const lost = count(["lost"]);
  const todo = count(["todo"]);
  const where = lc.item ? ` in ${lc.item}` : "";
  const reasons = lc.outputs
    .filter((o) => o.state !== "created" && o.reason)
    .map((o) => `${o.label} ${o.name}: ${o.reason}`);
  const when = `Last Create: ${whenWords(lc.at, timeZone)}.`;
  if (!failed && !choose && !lost) {
    return {
      tone: "success",
      title: `Done: ${made} of ${total} created${where}` + (todo ? `; ${todo} still need${todo === 1 ? "s" : ""} a step (below)` : ""),
      reasons, when, glad: true,
    };
  }
  const parts = [`${made} of ${total} created`];
  if (failed) parts.push(`${failed} failed`);
  if (choose) parts.push(`${choose} waiting for your choice`);
  if (lost) parts.push(`${lost} with no answer yet`);
  return { tone: failed ? "danger" : "warning", title: `Done with problems: ${parts.join(", ")}`, reasons, when, glad: false };
}

/** The Next list: what the person does now, in plain words, only for what this Create made. */
export function nextSteps(lc: LastCreate): string[] {
  const made = (k: OutputKind) => lc.outputs.find((o) => o.output === k && (o.state === "created" || o.state === "todo"));
  const out: string[] = [];
  const pipe = made("pipeline");
  const silver = made("silver_notebook");
  const gold = made("gold_views");
  if (pipe && pipe.run === "Running") out.push(`Follow the run of ${pipe.name} in Fabric (the link on its card); Krusgraph started it.`);
  else if (pipe && pipe.run === "Failed") out.push(`The run of ${pipe.name} failed: see its card for the step and why, fix it, and run it again in Fabric.`);
  else if (pipe && pipe.run !== "Succeeded") out.push(`Run the pipeline ${pipe.name} once to fill the silver and gold tables; nothing has run yet.`);
  else if (silver) out.push(`Run the notebook ${silver.name}${gold ? `, then ${gold.name},` : ""} to fill the silver${gold ? " and gold" : ""} tables; nothing has run yet.`);
  else if (gold) out.push(`Run the notebook ${gold.name} once the silver tables are filled.`);
  const model = made("semantic_model");
  if (model && REFRESH_PENDING.includes(model.refresh ?? "")) out.push(`Refresh the semantic model ${model.name} once in Fabric.`);
  const report = made("report");
  if (report) out.push(`Open the report ${report.name}: its page reads the semantic model${pipe || silver ? " (after the run, with the new rows)" : ""}.`);
  const api = made("graphql");
  if (api) out.push(`Try the API for GraphQL ${api.name} in its query editor in Fabric.`);
  const onto = made("ontology");
  if (onto) out.push(`Review the ontology ${onto.name} in Fabric.`);
  const agent = made("data_agent");
  if (agent && agent.published) out.push(`Ask the data agent ${agent.name} a few questions: it is published, so people with access to the workspace can use it.`);
  else if (agent) out.push(`Ask the data agent ${agent.name} a few questions, and publish it in Fabric when its answers are right (it is an unpublished draft).`);
  const app = made("rayfin_app");
  if (app) out.push(`Publish the App ${app.name}: download the package on its card and run its commands in a terminal with Node (e.g. Azure Cloud Shell).`);
  if (lc.outputs.some((o) => o.state === "choose")) out.push("Choose Update or a new name on the cards that ask for it.");
  if (lc.outputs.some((o) => o.state === "failed" || o.state === "lost"))
    out.push("Fix what the red cards say, then choose Create again: what is already built is skipped.");
  return out;
}

export const KEEP_UP_TO_DATE: string[] = [
  "When the data changes: the pipeline's schedule runs it (tick Schedule on the pipeline card, or add one in Fabric), " +
    "or run it yourself. The semantic model is Direct Lake, so it reads the new rows of the gold and silver tables " +
    "without being built again.",
  "When tables or columns change, open this Krusgraph Model item again and choose “Check against the rows again”. " +
    "Create then shows what is out of date, with Update or a new name on each card.",
];

/** n185: Keep it up to date for this finish: the first line names the schedule Create set, when there is one. */
export function keepUpToDate(lc: LastCreate | undefined): string[] {
  const pipe = lc?.outputs.find((o) => o.output === "pipeline");
  if (!pipe?.schedule) return KEEP_UP_TO_DATE;
  return [`When the data changes: the pipeline ${pipe.name} runs on its schedule, ${pipe.schedule}. The semantic model is ` +
    "Direct Lake, so it reads the new rows of the gold and silver tables without being built again.", KEEP_UP_TO_DATE[1]];
}

/** The Create cards a finish is drawn from: the live run's, else none (the stored summary stands in). */
export function finishedOf(cards: BuildCard[], item: string, at: string): LastCreate | undefined {
  if (!cards.length || running(cards)) return undefined;
  return lastCreateOf(cards, item, at);
}

/** For the product list and the Open links: an item's label by its own type. */
export function createdLabel(c: CreatedItem): string {
  return itemTypeLabel(c.type, c.output);
}

/** The marks' colours (Fluent's status tokens) and the finish's cheer. The mascots hop only for a person whose system
 * allows motion: the animation is inside prefers-reduced-motion: no-preference, so "reduce" leaves them still (the
 * celebrate pose and its confetti stay, without movement). With the mascots off, no figure is drawn at all. */
export const FINISH_CSS = `
.krusgraph-mark { display: inline-flex; vertical-align: middle; margin-left: 6px }
.krusgraph-mark-success { color: var(--colorStatusSuccessForeground1, #107c10) }
.krusgraph-mark-warning { color: var(--colorStatusWarningForeground1, #bc4b09) }
.krusgraph-mark-danger { color: var(--colorStatusDangerForeground1, #c50f1f) }
.krusgraph-finish { display: grid; gap: 8px; margin-bottom: 8px }
@media (prefers-reduced-motion: no-preference) {
  .krusgraph-cheer .krusgraph-fig { animation: krusgraph-hop 0.9s ease-out 2 }
  @keyframes krusgraph-hop { 0%, 100% { transform: translateY(0) } 40% { transform: translateY(-6px) } }
}
`;
