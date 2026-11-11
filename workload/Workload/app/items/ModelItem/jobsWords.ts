/**
 * n185: the pipeline's Run once and Schedule, and the data agent's layer, Publish and Microsoft 365 Copilot, in words
 * and as data (fabric_backend/pipeline_jobs.py, agent_publish.py, workload_api._jobs_card / agent_card). Pure functions,
 * no React and no Fabric client, so they run in unit tests (jobsWords.test.ts).
 *
 * All four ticks are off by default: with none ticked, Krusgraph runs nothing, schedules nothing and publishes nothing.
 * The run is started by Create without waiting; the editor reads it (pipelineRun) every POLL_MS for at most
 * MAX_WAIT_MS, so no other card waits. Run ids and schedule ids go into outputs.json (pipeline_jobs) so a later cleanup
 * can remove the schedule.
 */
import { OutputChoice, PipelineJobsRecord } from "./ModelItemDefinition";
import { AgentCard, AgentOptions, BuildCard, CreatedRef, JobsCard, PipelineJobs, PipelineRun, ScheduleChoice } from "./engineClient";

export const POLL_MS = 10_000;
/** n197: a demo pipeline (silver, gold, check) can take a quarter of an hour on a small capacity; the run is followed
 * this long, and a reopened item follows it again */
export const MAX_WAIT_MS = 45 * 60_000;
export const DEFAULT_TIME_ZONE = "Europe/Stockholm";
/** The time zones the engine maps to Fabric's Windows ids (pipeline_jobs.WINDOWS_ZONES). */
export const TIME_ZONES = [
  "Europe/Stockholm", "Europe/Oslo", "Europe/Copenhagen", "Europe/Helsinki", "Europe/Berlin", "Europe/Amsterdam",
  "Europe/Paris", "Europe/London", "UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Tokyo",
  "Australia/Sydney",
];

export const NO_JOBS: PipelineJobs = { run_once: false, schedule: null };
export const NO_AGENT: AgentOptions = { layer: "silver", publish: false, copilot: false };

export function defaultSchedule(): ScheduleChoice {
  return { every: "day", at: "06:00", time_zone: DEFAULT_TIME_ZONE };
}

export function jobsOf(c: OutputChoice | undefined): PipelineJobs {
  return (c?.jobs as PipelineJobs | undefined) ?? NO_JOBS;
}

export function agentOf(c: OutputChoice | undefined): AgentOptions {
  return (c?.agent as AgentOptions | undefined) ?? NO_AGENT;
}

/** What a schedule says before Create: "daily at 06:00 Europe/Stockholm" or "every 4 hours from 06:00 Europe/Stockholm". */
export function scheduleWords(s: ScheduleChoice): string {
  const when = s.every === "day" ? `daily at ${s.at}` : `every ${s.hours ?? 1} hour${(s.hours ?? 1) === 1 ? "" : "s"} from ${s.at}`;
  return `${when} ${s.time_zone}${s.start ? `, from ${s.start}` : ""}`;
}

/** Problems the engine would refuse, said before Preview. */
export function scheduleProblems(s: ScheduleChoice | null, today = new Date()): string[] {
  if (!s) return [];
  const out: string[] = [];
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(s.at)) out.push("Schedule: the time is hh:mm, like 06:00.");
  if (s.every === "hours" && !(Number.isInteger(s.hours) && (s.hours as number) >= 1 && (s.hours as number) <= 24))
    out.push("Schedule: every 1 to 24 hours.");
  if (!TIME_ZONES.includes(s.time_zone)) out.push("Schedule: choose a time zone from the list.");
  if (s.start && s.start < today.toISOString().slice(0, 10)) out.push("Schedule: the start date is in the past; Fabric would start a run at once.");
  return out;
}

/** The permission's refusal from the last dry run, when the sign-in cannot run or schedule pipelines. */
export function jobsBlocked(preview: BuildCard[] | undefined): JobsCard["permission"] | undefined {
  const p = preview?.find((c) => c.output === "pipeline")?.jobs?.permission;
  return p && p.granted === false ? p : undefined;
}

/** One line per activity: "Silver tables: Succeeded, 1m59s". */
export function activityLines(run: PipelineRun | undefined): string[] {
  return (run?.activities ?? []).map((a) => `${a.activity}: ${a.status}${a.duration ? `, ${a.duration}` : ""}${a.error ? ` (${a.error})` : ""}`);
}

export function runFinished(run: PipelineRun | undefined): boolean {
  return !!run && (run.status === "Succeeded" || run.status === "Failed" || run.status === "NotStarted");
}

/** The card's headline for the run. */
export function runHeadline(run: PipelineRun): { tone: "success" | "danger" | "info" | "warning"; text: string } {
  if (run.status === "Succeeded") return { tone: "success", text: `The run succeeded${run.duration ? ` in ${run.duration}` : ""}.` };
  if (run.status === "Failed") return { tone: "danger", text: `The run failed${run.why ? `: ${run.why}` : ""}.` };
  if (run.status === "NotStarted") return { tone: "warning", text: run.why ?? "The run did not start." };
  if (run.fabric_status === "NotStarted") return { tone: "info", text: "Queued in Fabric: the run waits for the capacity to start it." };
  return { tone: "info", text: run.note ?? "The run is going on in Fabric." };
}

/** After MAX_WAIT_MS without an end: said once, with the link. */
export function stillRunning(run: PipelineRun): PipelineRun {
  return { ...run, still_running: true, note: `Still running after ${MAX_WAIT_MS / 60_000} minutes; it goes on in Fabric. Follow it with the link.` };
}

