// @vitest-environment jsdom
// ED1 (Gustav's editor test of 21 November 2026, shop_lh / shop): one sign-in, one approval, every other choice a visible
// default. The Choose step's decisions are counted on the rendered step, the way docs/SMOOTH/AUDIT.md section 9 counts
// them: every enabled checkbox, radio group, text box, dropdown, button and "Permissions" fold visible without opening
// anything; the Dry run button (the step's one action) and the folds More outputs and About are not counted.
// Before ED1 a build in a new workspace showed 16; now 4 (three ticks and Change).
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { OutputsView, ProductView, ReviewView } from "./ModelItemViews";
import { choicesFor, toRequests, choiceProblems } from "./buildWords";
import { JOINED, builtOn, notCheckedLine, productOwnerLine } from "./ed1Words";
import { placeLine, targetRequest } from "./buildPlace";
import type { CreatedItem, OutputChoice, SourceDefinition } from "./ModelItemDefinition";

const SRC: SourceDefinition = { version: 1, platform: "fabric", workspaceId: "ws-src", itemId: "lh-1", itemType: "Lakehouse", displayName: "shop_lh", schema: "shop" };
const MODEL_BEFORE: CreatedItem = { type: "SemanticModel", id: "m-1", name: "shop_lh_model", workspace: "ws-item", output: "semantic_model" };

function visibleDecisions(html: string): string[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const hidden = (el: Element) => {
    for (let p: Element | null = el.parentElement; p; p = p.parentElement)
      if (p.tagName === "DETAILS" && !p.hasAttribute("open") && el.closest("summary")?.parentElement !== p) return true;
    return false;
  };
  const out: string[] = [];
  doc.querySelectorAll("input, button, select, textarea, summary").forEach((el) => {
    if (hidden(el) || el.hasAttribute("disabled")) return;
    const text = (el.textContent ?? "").trim();
    if (el.tagName === "BUTTON" && text === "Dry run") return;
    if (el.tagName === "SUMMARY" && !/^Permissions/.test(text)) return;
    if (el.tagName === "INPUT" && (el as HTMLInputElement).type === "radio") {
      const key = `radio:${(el as HTMLInputElement).name}`;
      if (!out.includes(key)) out.push(key);
      return;
    }
    out.push(`${el.tagName.toLowerCase()}:${text || (el as HTMLInputElement).value}`);
  });
  return out;
}

