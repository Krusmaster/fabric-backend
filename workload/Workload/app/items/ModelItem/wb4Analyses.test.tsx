// @vitest-environment jsdom
// WB4 (20 Nov 2026): Recommended analyses in Next, with other Fabric workloads. The engine's answer is its own, on the
// 24-month synthetic SAP sample sap_sd (wb4Analysis.fixture.json, made by the e2e engine's `sap` scenario); the review is
// the engine's own on the synthetic shop schema (w13Review.fixture.json). Readiness in words, never colour alone; ranked;
// one line of why; what is missing; the notebook starter only for a ready A7, A8 or A3; nothing before the check.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FIXTURE from "./w13Review.fixture.json";
import ANSWER from "./wb4Analysis.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { AnalysisAnswer, analysisCards, analysisKey, analysisSummary, askText, becauseLine, missingLine, READINESS_WORD } from "./analysisPlan";
import { AnalysisContext, NextStepsPanel, forgetAnalyses } from "./NextStepsView";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SAP = ANSWER as unknown as AnalysisAnswer;
const SOURCE = { displayName: "demo_lh", schema: "sap_sd", itemType: "Lakehouse" };

describe("the cards (analysisPlan.ts)", () => {
  const cards = analysisCards(SAP, SOURCE);
  const by = Object.fromEntries(cards.map((c) => [c.id, c]));

  it("keep the engine's rank, and say the readiness in words", () => {
    expect(cards.map((c) => c.id).slice(0, 4)).toEqual(["A7", "A8", "A3", "A4"]);
    expect(cards.map((c) => c.rank)).toEqual(cards.map((_, i) => i + 1));
    expect([by.A7.word, by.A8.word, by.A1.word, by.A10.word]).toEqual(["Ready", "Partly ready", "Not ready yet", "Not applicable"]);
    expect(Object.values(READINESS_WORD).every((w) => /^[A-Z][a-z ]+$/.test(w))).toBe(true);
    expect(analysisSummary(cards)).toBe("3 of 10 analyses ready, 1 partly ready, 6 not ready yet.");
  });

  it("give one line of why, and what is missing", () => {
    expect(by.A7.line).toMatch(/^Recommended because VBRP\.NETWR is the amount to forecast/);
    expect(by.A7.line.includes("\n")).toBe(false);
    expect(by.A1.line).toMatch(/^Not ready yet because a cost/);
    expect(by.A1.missing).toMatch(/^What would make it ready: a cost: VBRP\.WAVWR/);
    expect(by.A2.missing).toContain("BSID/BSAD");
    expect(by.A8.missing).toMatch(/^Holding it back: capped at partial: customers/);
    expect(by.A3.missing).toMatch(/XYZ part not ready/);
  });

  it("offer the notebook starter only for a ready A7, A8 or A3; otherwise the request for Claude", () => {
    for (const id of ["A7", "A3"]) {
      const a = by[id].action;
      expect(a.kind).toBe("notebook");
      if (a.kind !== "notebook") continue;
      expect(a.label).toBe("Download notebook (.ipynb)");
      expect(JSON.parse(a.content).nbformat).toBe(4);
      expect(a.code).toContain("krusgraph.analysis");
    }
    expect(by.A8.action).toMatchObject({ kind: "ask", label: "Copy the request for Claude" });
    expect(askText(SAP.recommendations.find((e) => e.analysis === "A8")!, SOURCE)).toBe(
      'Draft the A8 RFM segmentation (and clustering) notebook for demo_lh (schema sap_sd): run analysis_notebook_draft with analysis="A8". It creates and runs nothing.');
    expect(by.A4.action.kind).toBe("ask");                                     // ready, but its notebook is planned
    expect(by.A1.action).toMatchObject({ kind: "ask" });
    expect(by.A1.action.kind === "ask" && by.A1.action.text).toContain("Run analysis_plan");
  });

  it("are none before the check, and none on a schema without SAP tables", () => {
    expect(analysisCards({ waiting: "Check against the rows first", recommendations: [] }, SOURCE)).toEqual([]);
    expect(analysisCards({ applies: false, words: "No SAP order-to-cash tables", recommendations: [] }, SOURCE)).toEqual([]);
    expect(analysisCards(undefined, SOURCE)).toEqual([]);
  });

  it("are kept per source, schema and check", () => {
    const a = analysisKey(SOURCE, REVIEW);
    expect(analysisKey(SOURCE, REVIEW)).toBe(a);
    expect(analysisKey({ ...SOURCE, schema: "dbo" }, REVIEW)).not.toBe(a);
    const one = { ...REVIEW, items: REVIEW.items.map((it, i) => (i === 0 ? { ...it, review: "rejected" } : it)) } as ReviewFile;
    expect(analysisKey(SOURCE, one)).not.toBe(a);
  });

  it("word a not-applicable analysis without a contradiction", () => {
    const a10 = SAP.recommendations.find((e) => e.analysis === "A10")!;
    expect(becauseLine(a10)).toMatch(/^Not applicable to this data because no documents of the return or credit types/);
    expect(missingLine(a10)).toMatch(/^To apply: /);
  });
});

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  forgetAnalyses();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

