import { describe, expect, it } from "vitest";
import { BuildCard } from "./engineClient";
import { OutputChoice } from "./ModelItemDefinition";
import {
  AppOptions, EDIT_TITLE, apiLines, chartTypes, designLines, editHref, featureOff, movePage, nothingTicked, packageHref, pagesInOrder,
  preflightWords, setAccent, setChartType, ticked, toggle, withAppChoices,
} from "./appWords";
import { toRequests } from "./buildWords";

const card = (answer: Record<string, any>, extra: Partial<BuildCard> = {}): BuildCard => ({
  output: "rayfin_app", label: "App (Rayfin, preview)", type: "AppBackend", name: "shop_app", dry_run: true, would: "create",
  updates_in_place: false, permissions: { needs: ["Item.ReadWrite.All"], missing: null, execute: "" }, answer, ...extra,
});

describe("n181: the App (Rayfin, preview) card", () => {
  it("shows the admin card when App items are off, never a generic error", () => {
    const off = featureOff(card({ error: "Fabric App items are turned off", kind: "feature_disabled", setting: "Enable Fabric App Items (preview)",
      where: "Admin portal → Tenant settings → Microsoft Fabric", admin_steps: ["a", "b"] }));
    expect(off?.setting).toBe("Enable Fabric App Items (preview)");
    expect(off?.steps).toEqual(["a", "b"]);
    expect(featureOff(card({ dry_run: true }))).toBeUndefined();
    expect(preflightWords({ status: "on", note: "On for the organisation." })).toBe("Fabric App items are on. On for the organisation.");
    expect(preflightWords({ status: "unknown", reason: "not a Fabric administrator" })).toContain("Could not check");
  });

  it("keeps the ticks in the outputs and sends them", () => {
    const c = card({ chosen: { kpis: ["rows:orders"], tables: [], charts: [] } });
    let t = ticked(c);
    expect(t.kpis).toEqual(["rows:orders"]);
    t = toggle(t, "charts", "chart:x", true);
    t = toggle(t, "kpis", "rows:orders", false);
    expect(t).toEqual({ kpis: [], tables: [], charts: ["chart:x"] });
    expect(nothingTicked({ kpis: [], tables: [], charts: [] })).toBe(true);
    const choices: OutputChoice[] = [{ type: "rayfin_app", name: "shop_app", enabled: true }, { type: "graphql", name: "shop_api", enabled: false }];
    const stored = withAppChoices(choices, t);
    expect(stored[0].app).toEqual(t);
    expect(ticked(c, stored[0].app)).toEqual(t);
    expect(toRequests(stored)).toEqual([{ kind: "rayfin_app", name: "shop_app", app: t }]);
  });

  it("says the API is read-only and lists every link", () => {
    const lines = apiLines({ connector: "shop", connector_type: "fabric-sqlanalytics", operations: ["read"], read_only: true, mutations: [],
      types: [{ type: "orders", queries: ["Query", "Query_by_pk"] }],
      links: [{ from: "orders.ship_to_id", to: "addresses.address_id", rule: "R5" }], note: "" });
    expect(lines[0]).toContain("read-only: queries only, no mutations");
    expect(lines).toContain("orders.ship_to_id → addresses.address_id (R5)");
    expect(packageHref({ zip_base64: "UEs=" })).toBe("data:application/zip;base64,UEs=");
  });
});

