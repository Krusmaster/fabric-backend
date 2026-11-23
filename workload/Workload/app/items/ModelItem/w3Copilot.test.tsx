// @vitest-environment jsdom
// W3 (Gustav's run of 23 November 2026 in a real tenant): the happy mascot line at three milestones, kept rare, and the
// data agent card's guidance with its "Make it available in Copilot" step.
// - Milestones: the catalog write succeeded; the pipeline's run succeeded after Create; the agent has its tables and its
//   example queries are valid. One line each, Onto celebrating, no repeat per milestone per Create, none with the
//   mascots off.
// - The agent without tables: Thinker says what to do, with the real count and layer. With tables and valid examples:
//   Builder recommends publishing, then Microsoft 365 Copilot; the step is a dry run first and publishes only after the
//   person ticks and chooses Publish as me. Publish to Agent Store stays the person's step in Fabric.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BuildCard } from "./engineClient";
import {
  CheerBook, PIPELINE_CHEER, agentCheer, agentReady, cheeredBefore, examplesValid, pipelineCheer, readCheered, withCheer,
} from "./cheer";
import { CheerContext, CheerSource } from "./cheerView";
import { AgentGuide, AgentPublishContext, CopilotStep } from "./CopilotStep";
import {
  COPILOT_BUTTON, CopilotAnswer, agentNoTablesLine, planLines, publishAdvice, publishBody, publishGate, requirementLine,
} from "./copilotWords";
import { OutputCard } from "./ModelItemViews";
import { selectTablesOffer } from "./afterRun";

const WS = "11111111-2222-4333-8444-555555555555";
const AGENT = "dddddddd-0000-4000-8000-0000000000a1";

function agent(sel: Record<string, unknown>, examples?: Record<string, unknown>, over: Partial<BuildCard> = {}): BuildCard {
  return {
    output: "data_agent", label: "Data agent", type: "DataAgent", name: "shop_agent", dry_run: false, status: "done", permissions: { needs: [] },
    created: [{ type: "DataAgent", id: AGENT, name: "shop_agent", workspace: WS }],
    agent: { layer: "silver", publish: false, copilot: false, where_examples: "x",
      selection: { layer: "silver", schema: "silver", deselected: 0, one_layer: true, words: "w", ...sel }, ...(examples ? { examples } : {}) },
    ...over,
  } as unknown as BuildCard;
}
const EMPTY = agent({ selected: 0, total: 7 });
const READY = agent({ selected: 7, total: 7 }, { status: "read", count: 4, valid: 4, invalid: 0, validating: 0 });
const RUN = { status: "Succeeded" as const, run_id: "r1" };

const DRY: CopilotAnswer = {
  name: "shop_agent", workspace: WS, agent_id: AGENT, published: false, confirm: "agent-abc", missing: 1, unverified: 3,
  preflight_words: "Missing for Microsoft 365 Copilot: Paid capacity, F2 or higher (or P1 or higher) (the workspace is on a trial capacity (FT1))",
  requirements: [
    { requirement: "Paid capacity, F2 or higher (or P1 or higher)", status: "missing", detail: "the workspace is on a trial capacity (FT1)",
      doc: "https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot" },
    { requirement: "Tenant setting \"Users can use Copilot and other features powered by Azure OpenAI\"", status: "unverified",
      detail: "Unverified: only a Fabric administrator can read tenant settings (Tenant.Read.All)", doc: "https://learn.microsoft.com/fabric/data-science/data-agent-tenant-settings" },
  ],
  plan: [
    { step: "Publish shop_agent in Fabric, so people with access to the workspace can use it", by: "Krusgraph, as you",
      how: "Publish data agent (POST .../dataAgents/{id}/staging/publish)", scope: "Item.ReadWrite.All (or DataAgent.ReadWrite.All)" },
    { step: "Make shop_agent available in Microsoft 365 Copilot", by: "you, in Fabric",
      how: "In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish. Krusgraph cannot do this step: Microsoft documents no API for it.", scope: null },
  ],
  copilot_step: "In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish. Krusgraph cannot do this step: Microsoft documents no API for it.",
};

