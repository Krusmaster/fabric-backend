// @vitest-environment jsdom
// ED3 (Gustav's editor test of 21 November 2026, part 3): Open in Fabric on every created item (a new tab), Run now
// with its states and the output's preview, one line after Create (never the same sentence twice), the stale check said
// once, and Advanced analytics with the analyses analysis_plan recommends. Synthetic shop schema; a fake engine only.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FIXTURE from "./w13Review.fixture.json";
import ANALYSIS from "./wb4Analysis.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { factoryTitle, nextSteps, staleCheckLine } from "./nextSteps";
import { AdvancedAnalytics, AnalysisContext, NextStepsPanel, StarterAnswer, StarterContext, forgetAnalyses } from "./NextStepsView";
import { RunContext, RunNow } from "./RunNowView";
import { FABRIC_PORTAL, OpenInFabric, fabricItemUrl } from "./openInFabric";
import { IDLE, RUN_ONLY_WHEN, nextView, outputTable, pollDelay, previewCells, runStatus } from "./runNow";
import { analysisCards, AnalysisAnswer } from "./analysisPlan";
import { analysisName, ipynbCells, pickedByDefault } from "./advancedAnalytics";
import { FileContext } from "./fileOffer";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SOURCE = { displayName: "shop_lh", schema: "shop", itemType: "Lakehouse" };
const SAP = ANALYSIS as unknown as AnalysisAnswer;
const WS = "11111111-1111-1111-1111-111111111111";
const NB = "22222222-2222-2222-2222-222222222222";
const LH = "33333333-3333-3333-3333-333333333333";

describe("Open in Fabric: the item's own page, per item type", () => {
  it.each([
    ["Notebook", "synapsenotebooks"], ["DataPipeline", "pipelines"], ["Report", "reports"], ["DataAgent", "aiskills"],
    ["Lakehouse", "lakehouses"], ["GraphQLApi", "graphql"], ["Ontology", "ontologies"],
  ])("%s opens /groups/<ws>/%s/<id>", (type, path) => {
    expect(fabricItemUrl({ id: NB, workspaceId: WS, type })).toBe(`${FABRIC_PORTAL}/groups/${WS}/${path}/${NB}`);
  });
  it("has no address without an id or a workspace", () => {
    expect(fabricItemUrl({ workspaceId: WS, type: "Notebook" })).toBeUndefined();
    expect(fabricItemUrl({ id: NB, type: "Notebook" })).toBeUndefined();
  });
});

