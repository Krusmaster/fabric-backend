// W4 (Gustav's tenant test, 24 November 2026): on Manage (the Data product page), items Retire deleted are folded under
// "Removed (n)", closed by default, and no longer listed at full weight among the live items.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DataProductView } from "./DataProductView";
import { OUTPUTS, STATUS } from "./productPage.fixture";
import { removedLabel, rowsOf, splitRemoved } from "./productWords";

describe("removed items on Manage", () => {
  it("splits the rows into live and removed, keeping their order", () => {
    const rows = rowsOf(OUTPUTS, STATUS);
    const { live, removed } = splitRemoved(rows);
    expect(removed.map((r) => r.name)).toEqual(["demo_lh_report_2"]);
    expect(live.every((r) => r.state !== "removed")).toBe(true);
    expect(live.length + removed.length).toBe(rows.length);
    expect(removedLabel(1)).toBe("Removed (1)");
  });

  it("renders the removed rows inside a closed disclosure after the live rows", () => {
    const html = renderToStaticMarkup(React.createElement(DataProductView, { productName: "Shop sales", outputs: OUTPUTS, status: STATUS }));
    const fold = html.indexOf("<details data-removed=\"\"><summary>Removed (1)</summary>");
    expect(fold).toBeGreaterThan(0);
    expect(html).not.toMatch(/<details data-removed="" open/);
    const removedRow = html.indexOf('data-state="removed"');
    expect(removedRow).toBeGreaterThan(fold);
    for (const state of ["built", "missing", "changed_outside", "pending", "failed"]) {
      expect(html.indexOf(`data-state="${state}"`)).toBeLessThan(fold);
    }
  });

  it("shows no disclosure when nothing was removed", () => {
    const html = renderToStaticMarkup(React.createElement(DataProductView, {
      productName: "Shop sales", outputs: { ...OUTPUTS, removed: [] }, status: STATUS }));
    expect(html).not.toContain("data-removed");
  });
});