/** The pipeline item of this Create (for the run's reads). */
export function pipelineItem(card: BuildCard | undefined): CreatedRef | undefined {
  return card?.created?.find((c) => c.type === "DataPipeline");
}

/** outputs.json's record with this run added or updated (by run id). */
export function recordRun(rec: PipelineJobsRecord | undefined, pipe: CreatedRef, run: PipelineRun, at: string): PipelineJobsRecord {
  const base = rec ?? { runs: [], schedules: [] };
  if (!run.run_id) return base;
  const entry = { run_id: run.run_id, pipeline_id: pipe.id, pipeline: pipe.name, workspace: pipe.workspace, started: run.started, status: run.status, at };
  return { ...base, runs: [...base.runs.filter((r) => r.run_id !== run.run_id), entry] };
}

/** outputs.json's record with the schedule Create made or updated (one per pipeline: updated in place). */
export function recordSchedule(rec: PipelineJobsRecord | undefined, pipe: CreatedRef, card: BuildCard, at: string): PipelineJobsRecord {
  const base = rec ?? { runs: [], schedules: [] };
  const r = card.jobs?.schedule_result;
  const s = card.jobs?.schedule;
  if (!r || r.status !== "Succeeded" || !r.id) return base;
  const entry = { id: r.id, pipeline_id: pipe.id, pipeline: pipe.name, workspace: pipe.workspace, every: s?.every ?? "day", at: s?.at,
    hours: s?.hours, time_zone: s?.time_zone, start: s?.start, next_run: r.next_run, mode: r.mode, recorded: at };
  return { ...base, schedules: [...base.schedules.filter((x) => x.id !== r.id), entry] };
}

/** The schedule ids this Model made: sent with every Create, so the engine updates them and never adds a second. */
export function scheduleIds(rec: PipelineJobsRecord | undefined): string[] {
  return (rec?.schedules ?? []).map((s) => s.id);
}

/** Whether the data agent should be sent again after the run: the agent was made by this Create and the run ended. */
export function agentAfterRun(cards: BuildCard[], run: PipelineRun): boolean {
  const agent = cards.find((c) => c.output === "data_agent");
  return !!agent?.created?.length && runFinished(run);
}

export const LAYER_LABEL: Record<AgentOptions["layer"], string> = {
  silver: "Silver tables (cleaned, keys and links held)",
  gold: "Gold views (one wide view per fact table)",
  source: "Source tables",
};

/** The Copilot tick is only offered once Publish is ticked; unticking Publish unticks Copilot too. */
export function withPublish(a: AgentOptions, publish: boolean): AgentOptions {
  return { ...a, publish, copilot: publish ? a.copilot : false };
}

/** n197 (item 2): the permissions the run's card uses, listed on the card: only those already granted for Run once. */
export function runPermissionLine(j: JobsCard): string {
  const p = j.permission;
  return `Permissions: starting and reading the run use ${p.scope}${p.or ? ` (or ${p.or})` : ""} on the workload app, the one Run once ` +
    "already needs (Fabric's Job Scheduler API: Run On Demand Item Job, Get Item Job Instance, and the pipeline's activity runs); nothing else.";
}

/** n209: a reason that says Fabric could not connect (workload_api._CONNECT): such an example is not checked yet. */
const CONNECT = /connect|network|timeout|unavailable|transport/i;

export const NOT_CHECKED_LINE = "Example queries: not checked yet.";

/** n209: what the agent card says about its example queries. An example Fabric could not connect for reads "not
 * checked yet" with the reason, never "invalid", also from an engine before n209 that listed it as invalid; only a real
 * query error is invalid. Nothing about validity while the pipeline's run has not succeeded (status not_checked). */
export function exampleWords(ex: AgentCard["examples"]): { lines: string[]; invalid: string[]; notChecked: string[] } {
  if (!ex) return { lines: [], invalid: [], notChecked: [] };
  if (ex.status === "not_checked") return { lines: [ex.words ?? NOT_CHECKED_LINE], invalid: [], notChecked: [] };
  if (ex.status !== "read") return { lines: [], invalid: [], notChecked: [] };
  const listed = ex.invalid_examples ?? [];
  const connect = listed.filter((x) => CONNECT.test(x.reason ?? ""));
  const real = listed.filter((x) => !CONNECT.test(x.reason ?? ""));
  const notChecked = [...(ex.not_checked_examples ?? []), ...connect];
  const invalid = Math.max(0, (ex.invalid ?? listed.length) - connect.length);
  const parts = [`${ex.valid ?? 0} valid`, `${invalid} invalid`, `${ex.validating ?? 0} still being checked`,
    notChecked.length ? `${notChecked.length} not checked yet` : ""].filter(Boolean);
  const lines = [`Examples in Fabric: ${parts.join(", ")}.`];
  if (notChecked.length) {
    lines.push(ex.not_checked_words ?? `Example queries: ${notChecked.length} not checked yet. Fabric could not connect to the tables the `
      + `agent reads (${notChecked[0].reason ?? "could not connect"}); this says nothing about the queries themselves.`);
  }
  if (ex.rechecked) lines.push(`${ex.rechecked} example(s) Fabric could not connect for at first were sent once more.`);
  return {
    lines,
    invalid: real.map((x) => `${x.question}: ${x.reason ?? "invalid"}`),
    notChecked: notChecked.map((x) => `${x.question}: not checked yet${x.reason ? ` (${x.reason})` : ""}`),
  };
}
