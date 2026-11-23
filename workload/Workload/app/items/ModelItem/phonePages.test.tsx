// n225: the editor's own pages on a phone. The founder's phone test in Fabric of 12 November 2026: at 375-412 px the
// editor rendered at desktop width and its text was tiny. Here the Review, Choose what to build (with the App card) and
// Data product pages are rendered with Fluent's styles (server-side, Griffel's style elements), the theme's tokens and
// the editor's own ModelItem.scss, into tests/fixtures/n225/. tests/test_n225_phone.py opens them in Chromium at 375,
// 412 and 1280 px (tests/n225_browser.js): no horizontal scroll, body text at least 14 px, tap targets at least 44 px.
// This test fails when the pages are stale: run `N225_WRITE=1 npm test`.
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as sass from "sass";
import {
  FluentProvider, RendererProvider, SSRProvider, createDOMRenderer, renderToStyleElements, webLightTheme,
} from "@fluentui/react-components";
import { describe, expect, it } from "vitest";
import { OutputsView, ReviewView } from "./ModelItemViews";
import { DataProductView } from "./DataProductView";
import { choicesFor } from "./buildWords";
import { ReviewFile, ReviewItem, SourceDefinition, OutputsDefinition } from "./ModelItemDefinition";
import { OUTPUTS, STATUS } from "./productPage.fixture";
import { APP_BEFORE_CREATE } from "./appWords";
import { CatalogView } from "./CatalogPanel";
import { CopilotStepView } from "./CopilotStep";
import type { CopilotAnswer } from "./copilotWords";
import type { CatalogAnswer } from "./catalogWords";

const ROOT = path.resolve(process.cwd(), "../..");
const DIR = path.join(ROOT, "tests/fixtures/n225");
const SCSS = sass.compile(path.resolve(process.cwd(), "app/items/ModelItem/ModelItem.scss")).css;
const TOKENS = `:root{${Object.entries(webLightTheme).map(([k, v]) => `--${k}:${v}`).join(";")}}`;

const LONG = "sales_order_line_items_with_a_very_long_name_from_the_erp";
const SOURCE: SourceDefinition = {
  version: 1, platform: "fabric", workspaceId: "0f0f0f0f-0000-4000-8000-000000000001", itemId: "0f0f0f0f-0000-4000-8000-000000000002",
  itemType: "Lakehouse", displayName: "demo_lh_with_a_long_lakehouse_name", schema: "shop",
};
const link = (id: string, source: string, target: string, review: ReviewItem["review"]): ReviewItem => ({
  id, type: "relationship", rule: "R1", columns: [`${target}_id`], source, target, target_columns: [`${target}_id`], review,
  check: { status: "passed", result: { orphans: 0, rows_with_value: 1200 } },
});
const REVIEW = {
  format: "krusgraph-review", version: 3, plan_id: "plan-0123abcd", source: { platform: "fabric", schema: "shop" },
  items: [
    { id: "k1", type: "key", rule: "K1", columns: ["order_id"], table: "orders", review: "accepted", check: { status: "passed", result: { duplicates: 0 } } },
    { id: "k2", type: "key", rule: "K2", columns: ["line_id", "order_id"], table: LONG, review: "proposed" },
    link("r1", "orders", "customers", "accepted"),
    link("r2", LONG, "orders", "proposed"),
    link("r3", "returns", "orders", "open"),
  ],
} as unknown as ReviewFile;

/** n225: a Data product whose item also built from an older plan, a save Fabric did not confirm, an unsaved id. */
const TWO_PLANS: OutputsDefinition = {
  ...OUTPUTS,
  plan: { plan_id: "plan-0123abcd", at: "2026-11-12T09:05:00.000Z" },
  created: [...OUTPUTS.created, { id: "00000000-0000-4000-8000-000000000041", type: "Notebook", name: `old_${LONG}`, workspace: SOURCE.workspaceId,
    output: "silver_notebook", plan: { plan_id: "plan-99999999" } }],
  last_create: { ...OUTPUTS.last_create!, outputs: [...OUTPUTS.last_create!.outputs,
    { output: "data_agent", label: "Data agent", name: "demo_lh_agent_2", state: "created" }].filter((o) => o.state !== "failed") },
};

const noop = (): void => undefined;

