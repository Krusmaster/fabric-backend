// n184, additions 1 and 2 from the founder's live Create (9 November 2026, package 1.0.913, all nine outputs created):
// the texts while Create runs and on its cards, and a clear finish that is kept in outputs.json.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  APP_STEPS_TITLE, FINISH_CSS, KEEP_UP_TO_DATE, banner, cardState, itemTypeLabel, lastCreateOf, nextSteps,
  progressLine, readLastCreate, reportFacts, visualCount, withCard,
} from "./createWords";
import { cardFacts, createEach, openLinks, resultLine } from "./buildWords";
import { BuildCard, ManyAnswer, OutputKind, OutputRequest } from "./engineClient";
import { emptyDefinition, fromParts, toParts } from "./ModelItemDefinition";
import { FinishView, OutputCard, ProductView, ResultView } from "./ModelItemViews";

const WS = "11111111-1111-1111-1111-111111111111";
const NINE: [OutputKind, string, string][] = [
  ["silver_notebook", "Silver notebook", "demo_lh_silver"], ["gold_views", "Gold views", "demo_lh_gold"],
  ["pipeline", "Pipeline", "demo_lh_pipeline"], ["semantic_model", "Semantic model", "demo_lh_model"],
  ["report", "Report", "demo_lh_report"], ["graphql", "API for GraphQL", "demo_lh_api"], ["ontology", "Ontology", "demo_lh_ontology"],
  ["data_agent", "Data agent", "demo_lh_agent"], ["rayfin_app", "App (Rayfin, preview)", "demo_lh_app"],
];

function card(kind: OutputKind, extra: Partial<BuildCard> = {}): BuildCard {
  const [, label, name] = NINE.find((x) => x[0] === kind);
  return {
    output: kind, label, type: "", name, dry_run: false, would: "create", updates_in_place: true,
    permissions: { needs: [], missing: null, execute: "" }, status: "done", answer: {},
    created: [{ type: "X", id: `id-${kind}`, name, workspace: WS, output: kind }], ...extra,
  };
}

const allDone = (): BuildCard[] =>
  NINE.map(([k]) => card(k, k === "semantic_model" ? { refresh: { status: "refreshed" } } : {}));

describe("(a) while Create runs", () => {
  it("counts what has happened so far, never 'Nothing was created'", () => {
    const cards = [
      ...NINE.slice(0, 4).map(([k]) => card(k)),
      card("report", { status: "running", created: undefined, answer: undefined }),
      ...NINE.slice(5).map(([k]) => card(k, { status: "waiting", created: undefined, answer: undefined })),
    ];
    expect(progressLine(cards)).toBe("4 of 9 created, 1 creating, 4 waiting.");
    const a = { outputs: cards, refused: 0, dry_run: false } as unknown as ManyAnswer;
    expect(resultLine(a)).toBe("4 of 9 created, 1 creating, 4 waiting.");
    expect(resultLine(a)).not.toContain("Nothing was created");
  });

  it("says failed ones as they come", () => {
    const cards = [card("silver_notebook"), card("gold_views", { answer: { error: "boom", kind: "unexpected" } }),
      card("pipeline", { status: "running" })];
    expect(progressLine(cards)).toBe("1 of 3 created, 1 creating, 1 failed.");
  });

  it("is what createEach's cards say at every step", async () => {
    const outputs: OutputRequest[] = NINE.slice(0, 3).map(([kind, , name]) => ({ kind, name }));
    const seen: string[] = [];
    await createEach(outputs, [], async (o) => ({ outputs: [card(o.kind)], created: [] } as unknown as ManyAnswer),
      (cs) => seen.push(progressLine(cs)));
    expect(seen).toEqual([
      "0 of 3 created, 3 waiting.", "0 of 3 created, 1 creating, 2 waiting.", "1 of 3 created, 2 waiting.",
      "1 of 3 created, 1 creating, 1 waiting.", "2 of 3 created, 1 waiting.", "2 of 3 created, 1 creating.", "3 of 3 created.",
    ]);
  });
});