/** The text a person reads: inline elements run together (as the browser shows them), blocks on their own line. */
function readText(html: string): string {
  return html
    .replace(/<\/?(p|div|section|li|ul|ol|h\d|details|summary|label|br|fieldset|legend)\b[^>]*>/g, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"');
}

function choose(opts: { source?: SourceDefinition; itemWs?: string; choices?: OutputChoice[]; created?: CreatedItem[]; open?: boolean } = {}) {
  const source = opts.source ?? SRC;
  const choices = opts.choices ?? choicesFor([], source.displayName, { displayName: "shop_model", created: [] });
  return renderToStaticMarkup(
    <OutputsView choices={choices} onChange={() => {}} created={opts.created ?? []} product={{ on: false, name: "" }} onProduct={() => {}}
      onOpen={() => {}} onPreview={() => {}} source={source} itemWorkspaceId={opts.itemWs ?? "ws-item"} onBuildIn={() => {}}
      onChooseTarget={() => {}} onPickModel={() => {}} changeOpen={opts.open} />
  );
}

const tick = (choices: OutputChoice[], kind: string, enabled: boolean) => choices.map((c) => (c.type === kind ? { ...c, enabled } : c));

describe("ED1 4: fewer decisions on the Choose step", () => {
  it("shows 4 decisions (from 16): the three ticks and one Change", () => {
    const d = visibleDecisions(choose());
    expect(d).toHaveLength(4);
    expect(d[0]).toBe("button:Change");
  });

  it("says where silver and gold go in one line, the same lakehouse the dry run sends", () => {
    const html = choose();
    expect(readText(html)).toContain("Silver and gold go to a lakehouse shop_lh_krusgraph in this workspace. Create makes it if it is not there yet.");
    expect(targetRequest(SRC, "ws-item").create_lakehouse).toBe("shop_lh_krusgraph");
    expect(html).not.toContain("choose one");
    expect(html).not.toContain("Make a lakehouse here");
    expect(html).not.toContain("first lakehouse");
  });

  it("names a chosen lakehouse, and the source itself in its own workspace", () => {
    const chosen = { ...SRC, target: { itemId: "lh-9", displayName: "sales_lh", workspaceId: "ws-item" } };
    expect(placeLine(chosen, "ws-item")).toBe("Silver and gold go to sales_lh in this workspace.");
    expect(targetRequest(chosen, "ws-item")).toEqual({ lakehouse: "lh-9", workspace: "ws-item", where: "item" });
    expect(placeLine(SRC, "ws-src")).toBe("Silver and gold go to shop_lh in this workspace.");
    expect(targetRequest(SRC, "ws-src").create_lakehouse).toBeUndefined();
  });

  it("shows the names from the rule and asks for none; Change makes them editable and shows the rest", () => {
    const shut = choose();
    expect(readText(shut)).toContain("Name: shop_lh_pipeline");
    expect(shut).not.toContain('value="shop_lh_pipeline"');
    expect(shut).not.toContain("Permissions");
    const open = choose({ open: true });
    expect(open).toContain('value="shop_lh_pipeline"');
    expect(open).toContain("Build in");
    expect(open).toContain("Name of the lakehouse Create makes");
    expect(open).toContain("Permissions");
    expect(open).toContain("Run once after Create");
  });
});

describe("ED1 4b: the report is built on the model by default", () => {
  const base = tick(choicesFor([], "shop_lh", { displayName: "shop_model", created: [] }), "report", true);

  it("says Built on: the semantic model above, and follows its name", () => {
    expect(readText(choose({ choices: base }))).toContain("Built on: shop_lh_model (the semantic model above)");
    const renamed = base.map((c) => (c.type === "semantic_model" ? { ...c, name: "sales_model" } : c));
    expect(builtOn("report", renamed, [])!.text).toBe("Built on: sales_model (the semantic model above)");
    expect(choose({ choices: base })).not.toContain("Empty: the semantic model chosen above");
  });

  it("without the model ticked: the model this item built before, else it says plainly the report needs one", () => {
    const noModel = tick(base, "semantic_model", false);
    expect(builtOn("report", noModel, [MODEL_BEFORE])!.text).toBe("Built on: shop_lh_model (the semantic model this item built before)");
    expect(toRequests(noModel, [MODEL_BEFORE]).find((r) => r.kind === "report")).toMatchObject({ model: "shop_lh_model" });
    expect(choiceProblems(noModel, [MODEL_BEFORE])).toEqual([]);
    expect(builtOn("report", noModel, [])).toMatchObject({ missing: true });
    expect(choiceProblems(noModel, [])).toContain("A report needs a semantic model: tick Semantic model, or choose one under Change.");
  });

  it("a model picked under Change (no free text box), and the other dependants say what they are built on", () => {
    const open = choose({ choices: base, open: true });
    expect(open).toContain("Choose a semantic model in this workspace");
    expect(open).not.toMatch(/<input[^>]*aria-label="Built on"/);
    const picked = base.map((c) => (c.type === "report" ? { ...c, model: "finance_model" } : c));
    expect(builtOn("report", picked, [])!.text).toBe("Built on: finance_model (a semantic model in this workspace)");
    expect(builtOn("data_agent", base, [])!.text).toBe("Built on: the silver tables this build writes");
    expect(builtOn("graphql", base, [], "shop_lh")!.text).toBe("Built on: the tables of shop_lh");
    expect(builtOn("ontology", base, [])!.text).toBe("Built on: the silver tables this build writes");
  });
});

describe("ED1 2: no sentence runs into the next", () => {
  it("in every Choose state, open and shut, in this and the source's workspace", () => {
    const all = tick(tick(tick(choicesFor([], "shop_lh", { displayName: "shop_model", created: [] }), "report", true), "graphql", true), "ontology", true);
    for (const html of [choose(), choose({ open: true }), choose({ itemWs: "ws-src" }), choose({ itemWs: "ws-src", open: true }),
      choose({ choices: all, open: true }), choose({ source: { ...SRC, buildIn: "source" }, open: true })]) {
      const text = readText(html);
      const m = text.match(JOINED);
      expect(m ? JSON.stringify(text.slice(Math.max(0, m.index! - 60), m.index! + 40)) : "").toBe("");
    }
  });
  it("finds the join Gustav saw", () => {
    expect("written to a lakehouse of this workspace.Silver and gold go to").toMatch(JOINED);
    expect("e.g. a lakehouse. Silver").not.toMatch(JOINED);
  });
});

describe("ED1 3: no '?' placeholder on the data product card", () => {
  it("omits the plan until it is known", () => {
    expect(productOwnerLine({ owner: "Data team", plan: {} })).toBe("Owner: Data team.");
    expect(productOwnerLine({ owner: "Data team", plan: { plan_id: "p-7" } })).toBe("Owner: Data team. Plan p-7.");
    const html = renderToStaticMarkup(<ProductView product={{ name: "shop", owner: "Data team", plan: {}, items: [], domains: [] } as never} />);
    expect(readText(html)).not.toContain("?");
    expect(readText(html)).toContain("Owner: Data team.");
  });
});

describe("ED1 5: keys and links", () => {
  const item = (id: string, check: unknown, extra: Record<string, unknown> = {}) =>
    ({ id, type: "key", table: id, columns: ["id"], rule: "K1", review: "proposed", check, ...extra });
  const review = (items: unknown[]) => ({ format: "krusgraph-review", version: 1, plan_id: "p1", source: { schema: "shop" }, items, open_questions: [] as unknown[] });
  const view = (r: unknown) => renderToStaticMarkup(
    <ReviewView review={r as never} answered={{}} map={undefined as never} source={SRC} onDecide={() => {}} onAcceptAll={() => {}}
      onCheck={() => {}} onChoice={() => {}} mascotsOn={false} onToggleMascots={() => {}} checking={false} sap={undefined as never} />
  );

  it("hides Accept all when nothing passed", () => {
    const html = view(review([item("orders", { status: "not_checked" })]));
    expect(html).not.toContain("Accept all that passed the check (0)");
    expect(html).not.toContain("Accept all (0)");
    expect(view(review([item("orders", { status: "passed", result: { rows: 5 } })]))).toContain("Accept all that passed the check (1)");
  });

  it("says which items were not checked and why, in one line", () => {
    const items = [
      item("orders", { status: "passed", result: { rows: 5 } }),
      item("audit_log", { status: "not_checked", result: { rows: 0 } }),
      { id: "r1", type: "relationship", source: "orders", columns: ["promo_id"], target: "promos", rule: "R1", check: { status: "not_checked", result: { rows_with_value: 0, orphans: 0 } } },
      item("customers", { status: "stale", stale_because: "customers changed since the check" }),
    ];
    const line = notCheckedLine(items as never, 1)!;
    expect(line.text).toBe("Not checked: the key of audit_log (audit_log has no rows); orders.promo_id → promos (no row has a value in the column); the key of customers (customers changed since the check).");
    expect(line.again).toBe(true);
    expect(notCheckedLine(items.slice(0, 3) as never, 1)!.again).toBe(false);
    expect(notCheckedLine(items as never, 0)).toBeUndefined();
    expect(readText(view(review(items)))).toContain("Not checked: the key of audit_log (audit_log has no rows)");
  });
});