describe("cheer: the milestones", () => {
  it("the pipeline cheers only for a run of this Create that succeeded", () => {
    const pipe = (status: string, run_id?: string) => ({ output: "pipeline", dry_run: false, jobs: { run: { status, run_id } } }) as unknown as BuildCard;
    expect(pipelineCheer(pipe("Succeeded", "r1"))).toBe(PIPELINE_CHEER);
    for (const p of [pipe("Running", "r1"), pipe("Failed", "r1"), pipe("Succeeded"), { ...pipe("Succeeded", "r1"), dry_run: true }]) {
      expect(pipelineCheer(p as BuildCard)).toBeUndefined();
    }
  });

  it("the agent is ready with every table selected and only valid examples", () => {
    expect(agentReady(READY)).toBe(true);
    expect(agentCheer(READY)).toBe("The agent is ready: 7 silver tables selected and 4 valid example queries.");
    expect(agentReady(EMPTY)).toBe(false);
    expect(agentReady(agent({ selected: 5, total: 7 }, { status: "read", valid: 4 }))).toBe(false);
    expect(agentReady(agent({ selected: 7, total: 7 }, { status: "read", valid: 3, invalid: 1 }))).toBe(false);
    expect(agentReady(agent({ selected: 7, total: 7 }, { status: "not_checked", count: 4 }))).toBe(false);
    expect(examplesValid(agent({ selected: 7 }, { status: "read", valid: 4, not_checked: 1 }))).toBe(false);
    expect(agentReady({ ...READY, dry_run: true } as BuildCard)).toBe(false);
  });

  it("once per milestone per Create: one place claims it, outputs.json remembers it, a new Create starts again", () => {
    const book = new CheerBook();
    expect(book.claim("pipeline_succeeded", "c1", "pipeline")).toBe(true);
    expect(book.claim("pipeline_succeeded", "c1", "pipeline")).toBe(true);           // the same place, drawn again
    expect(book.claim("pipeline_succeeded", "c1", "elsewhere")).toBe(false);         // never twice on the page
    expect(book.claim("agent_ready", "c1", "agent")).toBe(true);
    const rec = withCheer(undefined, "c1", "pipeline_succeeded");
    expect(cheeredBefore(rec, "c1", "pipeline_succeeded")).toBe(true);
    expect(new CheerBook().claim("pipeline_succeeded", "c1", "pipeline", rec)).toBe(false);   // reopened: no repeat
    expect(new CheerBook().claim("pipeline_succeeded", "c2", "pipeline", rec)).toBe(true);    // the next Create
    expect(withCheer(rec, "c2", "agent_ready")).toEqual({ create: "c2", said: ["agent_ready"] });
    expect(readCheered({ create: "c1", said: ["agent_ready", "nonsense"] })).toEqual({ create: "c1", said: ["agent_ready"] });
    expect(readCheered("x")).toBeUndefined();
  });
});

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const src = (on: boolean, book = new CheerBook()): CheerSource => ({ on, create: "c1", book });

describe("cheer on the cards", () => {
  const pipeline = { output: "pipeline", label: "Pipeline", type: "DataPipeline", name: "p", dry_run: false, status: "done", permissions: { needs: [] },
    jobs: { run_once: true, schedule: null, words: [], permission: { scope: "Item.Execute.All", or: "DataPipeline.Execute.All" },
      run: { status: "Succeeded", run_id: "r1" } } } as unknown as BuildCard;

  it("the pipeline card cheers once, with the mascots on only", () => {
    const book = new CheerBook();
    act(() => root.render(<CheerContext.Provider value={src(true, book)}><OutputCard card={pipeline} /><OutputCard card={pipeline} /></CheerContext.Provider>));
    expect(host.querySelectorAll("[data-w3-cheer=pipeline_succeeded]").length).toBe(1);
    expect(host.querySelector("[data-w3-cheer=pipeline_succeeded] [data-pose=celebrate]")).not.toBeNull();
    act(() => root.render(<CheerContext.Provider value={src(false)}><OutputCard card={pipeline} /></CheerContext.Provider>));
    expect(host.querySelector("[data-w3-cheer]")).toBeNull();
  });

  it("the agent card cheers when ready, and not before", () => {
    act(() => root.render(<CheerContext.Provider value={src(true)}><OutputCard card={READY} run={RUN} /></CheerContext.Provider>));
    expect(host.querySelector("[data-w3-cheer=agent_ready]")!.textContent).toContain("The agent is ready");
    act(() => root.render(<CheerContext.Provider value={src(true)}><OutputCard card={EMPTY} run={RUN} /></CheerContext.Provider>));
    expect(host.querySelector("[data-w3-cheer]")).toBeNull();
  });
});