describe("(b) the data product lists each item by its own type", () => {
  const items = [
    { type: "DataPipeline", id: "p", name: "demo_lh_pipeline", workspace: WS, output: "pipeline" },
    { type: "Notebook", id: "s", name: "demo_lh_silver", workspace: WS, output: "pipeline" },
    { type: "Notebook", id: "g", name: "demo_lh_gold", workspace: WS, output: "pipeline" },
    { type: "Notebook", id: "c", name: "demo_lh_pipeline_check", workspace: WS, output: "pipeline" },
    { type: "AppBackend", id: "a", name: "demo_lh_app", workspace: WS, output: "rayfin_app" },
  ];
  it("in the summary list and the Open links", () => {
    expect(items.map((x) => itemTypeLabel(x.type, x.output))).toEqual(["Pipeline", "Notebook", "Notebook", "Notebook", "App"]);
    expect(openLinks(items).map((l) => l.label)).toEqual(["Pipeline demo_lh_pipeline", "Notebook demo_lh_silver",
      "Notebook demo_lh_gold", "Notebook demo_lh_pipeline_check", "App demo_lh_app"]);
    const html = renderToStaticMarkup(React.createElement(ProductView, {
      product: { name: "Shop", owner: null, plan: {}, items, domains: [] } as never,
    }));
    expect(html).toContain("Notebook demo_lh_silver");
    expect(html).toContain("Notebook demo_lh_pipeline_check");
    expect(html).not.toContain("Pipeline demo_lh_silver");
  });
});

describe("(d) the report's visuals are counted the same in the dry run and on Create", () => {
  const visuals = (n: number) => [{ type: "textbox", title: "Overview" }, ...Array.from({ length: n }, () => ({ type: "card" })),
    { type: "textbox", title: "Footnote" }];
  it("leaves the title and footnote text boxes out of both counts", () => {
    expect(visualCount({ visuals: visuals(8) })).toBe(8);
    const dry = card("report", { dry_run: true, answer: { report: { visuals: visuals(8), bound_to: { semantic_model: "demo_lh_model" } } } });
    expect(cardFacts(dry)[0]).toBe("One page with 8 visuals on demo_lh_model, plus its title and footnote");
  });

  it("explains a difference on the Create card with what was not drawn", () => {
    const done = card("report", { dry_run_visuals: 8, answer: { report: { visuals: visuals(6), not_drawn: [
      { visual: "clusteredColumnChart", why: "no count or quantity measure whose table reaches Calendar through active relationships" }] } } });
    const facts = reportFacts(done);
    expect(facts[0]).toBe("One page with 6 visuals, plus its title and footnote");
    expect(facts[1]).toContain("The dry run drew 8 from this build's draft of the semantic model; Create drew 6");
    expect(facts[2]).toBe("Not drawn: the chart by month: no count or quantity measure whose table reaches Calendar through active relationships");
    expect(reportFacts(card("report", { dry_run_visuals: 6, answer: { report: { visuals: visuals(6) } } }))).toHaveLength(1);
  });

  it("is carried from the dry run into Create's card by createEach", async () => {
    const preview = { outputs: [card("report", { dry_run: true, answer: { report: { visuals: visuals(8) } } })] } as unknown as ManyAnswer;
    const run = await createEach([{ kind: "report", name: "demo_lh_report", model: "m" }], [],
      async () => ({ outputs: [card("report", { answer: { report: { visuals: visuals(8) } } })] } as unknown as ManyAnswer), () => undefined, preview);
    expect(run.cards[0].dry_run_visuals).toBe(8);
  });
});

describe("(f) the App card", () => {
  it("says the App item is empty and where its pages come from", () => {
    expect(cardFacts(card("rayfin_app"))).toEqual(["Empty App item created; its pages and connector come from the package and commands below."]);
    expect(cardFacts(card("rayfin_app", { dry_run: true }))[0]).toContain("Create makes an empty App item");
  });

  it("titles the commands for a terminal, never the Fabric portal", () => {
    const app = card("rayfin_app", {
      portal_steps: ["Install: npm i"],
      answer: { pages: [], api: undefined, commands: [{ step: "Install", command: "npm i" }], why_not_published: "x", preflight: { status: "on" } },
    });
    const html = renderToStaticMarkup(React.createElement(OutputCard, { card: app }));
    expect(APP_STEPS_TITLE).toBe("Still to do (in a terminal with Node, e.g. Azure Cloud Shell)");
    expect(html).toContain(APP_STEPS_TITLE);
    expect(html).not.toContain("Still to do in the Fabric portal");
    const nb = renderToStaticMarkup(React.createElement(OutputCard, { card: card("silver_notebook", { portal_steps: ["Open it and Run all."] }) }));
    expect(nb).toContain("Still to do in the Fabric portal");
  });
});

