// n198: the Data product page rendered in every state (DataProductView.tsx, from the fake outputs.json of
// productPage.fixture.ts). The pages are kept in tests/fixtures/n198/, which tests/test_n198_browser.py opens in Chromium
// at 375 and 1280 px, light and dark, by keyboard. This test fails when they are stale: run `N198_WRITE=1 npm test`.
import * as fs from "fs";
import * as path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DataProductProps, DataProductView } from "./DataProductView";
import {
  DELETED, DELETE_DRY_RUN, FRESH, LEFTOVERS, LEFTOVERS_UNREAD, OUTPUTS, SOFT_DRY_RUN, STATUS, UPDATES,
} from "./productPage.fixture";
import { NOT_CHECKED } from "./productWords";

const DIR = path.resolve(process.cwd(), "../../tests/fixtures/n198");
const base: DataProductProps = { productName: "Shop sales", outputs: OUTPUTS, status: STATUS, health: NOT_CHECKED };

export const PAGES: Record<string, DataProductProps> = {
  states: base,
  fresh: { productName: "demo_model", outputs: FRESH },
  update: { ...base, updates: UPDATES },
  soft: { ...base, retire: SOFT_DRY_RUN },
  "delete-dry-run": { ...base, retire: DELETE_DRY_RUN, initialTyped: "shop sales" },
  "delete-typed": { ...base, retire: DELETE_DRY_RUN, initialTyped: "Shop sales", initialChosen: [] },
  deleted: { ...base, retire: DELETED },
  leftovers: { ...base, leftovers: LEFTOVERS },
  "leftovers-unread": { ...base, leftovers: LEFTOVERS_UNREAD },
};

function page(name: string, props: DataProductProps): string {
  const body = renderToStaticMarkup(React.createElement(DataProductView, props));
  return `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">` +
    `<title>Data product page: ${name}</title><style>:root{color-scheme:light dark}body{margin:0;background:Canvas}</style></head>` +
    `<body>${body}</body></html>\n`;
}

describe("the Data product page, rendered", () => {
  for (const [name, props] of Object.entries(PAGES)) {
    it(`${name} is the page kept in tests/fixtures/n198`, () => {
      const html = page(name, props);
      const file = path.join(DIR, `${name}.html`);
      if (process.env.N198_WRITE) {
        fs.mkdirSync(DIR, { recursive: true });
        fs.writeFileSync(file, html);
      }
      expect(fs.existsSync(file) ? fs.readFileSync(file, "utf8") : "(missing: run N198_WRITE=1 npm test)").toBe(html);
    });
  }

  it("says every state in words, and Delete waits for the typed name", () => {
    const states = page("states", PAGES.states);
    for (const word of ["Built", "Pending", "Failed", "Changed outside Krusgraph", "Missing", "Removed", "Health: not checked yet",
      "Plan id: plan-0123abcd", "Last pipeline run: succeeded"]) expect(states).toContain(word);
    const wrong = page("x", PAGES["delete-dry-run"]);
    expect(wrong).toMatch(/<button type="button" class="kg-dp-danger" disabled="">Delete 4 item\(s\) from Fabric<\/button>/);
    const right = page("x", PAGES["delete-typed"]);
    expect(right).toMatch(/<button type="button" class="kg-dp-danger">Delete 4 item\(s\) from Fabric<\/button>/);
    expect(page("x", PAGES.fresh)).toContain("Nobody is the owner yet");
  });
});