function page(title: string, el: React.ReactElement): string {
  const renderer = createDOMRenderer();
  const body = renderToStaticMarkup(
    <RendererProvider renderer={renderer}>
      <SSRProvider>
        <FluentProvider theme={webLightTheme}>{el}</FluentProvider>
      </SSRProvider>
    </RendererProvider>,
  );
  const styles = renderToStaticMarkup(<>{renderToStyleElements(renderer)}</>);
  return `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">` +
    `<title>Krusgraph Model on a phone: ${title}</title><style>${TOKENS}</style>${styles}<style>${SCSS}</style>` +
    `<style>body{margin:0;background:#fff;font-family:"Segoe UI",system-ui,sans-serif}</style></head><body>${body}</body></html>\n`;
}

/** CA1: the catalog step after a dry run, with long names, as a phone shows it. */
const CATALOG: CatalogAnswer = {
  summary: "1 data product card(s); as you: 1 description(s) and tags on 1 item(s) to write; for others: 3 request(s) in the handover files",
  products: [{
    name: "Shop sales", slug: "shop_sales", tables: ["orders", LONG],
    description: `Data product Shop sales (shop): Orders, ${LONG}. Checked by Krusgraph: 2 of 2 keys unique, 0 orphan rows over 1 link, checked 17 Nov 2026.`,
    owner: "not chosen yet", domain: { proposed: "Shop sales", why: "orders is the table the others point at most", note: "a proposal" },
    tags: ["Krusgraph", "Shop sales"], contract: { format: "ODCS v3.2.0", status: "draft", file: "contracts/shop_sales.odcs.yaml" },
    glossary: [{ term: "Orders", definition: "One row of shop.orders; identified by order_id (rule K1)." }],
    evidence: { counted: true, line: "2 of 2 keys unique, 0 orphan rows over 1 link, checked 17 Nov 2026" },
    quality_rules: [{ id: "orders_key_unique", kind: "unique_key", says: "orders.order_id has no duplicates and no empty values", status: "proven", sql: "" }],
  }],
  diff: [
    { item: `${LONG}_model`, type: "SemanticModel", field: "description", before: "", after: `Data product Shop sales (shop): Orders, ${LONG}. Checked by Krusgraph: 2 of 2 keys unique.`, action: "write" },
    { item: SOURCE.displayName, type: "Lakehouse", field: "tags", before: [], after: ["Krusgraph"], action: "write" },
    { item: SOURCE.displayName, type: "Lakehouse", field: "description", before: null, after: "Data product Shop sales", action: "kept", why: "the item has its own description and Krusgraph did not build it" },
  ],
  confirm: "catalog-0123abcd", writable: false,
  handover: {
    requests: [{ step: "Create the tags", by: "fabric_admin", method: "POST", url: "x" },
      { step: "Assign the workspace to the domain", by: "workspace_admin", method: "POST", url: "x" },
      { step: "Endorse Shop sales", by: "reviewer", method: null, url: null }],
    approvals: [], files: { "handover/fabric-admin.md": "#", "handover/endorsement.md": "#", "handover/purview.json": "{}" },
  },
  note: "Nothing was created or changed in Fabric.",
};

/** W3: the Copilot step's dry run, with a long agent name. */
const COPILOT: CopilotAnswer = {
  name: `${LONG}_agent`, workspace: "11111111-2222-4333-8444-555555555555", agent_id: "dddddddd-0000-4000-8000-0000000000a1",
  published: false, confirm: "agent-0123abcd", missing: 1, unverified: 2,
  preflight_words: "Missing for Microsoft 365 Copilot: Paid capacity, F2 or higher (or P1 or higher) (the workspace is on a trial capacity (FT1))",
  requirements: [
    { requirement: "Paid capacity, F2 or higher (or P1 or higher)", status: "missing", detail: "the workspace is on a trial capacity (FT1)",
      doc: "https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot" },
    { requirement: "Microsoft Copilot licence (or Office 365 commercial subscription) and a user licence per person", status: "unverified",
      detail: "Unverified: licences are not readable through Fabric's API", doc: "https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot" },
  ],
  plan: [
    { step: `Publish ${LONG}_agent in Fabric, so people with access to the workspace can use it`, by: "Krusgraph, as you",
      how: "Publish data agent (POST .../dataAgents/{id}/staging/publish)", scope: "Item.ReadWrite.All (or DataAgent.ReadWrite.All)" },
    { step: `Make ${LONG}_agent available in Microsoft 365 Copilot`, by: "you, in Fabric",
      how: "In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish. Krusgraph cannot do this step: Microsoft documents no API for it.", scope: null },
  ],
  copilot_step: "In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish. Krusgraph cannot do this step: Microsoft documents no API for it.",
};