describe("Run now: the states a run goes through", () => {
  it("queued -> running -> succeeded with the preview, reading again while it runs", () => {
    let v = nextView({ state: "starting", polls: 0 }, { state: "queued", run_id: "r1" });
    expect(v.state).toBe("queued");
    expect(pollDelay(v)).toBe(5000);
    v = nextView(v, { state: "running" });
    expect(v).toMatchObject({ state: "running", runId: "r1" });
    v = nextView(v, { state: "succeeded", preview: { table: "orders_features", row_count: 12, columns: ["a"], rows: [{ a: 1 }], words: "orders_features: 12 rows" } });
    expect(v.state).toBe("succeeded");
    expect(pollDelay(v)).toBeUndefined();
    expect(runStatus(v)).toEqual({ word: "Succeeded", line: "orders_features: 12 rows" });
  });
  it("failed says Fabric's message once, in the line, not in the word", () => {
    const v = nextView({ ...IDLE, runId: "r1" }, { state: "failed", message: "Table not found: shop.orders" });
    const st = runStatus(v);
    expect(st.word).toBe("Failed");
    expect(`${st.word} ${st.line}`.split("Table not found").length - 1).toBe(1);
  });
  it("without the permission: not started, with the way in Fabric", () => {
    const v = nextView(IDLE, { error: "Your sign-in cannot start a notebook from Krusgraph.", kind: "needs_permission", hint: "Open in Fabric and choose Run there." });
    expect(v.state).toBe("refused");
    expect(pollDelay(v)).toBeUndefined();
  });
  it("stops reading after half an hour", () => {
    expect(pollDelay({ state: "running", runId: "r", polls: 131 })).toBeUndefined();
    expect(pollDelay({ state: "running", runId: "r", polls: 20 })).toBe(15000);
  });
  it("finds the table a starter writes, and shows at most 10 rows", () => {
    expect(outputTable('features.write.mode("overwrite").format("delta").saveAsTable("orders_features")')).toBe("orders_features");
    const rows = Array.from({ length: 14 }, (_, i) => ({ id: i, name: null as string | null }));
    const c = previewCells({ table: "t", columns: ["id", "name"], rows });
    expect(c.rows.length).toBe(10);
    expect(c.rows[0]).toEqual(["0", ""]);
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
  vi.useRealTimers();
});

const sentences = (t: string) => t.split(/(?<=[.!?])\s+|(?<=[.!?])(?=[A-Z])/).map((x) => x.trim()).filter((x) => x.length > 12);

describe("the Data Science card after Create", () => {
  const made = { type: "Notebook", id: NB, name: "shop_lh_orders_features", workspace: WS, output: "ds_features", attached: LH };
  it("has Open in Fabric (a new tab) first and Run now beside it; Download and Copy are secondary", () => {
    const open = vi.fn(async () => {});
    act(() => root.render(
      <FileContext.Provider value={{ offer: vi.fn(), open, base: "" } as never}>
        <RunContext.Provider value={{ run: vi.fn() }}>
          <NextStepsPanel review={REVIEW} created={[made]} source={SOURCE} onBuild={() => {}} />
        </RunContext.Provider>
      </FileContext.Provider>));
    const card = host.querySelector("[data-step=ds-features]")!;
    const link = card.querySelector("a.kg-open-fabric") as HTMLAnchorElement;
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.href).toBe(`${FABRIC_PORTAL}/groups/${WS}/synapsenotebooks/${NB}`);
    expect(link.className).toContain("kg-open-fabric-primary");
    act(() => link.click());
    expect(open).toHaveBeenCalledWith(link.href);
    const buttons = Array.from(card.querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons.slice(0, 1)).toEqual(["Run now"]);
    expect(buttons).toContain("Download notebook (.ipynb)");
    expect(card.textContent).toContain(RUN_ONLY_WHEN);
    expect(card.textContent).not.toContain("Dry run");
  });
  it("never says the same thing twice (Gustav: 'open it and run it' and 'run it yourself')", () => {
    act(() => root.render(
      <RunContext.Provider value={{ run: vi.fn() }}>
        <NextStepsPanel review={REVIEW} created={[made]} source={SOURCE} onBuild={() => {}} />
      </RunContext.Provider>));
    const card = host.querySelector("[data-step=ds-features]")!;
    const text = Array.from(card.querySelectorAll(".fui-Caption1, .fui-Body1")).map((e) => e.textContent ?? "").join(" ");
    const all = sentences(text);
    expect(new Set(all).size).toBe(all.length);
    expect(text).not.toMatch(/run it yourself|open it and run it/i);
    expect(text.match(/runs it only when you choose Run now/g)?.length).toBe(1);
  });
  it("after Create in this session: the dry run's words go, the card shows the item once", async () => {
    let created = false;
    const run = vi.fn(async ({ dryRun }: { dryRun: boolean }): Promise<StarterAnswer> => (dryRun
      ? { would: "create", name: made.name, confirm: "starter-1", words: "Would create the notebook in demo_ws, attached to shop_lh_krusgraph_test. Krusgraph runs it only when you choose Run now." }
      : { would: "created", name: made.name, confirm: null, words: "Created the notebook in demo_ws.", created: made }));
    const Wrapper = () => {
      const [list, setList] = React.useState<typeof made[]>([]);
      return (
        <StarterContext.Provider value={{ run, onCreated: (i) => { created = true; setList([i as typeof made]); } }}>
          <RunContext.Provider value={{ run: vi.fn() }}>
            <NextStepsPanel review={REVIEW} created={list} source={SOURCE} onBuild={() => {}} />
          </RunContext.Provider>
        </StarterContext.Provider>);
    };
    await act(async () => root.render(<Wrapper />));
    const dry = Array.from(host.querySelectorAll("button")).find((b) => b.textContent === "Dry run")!;
    await act(async () => dry.click());
    const create = Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith("Create "))!;
    await act(async () => create.click());
    expect(created).toBe(true);
    const card = host.querySelector("[data-step=ds-features]")!;
    expect(card.querySelector("a.kg-open-fabric")).not.toBeNull();
    const all = sentences(card.textContent ?? "");
    expect(new Set(all).size).toBe(all.length);
    expect(card.textContent).not.toContain("Would create");
  });
});

describe("Run now on the card: status and the preview", () => {
  it("reads until it succeeds and shows the row count and the first rows", async () => {
    vi.useFakeTimers();
    const answers = [
      { state: "queued", run_id: "44444444-4444-4444-4444-444444444444", words: "queued" },
      { state: "running", words: "running" },
      { state: "succeeded", words: "succeeded", preview: { table: "orders_features", row_count: 3, columns: ["order_id", "order_items_rows"],
        rows: [{ order_id: 1, order_items_rows: 2 }, { order_id: 2, order_items_rows: 1 }, { order_id: 3, order_items_rows: 4 }],
        words: "orders_features: 3 rows; the first 3 below. Read now, not stored." } },
    ];
    const run = vi.fn(async (_body: unknown) => answers.shift() as never);
    act(() => root.render(
      <RunContext.Provider value={{ run }}>
        <RunNow item={{ id: NB, workspaceId: WS, type: "Notebook", displayName: "shop_lh_orders_features" }}
          preview={{ lakehouse: LH, table: "orders_features", schema: "dbo" }} />
      </RunContext.Provider>));
    expect(run).not.toHaveBeenCalled();                                  // never automatic
    const btn = host.querySelector("button")!;
    await act(async () => btn.click());
    expect(host.querySelector(".fui-Badge")!.textContent).toBe("Queued in Fabric");
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(host.querySelector(".fui-Badge")!.textContent).toBe("Running in Fabric");
    await act(async () => { vi.advanceTimersByTime(5000); });
    expect(host.querySelector(".fui-Badge")!.textContent).toBe("Succeeded");
    expect(host.textContent).toContain("orders_features: 3 rows");
    expect(host.querySelectorAll(".kg-run-preview tbody tr").length).toBe(3);
    expect(run.mock.calls[1][0]).toMatchObject({ run_id: "44444444-4444-4444-4444-444444444444", preview: { table: "orders_features" } });
    expect(run).toHaveBeenCalledTimes(3);
  });
  it("is not offered for a report", () => {
    act(() => root.render(
      <RunContext.Provider value={{ run: vi.fn() }}>
        <RunNow item={{ id: NB, workspaceId: WS, type: "Report" }} />
      </RunContext.Provider>));
    expect(host.querySelector("button")).toBeNull();
  });
});

