// n185: Run once and Schedule on the pipeline, and the data agent's layer, Publish and Microsoft 365 Copilot, in the
// editor: off by default, sent with Create, shown on the cards, kept in outputs.json, and the Next list after the run.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BuildCard, CreatedRef, JobsCard, OutputKind, PipelineRun } from "./engineClient";
import {
  NOT_CHECKED_LINE, exampleWords, NO_AGENT, NO_JOBS, activityLines, agentAfterRun, agentOf, defaultSchedule, jobsBlocked, jobsOf, recordRun, recordSchedule,
  runFinished, runHeadline, scheduleIds, scheduleProblems, scheduleWords, stillRunning, withPublish,
} from "./jobsWords";
import { toRequests } from "./buildWords";
import { keepUpToDate, lastCreateOf, nextSteps, withRunEnd } from "./createWords";
import { emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";
import { OutputCard, OutputsView } from "./ModelItemViews";

const WS = "11111111-1111-1111-1111-111111111111";
const PIPE: CreatedRef = { type: "DataPipeline", id: "pl-1", name: "demo_lh_pipeline", workspace: WS, output: "pipeline" };
const GRANTED: JobsCard["permission"] = { granted: true, scope: "DataPipeline.Execute.All", or: "Item.Execute.All" };
const REFUSED: JobsCard["permission"] = {
  granted: false, scope: "DataPipeline.Execute.All", or: "Item.Execute.All",
  why: "Your sign-in does not carry DataPipeline.Execute.All, which running and scheduling a pipeline need; Krusgraph builds the pipeline and runs or schedules nothing.",
  entra_steps: ["Entra admin centre …", "Tick DataPipeline.Execute.All → Add permissions."],
  az: "az ad app permission add --id 853a0cf0-7d35-42b7-b384-26178755a72a --api 00000009-0000-0000-c000-000000000000 --api-permissions …",
  consent_note: "Grant admin consent in the Entra portal (App registrations -> the workload app -> API permissions -> Grant admin consent): `az ad app permission admin-consent` fails in Cloud Shell.",
  manual: ["Run it once: open the pipeline in Fabric and choose Run.", "Run it regularly: on the pipeline choose Schedule."],
};
const SUCCEEDED: PipelineRun = {
  status: "Succeeded", run_id: "run-1", duration: "4m12s", links: { run: "https://app.fabric.microsoft.com/run-1" },
  activities: [{ activity: "Silver tables", status: "Succeeded", duration: "1m59s" }, { activity: "Gold views", status: "Succeeded", duration: "1m01s" },
    { activity: "Check keys, orphans and sums", status: "Succeeded", duration: "32s" }],
};

function card(kind: OutputKind, extra: Partial<BuildCard> = {}): BuildCard {
  return {
    output: kind, label: kind === "pipeline" ? "Pipeline" : "Data agent", type: "", name: kind === "pipeline" ? "demo_lh_pipeline" : "demo_lh_agent",
    dry_run: false, would: "create", updates_in_place: true, permissions: { needs: [], missing: null, execute: "" }, status: "done", answer: {},
    created: [kind === "pipeline" ? PIPE : { type: "DataAgent", id: "da-1", name: "demo_lh_agent", workspace: WS, output: "data_agent" }], ...extra,
  };
}

describe("off by default", () => {
  it("sends no jobs and no agent options until ticked, and the choices start unticked", () => {
    expect(jobsOf(undefined)).toEqual(NO_JOBS);
    expect(NO_JOBS).toEqual({ run_once: false, schedule: null });
    expect(agentOf(undefined)).toEqual({ layer: "silver", publish: false, copilot: false });
    expect(toRequests([{ type: "pipeline", name: "p", enabled: true }, { type: "data_agent", name: "a", enabled: true }]))
      .toEqual([{ kind: "pipeline", name: "p" }, { kind: "data_agent", name: "a" }]);
    const html = renderToStaticMarkup(
      React.createElement(OutputsView, { choices: [{ type: "pipeline", name: "demo_lh_pipeline", enabled: true }, { type: "data_agent", name: "demo_lh_agent", enabled: true }],
        onChange: () => {}, created: [], product: { on: false, name: "" }, onProduct: () => {}, onOpen: () => {}, onPreview: () => {} })
    );
    expect(html).toContain("Run once after Create (silver, then gold, then the check)");
    expect(html).toContain("Publish the agent in Fabric");
    expect(html).toContain("Also make it available in Microsoft 365 Copilot");
    const part = (label: string) => html.slice(html.indexOf(`aria-label="${label}"`), html.indexOf("</fieldset>", html.indexOf(`aria-label="${label}"`)));
    expect(part("Run and schedule")).not.toMatch(/checked=""/);           // Run once and Schedule: unticked
    expect(part("Data agent: layer and publishing").match(/checked=""/g)).toHaveLength(1);   // only the layer (silver); Publish, Copilot unticked
    expect(part("Data agent: layer and publishing")).toMatch(/disabled=""/);                 // Copilot needs Publish
  });

  it("sends what is ticked with Create", () => {
    const jobs = { run_once: true, schedule: defaultSchedule() };
    const agent = { layer: "silver" as const, publish: true, copilot: false };
    expect(toRequests([{ type: "pipeline", name: "p", enabled: true, jobs }, { type: "data_agent", name: "a", enabled: true, agent }]))
      .toEqual([{ kind: "pipeline", name: "p", jobs }, { kind: "data_agent", name: "a", agent }]);
  });
});

describe("the schedule", () => {
  it("defaults to daily at 06:00 Europe/Stockholm and says so", () => {
    expect(scheduleWords(defaultSchedule())).toBe("daily at 06:00 Europe/Stockholm");
    expect(scheduleWords({ every: "hours", hours: 4, at: "06:00", time_zone: "UTC", start: "2026-11-10" })).toBe("every 4 hours from 06:00 UTC, from 2026-11-10");
  });

  it("refuses what Fabric would not take before Preview", () => {
    expect(scheduleProblems({ every: "day", at: "6am", time_zone: "Europe/Stockholm" })).toEqual(["Schedule: the time is hh:mm, like 06:00."]);
    expect(scheduleProblems({ every: "hours", hours: 0, at: "06:00", time_zone: "Europe/Stockholm" })).toEqual(["Schedule: every 1 to 24 hours."]);
    expect(scheduleProblems({ every: "day", at: "06:00", time_zone: "Mars/Olympus" })).toEqual(["Schedule: choose a time zone from the list."]);
    expect(scheduleProblems({ every: "day", at: "06:00", time_zone: "UTC", start: "2026-11-01" }, new Date("2026-11-09T12:00:00Z")))
      .toEqual(["Schedule: the start date is in the past; Fabric would start a run at once."]);
    expect(scheduleProblems(null)).toEqual([]);
  });

  it("records the schedule id, and sends it back so the engine updates it and never adds a second", () => {
    const c = card("pipeline", { jobs: { run_once: false, schedule: defaultSchedule(), permission: GRANTED, words: [],
      schedule_result: { status: "Succeeded", mode: "created", id: "sch-1", next_run: "2026-11-10T06:00:00+01:00" } } });
    let rec = recordSchedule(undefined, PIPE, c, "2026-11-09T20:00:00Z");
    expect(rec.schedules).toEqual([expect.objectContaining({ id: "sch-1", pipeline_id: "pl-1", every: "day", at: "06:00", time_zone: "Europe/Stockholm" })]);
    rec = recordSchedule(rec, PIPE, { ...c, jobs: { ...c.jobs!, schedule_result: { status: "Succeeded", mode: "updated", id: "sch-1" } } }, "2026-11-10T08:00:00Z");
    expect(rec.schedules).toHaveLength(1);
    expect(scheduleIds(rec)).toEqual(["sch-1"]);
  });
});

describe("without DataPipeline.Execute.All", () => {
  it("shows both choices disabled with why, the Entra steps, the Cloud Shell line, the consent note and the manual steps", () => {
    const preview = [card("pipeline", { dry_run: true, jobs: { run_once: false, schedule: null, permission: REFUSED, words: [] } })];
    const blocked = jobsBlocked(preview);
    expect(blocked?.granted).toBe(false);
    const html = renderToStaticMarkup(
      React.createElement(OutputsView, { choices: [{ type: "pipeline", name: "demo_lh_pipeline", enabled: true }], onChange: () => {}, created: [],
        product: { on: false, name: "" }, onProduct: () => {}, onOpen: () => {}, onPreview: () => {}, jobsBlocked: blocked })
    );
    expect(html.match(/disabled=""/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain("az ad app permission add");
    expect(html).toContain("admin-consent` fails in Cloud Shell");
    expect(html).toContain("open the pipeline in Fabric and choose Run");
    expect(jobsBlocked([card("pipeline", { jobs: { run_once: false, schedule: null, permission: GRANTED, words: [] } })])).toBeUndefined();
  });
});

describe("the run on the card", () => {
  it("shows each step with its duration and the link", () => {
    expect(activityLines(SUCCEEDED)).toEqual(["Silver tables: Succeeded, 1m59s", "Gold views: Succeeded, 1m01s", "Check keys, orphans and sums: Succeeded, 32s"]);
    const html = renderToStaticMarkup(React.createElement(OutputCard, { card: card("pipeline", { jobs: { run_once: true, schedule: null, permission: GRANTED,
      words: ["Create starts one run of demo_lh_pipeline: silver, then gold, then the check"], run: SUCCEEDED } }) }));
    expect(html).toContain("The run succeeded in 4m12s.");
    expect(html).toContain("Silver tables: Succeeded, 1m59s");
    expect(html).toContain("Open the run in Fabric");
  });

  it("a failed run says which step and why; one still running at the bound says so with the link", () => {
    const failed: PipelineRun = { status: "Failed", run_id: "r", why: "1 orphan in order_items",
      activities: [{ activity: "Check keys, orphans and sums", status: "Failed", duration: "32s", error: "1 orphan in order_items" }] };
    expect(runHeadline(failed)).toEqual({ tone: "danger", text: "The run failed: 1 orphan in order_items." });
    expect(activityLines(failed)[0]).toBe("Check keys, orphans and sums: Failed, 32s (1 orphan in order_items)");
    const running: PipelineRun = { status: "Running", run_id: "r", links: { run: "https://x" } };
    expect(runFinished(running)).toBe(false);
    const late = stillRunning(running);
    expect(late.note).toBe("Still running after 45 minutes; it goes on in Fabric. Follow it with the link.");
    expect(runHeadline(late).tone).toBe("info");
  });

  it("records the run id in outputs.json, which keeps it across a save", () => {
    const rec = recordRun(undefined, PIPE, SUCCEEDED, "2026-11-09T20:05:00Z");
    expect(rec.runs).toEqual([expect.objectContaining({ run_id: "run-1", pipeline_id: "pl-1", status: "Succeeded" })]);
    const def = emptyDefinition();
    def.outputs.pipeline_jobs = rec;
    expect(fromParts(toParts(def) as never).outputs.pipeline_jobs).toEqual(rec);
  });
});

describe("the Next list and Keep it up to date", () => {
  const finish = (pipeRun?: string, published?: boolean, schedule = false) => {
    const lc = lastCreateOf([card("pipeline", { jobs: { run_once: !!pipeRun, schedule: schedule ? defaultSchedule() : null, permission: GRANTED, words: [],
      ...(pipeRun ? { run: { status: pipeRun as PipelineRun["status"] } } : {}),
      ...(schedule ? { schedule_result: { status: "Succeeded", id: "s" } } : {}) } }),
      card("data_agent", published ? { agent: { layer: "silver", publish: true, copilot: false, where_examples: "", published: true } } : {})],
      "demo", "2026-11-09T20:00:00Z");
    return lc;
  };

  it("drops 'run the pipeline' when the run succeeded, and follows a running one", () => {
    expect(nextSteps(finish()).join(" ")).toContain("Run the pipeline demo_lh_pipeline once");
    expect(nextSteps(finish("Running"))[0]).toBe("Follow the run of demo_lh_pipeline in Fabric (the link on its card); Krusgraph started it.");
    const done = withRunEnd(finish("Running"), "Succeeded", true)!;
    expect(nextSteps(done).join(" ")).not.toContain("Run the pipeline");
    expect(nextSteps(done).join(" ")).toContain("it is published, so people with access to the workspace can use it");
    expect(nextSteps(withRunEnd(finish("Running"), "Failed")!)[0]).toContain("failed");
  });

  it("names the schedule under Keep it up to date, and how to follow a schema change", () => {
    const k = keepUpToDate(finish(undefined, false, true));
    expect(k[0]).toContain("runs on its schedule, daily at 06:00 Europe/Stockholm");
    expect(keepUpToDate(finish())[0]).toContain("the pipeline's schedule runs it (tick Schedule on the pipeline card, or add one in Fabric)");
    expect(k[1]).toContain("open this Krusgraph Model item again and choose “Check against the rows again”");
    expect(k[1]).toContain("Update or a new name");
  });
});

describe("the data agent", () => {
  it("Copilot needs Publish: unticking Publish unticks Copilot", () => {
    expect(withPublish({ layer: "silver", publish: true, copilot: true }, false)).toEqual({ layer: "silver", publish: false, copilot: false });
    expect(NO_AGENT.publish || NO_AGENT.copilot).toBe(false);
  });

  it("is sent again after the run only when this Create made it and the run ended", () => {
    expect(agentAfterRun([card("data_agent")], SUCCEEDED)).toBe(true);
    expect(agentAfterRun([card("data_agent", { created: [] })], SUCCEEDED)).toBe(false);
    expect(agentAfterRun([card("data_agent")], { status: "Running" })).toBe(false);
  });

  it("the card shows the layer, the examples' validation and the Copilot preflight with Microsoft's links", () => {
    const html = renderToStaticMarkup(React.createElement(OutputCard, { card: card("data_agent", { agent: {
      layer: "silver", publish: true, copilot: true, where_examples: "Krusgraph's example questions are the agent's example queries (Example queries pane).",
      selection: { layer: "silver", schema: "silver", selected: 7, deselected: 7, one_layer: true, words: "selected 7 of 7 tables in silver (silver); deselected 7 of the same tables in other layers" },
      examples: { status: "read", count: 3, valid: 2, invalid: 1, validating: 0, invalid_examples: [{ question: "Show orders", reason: "Invalid object name" }] },
      words: ["Published demo_lh_agent in Fabric: people with access to the workspace can use it."], published: true,
      copilot_preflight: { missing: 1, unverified: 2, words: "Missing for Microsoft 365 Copilot: Paid capacity, F2 or higher (or P1 or higher) (the workspace is on a trial capacity (FT1))",
        step: "In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish.",
        requirements: [{ requirement: "Paid capacity, F2 or higher (or P1 or higher)", status: "missing", detail: "trial (FT1)", doc: "https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot" }] },
    } }) }));
    expect(html).toContain("selected 7 of 7 tables in silver");
    expect(html).toContain("Examples in Fabric: 2 valid, 1 invalid, 0 still being checked.");
    expect(html).toContain("Show orders: Invalid object name");
    expect(html).toContain("Missing: Paid capacity, F2 or higher");
    expect(html).toContain("https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot");
    expect(html).toContain("tick Publish to Agent Store");
  });
});

describe("n209: the data agent's examples and the pipeline's run", () => {
  const CONNECT = "Failed to connect to server x1.datawarehouse.fabric.microsoft.com";
  const agentCard = (examples: NonNullable<BuildCard["agent"]>["examples"]) => card("data_agent", { agent: {
    layer: "silver", publish: true, copilot: false, where_examples: "", examples, words: [] } });
  const html = (examples: NonNullable<BuildCard["agent"]>["examples"]) => renderToStaticMarkup(React.createElement(OutputCard, { card: agentCard(examples) }));

  it("before the run succeeded: not checked yet, and nothing about validity", () => {
    const words = "Example queries: not checked yet. Fabric checks them against the tables the agent reads, which the pipeline's run is writing now; Krusgraph checks them when the run has succeeded.";
    const w = exampleWords({ status: "not_checked", count: 4, words });
    expect(w).toEqual({ lines: [words], invalid: [], notChecked: [] });
    const out = html({ status: "not_checked", count: 4, words });
    expect(out).toContain("not checked yet");
    expect(out).not.toMatch(/invalid|valid,/i);
    expect(exampleWords({ status: "not_checked" }).lines).toEqual([NOT_CHECKED_LINE]);
  });

  it("a failure to connect, sent once more and still failing, reads not checked yet with the reason, never invalid", () => {
    const ex = { status: "read", count: 2, valid: 0, invalid: 1, validating: 0, rechecked: 1,
      invalid_examples: [{ question: "Orders per customer?", reason: "Invalid column name 'x'" }],
      not_checked: 1, not_checked_examples: [{ question: "Sales by month?", reason: CONNECT }],
      not_checked_words: `Example queries: 1 not checked yet. Fabric could not connect to the tables the agent reads (${CONNECT}); ...` };
    const w = exampleWords(ex);
    expect(w.lines[0]).toBe("Examples in Fabric: 0 valid, 1 invalid, 0 still being checked, 1 not checked yet.");
    expect(w.notChecked).toEqual([`Sales by month?: not checked yet (${CONNECT})`]);
    expect(w.invalid).toEqual(["Orders per customer?: Invalid column name 'x'"]);    // only a real query error is invalid
    expect(w.lines).toContain("1 example(s) Fabric could not connect for at first were sent once more.");
    const out = html(ex);
    expect(out).toContain(`Sales by month?: not checked yet (${CONNECT})`);
    expect(out).not.toContain("Sales by month?: Failed");
  });

  it("an engine before n209 that listed a failure to connect as invalid: the editor still says not checked yet", () => {
    const w = exampleWords({ status: "read", count: 1, valid: 0, invalid: 1, validating: 0,
      invalid_examples: [{ question: "Sales by month?", reason: CONNECT }] });
    expect(w.invalid).toEqual([]);
    expect(w.lines[0]).toBe("Examples in Fabric: 0 valid, 0 invalid, 0 still being checked, 1 not checked yet.");
    expect(w.notChecked[0]).toContain("not checked yet");
    expect(html({ status: "read", count: 1, valid: 0, invalid: 1, validating: 0, invalid_examples: [{ question: "Sales by month?", reason: CONNECT }] }))
      .not.toContain('aria-label="Invalid examples"');
  });
});