describe("n189: more choices without AI, and Change the app yourself", () => {
  const opts: AppOptions = {
    kpis: [{ id: "rows:orders", label: "Rows in orders", default: true, why: "" }],
    tables: [{ id: "table:orders", label: "orders", default: true, why: "" }, { id: "table:products", label: "products", default: true, why: "" }],
    charts: [
      { id: "chart:cat", label: "Total quantity by categories (name)", default: true, why: "", kind: "category", types: ["bar", "table"], type: "bar" },
      { id: "chart:time", label: "Total quantity by month (orders.order_date)", default: true, why: "", kind: "time", types: ["line", "bar", "table"], type: "line" },
    ],
    filters: [{ id: "filter:categories.name", label: "Categories", default: true, why: "" }],
    pages: [{ id: "overview", label: "Overview (key figures and charts)" }, { id: "table:orders", label: "orders" }, { id: "table:products", label: "products" }],
    accents: [{ id: "blue", label: "Blue", light: "#0f6cbd", dark: "#479ef5" }, { id: "teal", label: "Teal", light: "#03787c", dark: "#3fbfc4" }],
  };
  const chosen = { kpis: ["rows:orders"], tables: ["table:orders", "table:products"], charts: ["chart:cat", "chart:time"],
    filters: ["filter:categories.name"], chart_types: { "chart:cat": "bar", "chart:time": "line" }, page_order: ["overview", "table:orders", "table:products"], accent: "blue" };

  it("offers each ticked chart's types, and keeps the choice", () => {
    let t = ticked(card({ chosen }));
    expect(chartTypes(opts, t).map((c) => [c.id, c.type, c.types])).toEqual([["chart:cat", "bar", ["bar", "table"]], ["chart:time", "line", ["line", "bar", "table"]]]);
    t = setChartType(t, "chart:cat", "table");
    expect(chartTypes(opts, t)[0].type).toBe("table");
    expect(chartTypes(opts, setChartType(t, "chart:cat", "line"))[0].type).toBe("bar");   // a category chart has no line
  });

  it("moves pages, ticks filters and picks an accent; all of it goes into outputs.json and the request", () => {
    let t = ticked(card({ chosen }));
    t = movePage(opts, t, "table:products", -1);
    expect(pagesInOrder(opts, t).map((p) => p.id)).toEqual(["overview", "table:products", "table:orders"]);
    t = movePage(opts, t, "overview", -1);                                              // already first: unchanged
    expect(t.page_order).toEqual(["overview", "table:products", "table:orders"]);
    t = toggle(t, "filters", "filter:categories.name", false);
    t = setAccent(t, "teal");
    const stored = withAppChoices([{ type: "rayfin_app", name: "shop_app", enabled: true }], t);
    expect(stored[0].app).toMatchObject({ filters: [], accent: "teal", page_order: ["overview", "table:products", "table:orders"] });
    expect(toRequests(stored)[0].app).toEqual(t);
    expect(pagesInOrder(opts, { kpis: [], charts: [], tables: ["table:orders"] }).map((p) => p.id)).toEqual(["table:orders"]);
  });

  it("an outputs.json from before n189 shows the dry run's filters, types, order and accent", () => {
    const t = ticked(card({ chosen }), { kpis: ["rows:orders"], tables: [], charts: ["chart:cat"] });
    expect(t.kpis).toEqual(["rows:orders"]);
    expect(t.filters).toEqual(["filter:categories.name"]);
    expect(t.accent).toBe("blue");
  });

  it("the dry run says the look and the layout, and links EDIT-WITH-AI.md", () => {
    const lines = designLines({ accent: "teal", accent_colours: { light: "#03787c", dark: "#3fbfc4" }, page_order: ["Overview", "orders"],
      charts: [{ id: "chart:cat", label: "Total quantity by categories (name)", type: "table" }],
      filters: [{ id: "filter:orders.order_date", label: "Order date", kind: "dates", reaches: ["order_items", "orders"] }],
      last_refresh: null, look: "Fluent-like" });
    expect(lines).toContain("Accent: teal (#03787c in light, #3fbfc4 in dark)");
    expect(lines).toContain("Pages, in this order: Overview, orders");
    expect(lines).toContain("Total quantity by categories (name): table chart");
    expect(lines).toContain("Filter Order date (a date range): applies to order_items, orders");
    expect(lines.some((l) => l.startsWith("Last refresh: when the page read the data"))).toBe(true);
    expect(EDIT_TITLE).toBe("Change the app yourself");
    const href = editHref({ markdown: "# Change shop_app yourself\nnpx rayfin up" });
    expect(href?.startsWith("data:text/markdown;charset=utf-8,")).toBe(true);
    expect(decodeURIComponent(href!.split(",")[1])).toContain("npx rayfin up");
    expect(editHref(undefined)).toBeUndefined();
  });
});