describe("the stale check on the Next page", () => {
  it("is said once when the newest check is older than a day, and not at all from today", () => {
    expect(staleCheckLine("2026-11-11T20:23:00Z", new Date("2026-11-21T13:00:00Z"))).toBe(
      "That check is 9 days old: Check against the rows again to prove it on today's rows.");
    expect(staleCheckLine("2026-11-21T09:00:00Z", new Date("2026-11-21T13:00:00Z"))).toBeUndefined();
  });
  it("the Data Factory card does not call the pipeline built while silver is not", () => {
    expect(factoryTitle(["silver_notebook", "gold_views"], ["pipeline"])).toBe(
      "Silver notebook and gold views; the pipeline exists but has nothing to run until they are built");
  });
});

describe("Advanced analytics on the Data product step", () => {
  it("lists the analyses the rules recommend, with the top one ticked and nothing created before Create", async () => {
    const starter = vi.fn(async ({ dryRun, name }: { dryRun: boolean; name: string }): Promise<StarterAnswer> => (dryRun
      ? { would: "create", name, confirm: "starter-a7", words: `Would create the notebook ${name} in demo_ws, attached to shop_lh_krusgraph_test.` }
      : { would: "created", name, confirm: null, words: "", created: { type: "Notebook", id: NB, name, workspace: WS, output: "analysis_A7", attached: LH } }));
    const onCreated = vi.fn();
    await act(async () => root.render(
      <AnalysisContext.Provider value={{ run: async () => SAP }}>
        <StarterContext.Provider value={{ run: starter, onCreated }}>
          <AdvancedAnalytics review={REVIEW} source={SOURCE} created={[]} />
        </StarterContext.Provider>
      </AnalysisContext.Provider>));
    const section = host.querySelector("#kg-advanced-analytics")!;
    expect(section.querySelector("h2")!.textContent).toBe("Advanced analytics");
    const cards = analysisCards(SAP, SOURCE);
    expect(pickedByDefault(cards)).toEqual(["A7"]);
    const ids = Array.from(section.querySelectorAll("[data-analysis]")).map((li) => li.getAttribute("data-analysis"));
    expect(ids).toEqual(SAP.recommendations.map((r) => r.analysis));
    const ticks = Array.from(section.querySelectorAll("input[type=checkbox]")) as HTMLInputElement[];
    expect(ticks.filter((t) => t.checked).length).toBe(1);
    expect(starter).not.toHaveBeenCalled();
    const dry = Array.from(section.querySelectorAll("button")).find((b) => b.textContent === "Dry run: 1 notebook")!;
    await act(async () => dry.click());
    expect(starter).toHaveBeenCalledWith(expect.objectContaining({ dryRun: true, output: "analysis_A7" }));
    const name = analysisName(cards[0]);
    const create = Array.from(section.querySelectorAll("button")).find((b) => b.textContent === `Create ${name}`)!;
    await act(async () => create.click());
    expect(onCreated).toHaveBeenCalled();
  });
  it("takes the notebook's code cells from the .ipynb", () => {
    const nb = JSON.stringify({ cells: [{ cell_type: "markdown", source: ["# t"] }, { cell_type: "code", source: ["a = 1\n", "b = 2"] }] });
    expect(ipynbCells(nb)).toEqual(["a = 1\nb = 2"]);
  });
});

describe("Open in Fabric as a component", () => {
  it("opens through the host, else the browser's own new tab", () => {
    const opened = vi.spyOn(window, "open").mockImplementation(() => null);
    act(() => root.render(<OpenInFabric item={{ id: NB, workspaceId: WS, type: "DataPipeline", displayName: "demo_lh_pipeline" }} />));
    const a = host.querySelector("a")!;
    expect(a.getAttribute("aria-label")).toBe("Open in Fabric: demo_lh_pipeline (opens a new tab)");
    act(() => a.click());
    expect(opened).toHaveBeenCalledWith(`${FABRIC_PORTAL}/groups/${WS}/pipelines/${NB}`, "_blank", "noopener");
  });
});

// keep nextSteps imported for the type check of the fixture
void nextSteps;