export const PAGES: Record<string, () => React.ReactElement> = {
  review: () => (
    <ReviewView source={SOURCE} review={REVIEW} answered={{}} checking={false} mascotsOn={false} onToggleMascots={noop}
      onDecide={noop} onAcceptAll={noop} onCheck={noop} onChoice={noop} />
  ),
  outputs: () => {
    const choices = choicesFor([], SOURCE.displayName).map((c) => (c.type === "silver_notebook" ? { ...c, enabled: true, name: `${LONG}_silver` } : c));
    return (
      <OutputsView choices={choices} onChange={noop} created={[]} product={{ on: true, name: "Shop sales" }} onProduct={noop}
        onOpen={noop} onPreview={noop} />
    );
  },
  product: () => (
    <DataProductView productName="Shop sales" outputs={TWO_PLANS} status={STATUS}
      health="Health: not checked since this Create (2026-11-12 09:05 UTC). The latest result is from run r-17, checked 2026-11-11 19:23 UTC: red. 7 failed in the latest run."
      saved={{ state: "failed", at: "2026-11-12T09:06:00.000Z", tries: 4 }} />
  ),
  catalog: () => (
    <CatalogView answer={CATALOG} busy={false} owner="" checked={false} onOwner={noop} onPrepare={noop} onChecked={noop} onWrite={noop} />
  ),
  // W3: writing on: the box and Write under Prepare again, after the summary and the link to the changes
  "catalog-gate": () => (
    <CatalogView answer={{ ...CATALOG, writable: true }} busy={false} owner="" checked={false} onOwner={noop} onPrepare={noop} onChecked={noop} onWrite={noop} />
  ),
  // W3: after the write: the cheer, the receipt and the button to the workspace
  "catalog-written": () => (
    <CatalogView answer={{ ...CATALOG, writable: true, workspace: "11111111-2222-4333-8444-555555555555",
      results: [{ item: `${LONG}_model`, field: "description", ok: true, status: 200 }, { item: SOURCE.displayName, field: "tags", ok: true, status: 200 }] }}
      written busy={false} owner="" checked={false} onOwner={noop} onPrepare={noop} onChecked={noop} onWrite={noop} />
  ),
  // W3: the data agent's Make it available in Copilot, after its dry run
  copilot: () => <CopilotStepView answer={COPILOT} busy={false} ticked={false} onPrepare={noop} onTicked={noop} onPublish={noop} />,
};

describe("the editor's pages on a phone, rendered", () => {
  for (const [name, el] of Object.entries(PAGES)) {
    it(`${name} is the page kept in tests/fixtures/n225`, () => {
      const html = page(name, el());
      const file = path.join(DIR, `${name}.html`);
      if (process.env.N225_WRITE) {
        fs.mkdirSync(DIR, { recursive: true });
        fs.writeFileSync(file, html);
      }
      expect(fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "(missing: run N225_WRITE=1 npm test)").toBe(html);
    });
  }

  it("the App card says what Create gives before Create, and the App is not ticked", () => {
    const html = page("outputs", PAGES.outputs());
    expect(html).toContain(APP_BEFORE_CREATE.replace(/'/g, "&#x27;"));
    expect(choicesFor([], "demo_lh").find((c) => c.type === "rayfin_app")?.enabled).toBe(false);
  });

  it("the Data product page lists this plan's items apart from another plan's, and says Not saved", () => {
    const html = page("product", PAGES.product());
    expect(html).toContain("Not saved: Fabric did not confirm the save after 4 tries");
    expect(html).toContain("Save again");
    expect(html).toContain("1 item(s) this item built from another plan: not part of this data product");
    expect(html).toContain("demo_lh_agent_2");
    expect(html).toContain("Plan id: plan-0123abcd (the plan of the Create of 2026-11-12 09:05 UTC).");
  });
});