describe("the agent card's guidance", () => {
  it("without tables: Thinker says what to do, with the real count and layer", () => {
    expect(agentNoTablesLine(EMPTY, selectTablesOffer(EMPTY, 0, RUN), RUN))
      .toBe("The agent has no tables yet. Choose Select tables now, or tick the 7 silver tables in the agent (not krusgraph_quarantine).");
    expect(agentNoTablesLine(EMPTY, selectTablesOffer(EMPTY, 3, RUN), RUN))
      .toBe("The agent has no tables yet. Tick the 7 silver tables in the agent in Fabric (not krusgraph_quarantine).");
    const gold = agent({ layer: "gold", selected: 0, total: 4 });
    expect(agentNoTablesLine(gold, selectTablesOffer(gold, 0, RUN), RUN))
      .toBe("The agent has no tables yet. Choose Select tables now, or tick the 4 gold tables in the agent.");
    expect(agentNoTablesLine(EMPTY, selectTablesOffer(EMPTY, 0, { status: "Running" }), { status: "Running" })).toBeUndefined();
    expect(agentNoTablesLine(READY, selectTablesOffer(READY, 0, RUN), RUN)).toBeUndefined();
    const html = renderToStaticMarkup(<AgentGuide card={EMPTY} run={RUN} />);
    expect(html).toContain('data-mascot="thinker"');
    expect(html).toContain("Choose Select tables now");
  });

  it("with tables and valid examples: Builder recommends publishing, then Copilot", () => {
    expect(publishAdvice(READY)).toBe("Next: publish shop_agent, then make it available in Microsoft 365 Copilot. Make it available in Copilot "
      + "shows what Microsoft requires and what would be done; nothing is published until you choose.");
    const published = { ...READY, agent: { ...READY.agent!, published: true } } as BuildCard;
    expect(publishAdvice(published)).toMatch(/^shop_agent is published in Fabric\. Next: make it available in Microsoft 365 Copilot\./);
    expect(publishAdvice(EMPTY)).toBeUndefined();
  });

  it("with the mascots off the lines are plain sentences", () => {
    act(() => root.render(<CheerContext.Provider value={src(false)}><AgentGuide card={READY} run={RUN} /></CheerContext.Provider>));
    expect(host.querySelector(".krusgraph-fig")).toBeNull();
    expect(host.querySelector("[data-w3=agent-publish-advice]")!.tagName).toBe("P");
  });
});

describe("Make it available in Copilot", () => {
  it("its words: each requirement, the steps with who does them, and the gate", () => {
    expect(requirementLine(DRY.requirements[0])).toBe("Missing: Paid capacity, F2 or higher (or P1 or higher) (the workspace is on a trial capacity (FT1)).");
    expect(planLines(DRY)[0]).toMatch(/^1\. Publish shop_agent in Fabric, .*\. Krusgraph does it, as you: Publish data agent/);
    expect(planLines(DRY)[1]).toMatch(/^2\. Make shop_agent available in Microsoft 365 Copilot\. You do it, in Fabric: In Fabric, open the agent/);
    expect(publishGate(undefined, true).ok).toBe(false);
    expect(publishGate(DRY, false).why).toBe("Tick that you want Krusgraph to publish shop_agent in Fabric.");
    expect(publishGate({ ...DRY, confirm: null }, true).ok).toBe(false);
    expect(publishGate(DRY, true)).toEqual({ ok: true, why: "" });
    expect(publishBody(READY, "demo_lh", true)).toEqual({ workspace: WS, agent_id: AGENT, name: "shop_agent", source_name: "demo_lh", dry_run: true, confirm: null });
    expect(publishBody(READY, undefined, false, "agent-abc")).toMatchObject({ dry_run: false, confirm: "agent-abc" });
  });

  it("is a dry run first and publishes only after the tick and the click", async () => {
    const run = vi.fn(async (body: object) => ((body as { dry_run: boolean }).dry_run ? DRY
      : { ...DRY, published: true, confirm: null, words: "Published shop_agent in Fabric: people with access to the workspace can use it." }));
    act(() => root.render(<AgentPublishContext.Provider value={{ run, source: "demo_lh" }}><CopilotStep card={READY} /></AgentPublishContext.Provider>));
    const buttons = () => Array.from(host.querySelectorAll("button"));
    expect(run).not.toHaveBeenCalled();                                    // nothing is sent before a click
    await act(async () => buttons().find((b) => b.textContent === COPILOT_BUTTON)!.click());
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toMatchObject({ dry_run: true, confirm: null });
    expect(host.textContent).toContain("Missing: Paid capacity");
    expect(host.querySelectorAll("ol[aria-label='What would be done'] li").length).toBe(2);
    const publish = buttons().find((b) => b.textContent === "Publish as me")!;
    expect(publish.hasAttribute("disabled")).toBe(true);
    expect(host.querySelector("#kg-copilot-why")!.textContent).toBe("Tick that you want Krusgraph to publish shop_agent in Fabric.");
    await act(async () => (host.querySelector("input[type=checkbox]") as HTMLInputElement).click());
    expect(run).toHaveBeenCalledTimes(1);                                  // ticking sends nothing
    await act(async () => buttons().find((b) => b.textContent === "Publish as me")!.click());
    expect(run).toHaveBeenCalledTimes(2);
    expect(run.mock.calls[1][0]).toMatchObject({ dry_run: false, confirm: "agent-abc", agent_id: AGENT });
    expect(host.querySelector("[data-w3=published]")!.textContent).toContain("Last step, yours: In Fabric, open the agent → Publish → tick Publish to Agent Store");
  });

  it("is not offered where nothing provides the call, nor before the agent is ready", () => {
    act(() => root.render(<CopilotStep card={READY} />));
    expect(host.textContent).toBe("");
    act(() => root.render(<AgentPublishContext.Provider value={{ run: vi.fn() }}><AgentGuide card={EMPTY} run={RUN} /></AgentPublishContext.Provider>));
    expect(host.textContent).not.toContain(COPILOT_BUTTON);
  });
});