async function render(run: () => Promise<AnalysisAnswer>, review: ReviewFile = REVIEW) {
  await act(async () => root.render(
    <AnalysisContext.Provider value={{ run }}>
      <NextStepsPanel review={review} created={[]} source={SOURCE} onBuild={() => {}} />
    </AnalysisContext.Provider>));
}

describe("the section in Next, with other Fabric workloads", () => {
  it("is not there without the editor's engine (the older tests and pages)", () => {
    act(() => root.render(<NextStepsPanel review={REVIEW} created={[]} source={SOURCE} onBuild={() => {}} />));
    expect(host.querySelector(".kg-analysis")).toBeNull();
  });

  it("asks the engine nothing before a key has passed the check", async () => {
    const run = vi.fn(async () => SAP);
    const unchecked = { ...REVIEW, items: REVIEW.items.map((it) => ({ ...it, check: undefined as unknown })) } as ReviewFile;
    await render(run, unchecked);
    expect(run).not.toHaveBeenCalled();
    expect(host.querySelector(".kg-analysis")).toBeNull();
    expect(host.textContent).toContain("Check against the rows first");
  });

  it("shows the ranked cards with names a screen reader reads, and Download and Copy for the ready notebooks", async () => {
    const run = vi.fn(async () => SAP);
    await render(run);
    expect(run).toHaveBeenCalledTimes(1);
    const section = host.querySelector("section.kg-analysis")!;
    expect(section.getAttribute("aria-labelledby")).toBe("kg-analysis-title");
    expect(host.querySelector("#kg-analysis-title")!.textContent).toBe("Recommended analyses");
    expect(section.textContent).toContain("3 of 10 analyses ready, 1 partly ready, 6 not ready yet.");
    const lists = section.querySelectorAll("ol");
    expect(lists[0].getAttribute("aria-label")).toBe("Ready and partly ready analyses, ranked");
    expect(Array.from(lists[0].querySelectorAll("li")).map((li) => li.getAttribute("data-analysis"))).toEqual(["A7", "A8", "A3", "A4"]);
    expect(lists[1].getAttribute("start")).toBe("5");
    const a7 = section.querySelector("[data-analysis=A7]")!;
    expect(a7.querySelector(".fui-Badge")!.textContent).toBe("Ready");                    // the word, not only the colour
    expect(a7.querySelector("h4")!.textContent).toBe("A7 Demand and revenue forecasting");
    expect(a7.querySelector("[role=group]")!.getAttribute("aria-label")).toBe("A7 Demand and revenue forecasting: Ready");
    const names = Array.from(a7.querySelectorAll("button")).map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(names).toEqual(["Download notebook (.ipynb): A7 Demand and revenue forecasting", "Copy the code"]);
    expect(a7.textContent).toContain("Krusgraph does not run it and trains no model");
    const a8 = section.querySelector("[data-analysis=A8]")!;
    expect(a8.querySelector(".fui-Badge")!.textContent).toBe("Partly ready");
    expect(Array.from(a8.querySelectorAll("button")).map((b) => b.textContent)).toEqual(["Copy the request for Claude"]);
    const later = section.querySelector("details.kg-analysis-later")!;
    expect(later.querySelector("summary")!.textContent).toBe("Not ready yet (6): what data would make them ready");
    expect(later.textContent).toContain("would unlock A2, A9");
    expect(later.querySelector("[data-analysis=A1]")!.textContent).toContain("What would make it ready");
  });

  it("every button is reachable by keyboard: real buttons, none taken out of the tab order", async () => {
    await render(async () => SAP);
    const section = host.querySelector("section.kg-analysis")!;
    const controls = Array.from(section.querySelectorAll("button, summary"));
    expect(controls.length).toBeGreaterThan(10);
    expect(controls.every((c) => c.getAttribute("tabindex") !== "-1" && !(c as HTMLButtonElement).disabled)).toBe(true);
    expect(section.querySelectorAll("[onclick], div[role=button]").length).toBe(0);
  });

  it("does not count the rows again for the same check (the result view, then the Data product page)", async () => {
    const run = vi.fn(async () => SAP);
    await render(run);
    act(() => root.unmount());
    root = createRoot(host);
    await render(run);
    expect(run).toHaveBeenCalledTimes(1);
    expect(host.querySelector("[data-analysis=A7]")).not.toBeNull();
  });

  it("says when there is nothing SAP to rank, and offers Try again when the engine fails", async () => {
    await render(async () => ({ applies: false, words: "No SAP order-to-cash tables were found in this schema.", recommendations: [] }));
    expect(host.querySelector(".kg-analysis")!.textContent).toContain("No SAP order-to-cash tables were found");
    act(() => root.unmount());
    forgetAnalyses();
    root = createRoot(host);
    let fail = true;
    const run = vi.fn(async () => {
      if (fail) throw Object.assign(new Error("x"), { answer: { error: "The engine stopped.", hint: "Try again." } });
      return SAP;
    });
    await render(run);
    const alert = host.querySelector(".kg-analysis [role=alert]")!;
    expect(alert.textContent).toContain("The engine stopped. Try again.");
    fail = false;
    await act(async () => { (alert.querySelector("button") as HTMLButtonElement).click(); });
    expect(host.querySelector("[data-analysis=A7]")).not.toBeNull();
  });
});