describe("Addition 2: the marks on the cards", () => {
  it("green created, amber still to do or a choice, red failed, none for a dry run", () => {
    expect(cardState(card("silver_notebook"))).toBe("created");
    expect(cardState(card("rayfin_app"))).toBe("todo");
    expect(cardState(card("semantic_model", { refresh: { status: "refreshed" } }))).toBe("created");
    expect(cardState(card("semantic_model", { refresh: { status: "failed", reason: "x" } }))).toBe("todo");
    expect(cardState(card("gold_views", { refusal: { error: "no", kind: "consent" } }))).toBe("failed");
    expect(cardState(card("pipeline", { built_from: { status: "other", words: "built from another plan" } as never, choices: ["update", "new_name"] }))).toBe("choose");
    expect(cardState(card("ontology", { dry_run: true }))).toBeUndefined();
    const marks = (c: BuildCard) => renderToStaticMarkup(React.createElement(OutputCard, { card: c }));
    expect(marks(card("silver_notebook"))).toMatch(/krusgraph-mark krusgraph-mark-success" role="img" aria-label="Created"/);
    expect(marks(card("rayfin_app"))).toMatch(/krusgraph-mark-warning" role="img" aria-label="Created, still to do"/);
    expect(marks(card("gold_views", { answer: { error: "no", kind: "x" } }))).toMatch(/krusgraph-mark-danger" role="img" aria-label="Failed"/);
    expect(marks(card("ontology", { dry_run: true }))).not.toContain("krusgraph-mark");
  });
});

describe("Addition 2: the finish", () => {
  const AT = "2026-11-09T18:20:00Z";

  it("says Done: 9 of 9 created in demo when every output is done", () => {
    const lc = lastCreateOf(allDone(), "demo", AT);
    const b = banner(lc, "Europe/Stockholm");
    expect(b.tone).toBe("success");
    expect(b.title).toBe("Done: 9 of 9 created in demo; 1 still needs a step (below)");      // the App's pages
    expect(b.when).toBe("Last Create: 9 November 2026, 19:20.");
    const noApp = lastCreateOf(allDone().filter((c) => c.output !== "rayfin_app"), "demo", AT);
    expect(banner(noApp).title).toBe("Done: 8 of 8 created in demo");
  });

  it("says Done with problems, in red with the reasons, when outputs failed", () => {
    const cards = allDone().map((c) =>
      c.output === "ontology" ? { ...c, answer: { error: "Fabric refused", kind: "consent", hint: "Add Item.ReadWrite.All." }, created: [] }
        : c.output === "data_agent" ? { ...c, refusal: { error: "taken", kind: "already_exists" }, created: [] } : c);
    const b = banner(lastCreateOf(cards, "demo", AT));
    expect(b.tone).toBe("danger");
    expect(b.title).toBe("Done with problems: 7 of 9 created, 2 failed");
    expect(b.reasons).toContain("Ontology demo_lh_ontology: Fabric refused Add Item.ReadWrite.All.");
    expect(b.reasons).toContain("Data agent demo_lh_agent: taken");
    expect(b.glad).toBe(false);
    const amber = banner(lastCreateOf([card("silver_notebook"), card("pipeline", { built_from: { words: "built from another plan" } as never, choices: ["update"] })], "demo", AT));
    expect(amber.tone).toBe("warning");
    expect(amber.title).toBe("Done with problems: 1 of 2 created, 1 waiting for your choice");
  });

  it("lists what to do next in plain words", () => {
    const next = nextSteps(lastCreateOf(allDone(), "demo", AT));
    expect(next[0]).toBe("Run the pipeline demo_lh_pipeline once to fill the silver and gold tables; nothing has run yet.");
    expect(next.join(" ")).toContain("Open the report demo_lh_report");
    expect(next.join(" ")).toContain("publish it in Fabric when its answers are right");
    expect(next.join(" ")).toContain("Publish the App demo_lh_app: download the package on its card and run its commands in a terminal with Node");
    expect(next.join(" ")).not.toMatch(/create_|_draft|export_item/);
    const flowOnly = nextSteps(lastCreateOf([card("silver_notebook"), card("gold_views")], "demo", AT));
    expect(flowOnly[0]).toBe("Run the notebook demo_lh_silver, then demo_lh_gold, to fill the silver and gold tables; nothing has run yet.");
    const notRefreshed = nextSteps(lastCreateOf([card("semantic_model", { refresh: { status: "not_run" } })], "demo", AT));
    expect(notRefreshed).toEqual(["Refresh the semantic model demo_lh_model once in Fabric."]);
  });

  it("says how to keep it up to date", () => {
    expect(KEEP_UP_TO_DATE[0]).toContain("the pipeline's schedule runs it (tick Schedule on the pipeline card, or add one in Fabric)");
    expect(KEEP_UP_TO_DATE[0]).toContain("Direct Lake");
    expect(KEEP_UP_TO_DATE[1]).toContain("open this Krusgraph Model item again and choose “Check against the rows again”");
    expect(KEEP_UP_TO_DATE[1]).toContain("Update or a new name");
  });

  it("shows the mascots celebrating when on, and only the banner when off", () => {
    const lc = lastCreateOf(allDone(), "demo", AT);
    const on = renderToStaticMarkup(React.createElement(FinishView, { last: lc, mascotsOn: true }));
    expect(on).toContain('data-pose="celebrate"');
    expect(on).toMatch(/class="krusgraph-mascots krusgraph-cheer"/);
    expect(on).toContain("Done: 9 of 9 created in demo");
    expect(on).toContain('aria-label="Next"');
    expect(on).toContain("Keep it up to date");
    const off = renderToStaticMarkup(React.createElement(FinishView, { last: lc, mascotsOn: false }));
    expect(off).not.toContain("class=\"krusgraph-fig");
    expect(off).not.toContain("class=\"mascot");
    expect(off).not.toMatch(/class="[^"]*krusgraph-cheer/);
    expect(off).not.toContain("data-mascot");
    expect(off).toContain("Done: 9 of 9 created in demo");
    expect(off).toContain('aria-label="Next"');
    const sad = renderToStaticMarkup(React.createElement(FinishView, {
      last: lastCreateOf([card("silver_notebook", { answer: { error: "x", kind: "y" } })], "demo", AT), mascotsOn: true,
    }));
    expect(sad).not.toContain('data-pose="celebrate"');
    expect(sad).not.toMatch(/class="[^"]*krusgraph-cheer/);
  });

  it("moves only for people whose system allows motion", () => {
    const motion = FINISH_CSS.indexOf("@media (prefers-reduced-motion: no-preference)");
    expect(motion).toBeGreaterThan(-1);
    expect(FINISH_CSS.slice(0, motion)).not.toMatch(/animation|@keyframes|transition/);
    expect(FINISH_CSS.slice(motion)).toContain("animation: krusgraph-hop");
  });

  it("is kept in outputs.json and shown again, with its date, when the item is reopened", () => {
    const lc = lastCreateOf(allDone(), "demo", AT);
    const def = emptyDefinition();
    const saved = fromParts(toParts({ ...def, outputs: { ...def.outputs, last_create: lc } }) as never);
    expect(readLastCreate(saved.outputs.last_create)).toEqual(lc);
    const html = renderToStaticMarkup(React.createElement(ResultView, {
      outputs: saved.outputs, onOpen: (): void => undefined, mascotsOn: true, timeZone: "Europe/Stockholm",
    } as never));
    expect(html).toContain("Done: 9 of 9 created in demo");
    expect(html).toContain("Last Create: 9 November 2026, 19:20.");
    expect(readLastCreate({ at: 1 })).toBeUndefined();
    expect(readLastCreate({ at: AT, outputs: [{ output: "x", name: "y", state: "nonsense" }] })).toBeUndefined();
  });

  it("shows no stale finish while a new Create runs", () => {
    const lc = lastCreateOf(allDone(), "demo", AT);
    const running = { outputs: [card("silver_notebook", { status: "running" })], refused: 0 } as unknown as ManyAnswer;
    for (const answer of [running, { outputs: [], refused: 0 } as unknown as ManyAnswer]) {
      const html = renderToStaticMarkup(React.createElement(ResultView, {
        answer, outputs: { version: 1, outputs: [], created: [], last_create: lc }, onOpen: (): void => undefined, mascotsOn: false,
      } as never));
      expect(html).not.toContain("Done: 9 of 9");
    }
  });

  it("follows an Update on one card", () => {
    const cards = allDone().map((c) => (c.output === "pipeline" ? { ...c, built_from: { words: "built from another plan" } as never, choices: ["update" as const] } : c));
    const lc = lastCreateOf(cards, "demo", AT);
    expect(banner(lc).tone).toBe("warning");
    expect(withCard(lc, card("pipeline", { dry_run: true }), "later")).toBe(lc);                     // the Update's dry run writes nothing
    const after = withCard(lc, card("pipeline", { would: "update" }), "2026-11-09T18:40:00Z");
    expect(banner(after).tone).toBe("success");
    expect(after.at).toBe("2026-11-09T18:40:00Z");
  });
});

