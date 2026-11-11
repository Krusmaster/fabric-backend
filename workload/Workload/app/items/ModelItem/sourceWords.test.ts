import { readFileSync } from "fs";
import { join } from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EmptyView } from "./ModelItemViews";
import { isReadOnly, PICKER_TYPES, restType, sapMark, SOURCE_TYPES, sourceButton, sourceLabel, sourceNotes, targetButton, targetLine, targetProblem } from "./sourceWords";

describe("n201: the sources the Model reads", () => {
  it("offers lakehouses, warehouses, SQL databases and mirrored databases", () => {
    expect(SOURCE_TYPES).toEqual(["Lakehouse", "Warehouse", "SQLDatabase", "MirroredDatabase"]);
    expect(sourceLabel("MirroredDatabase")).toBe("Mirrored database");
    expect(sourceButton({ itemType: "MirroredDatabase", displayName: "sap_mirror" })).toBe("Mirrored database: sap_mirror");
    expect(sourceButton(undefined)).toBe("Choose a source");
    expect(PICKER_TYPES).toContain("SQLDbNative");
    expect(restType("SQLDbNative")).toBe("SQLDatabase");
    expect(restType("MountedRelationalDatabase")).toBe("MirroredDatabase");
    expect(restType("Lakehouse")).toBe("Lakehouse");
  });

  it("treats everything but a lakehouse as read-only, and an item saved before n201 as a lakehouse", () => {
    expect(isReadOnly("MirroredDatabase")).toBe(true);
    expect(isReadOnly("Warehouse")).toBe(true);
    expect(isReadOnly("Lakehouse")).toBe(false);
    expect(isReadOnly(undefined)).toBe(false);
    expect(isReadOnly("TODO")).toBe(false);
  });

  it("says where a read-only source's build writes, the default included", () => {
    const src = { itemType: "MirroredDatabase", displayName: "sap_mirror" };
    expect(targetLine(src)).toContain("the first lakehouse of this workspace, unless you choose one");
    expect(targetLine(src, { itemId: "1", displayName: "lh" })).toContain("the lakehouse lh");
    expect(targetButton()).toContain("(default)");
    expect(targetProblem("ws", { workspaceId: "other", type: "Lakehouse" })).toContain("same workspace");
    expect(targetProblem("ws", { workspaceId: "ws", type: "Warehouse" })).toContain("lakehouse");
    expect(targetProblem("ws", { workspaceId: "ws", type: "Lakehouse" })).toBeUndefined();
  });

  it("marks the SAP pack's items with the pack and its sources, and nothing else", () => {
    const offer = {
      pack: "sap", label: "SAP pack", note: "These keys and links are from the SAP pack", mirroring: "Initial and Delta", licence: "Premium Outbound Integration",
      status: "documented, not verified against data", client_dropped: false, learn: {},
      items: { "key:VBAK": { from: "from the SAP pack", client: "MANDT", pack_table: "VBAK", text: "Sales document, header",
        sources: [{ title: "SAP Help Portal: Sales", url: "https://help.sap.com/docs/SAP_ERP" }] } },
    };
    const m = sapMark(offer, "key:VBAK")!;
    expect(m.text).toContain("from the SAP pack");
    expect(m.text).toContain("MANDT");
    expect(m.sources[0].url).toMatch(/^https:\/\//);
    expect(sapMark(offer, "key:orders")).toBeUndefined();
    expect(sapMark(undefined, "key:VBAK")).toBeUndefined();
    expect(sourceNotes({ kind: "MirroredDatabase", words: "read-only", mirroring: "Parquet" }, offer)).toEqual(
      ["read-only", "Parquet", offer.note, offer.licence]);
    expect(sourceNotes(undefined, undefined)).toEqual([]);
  });

  it("claims no certification, partnership or endorsement", () => {
    const text = readFileSync(join(__dirname, "sourceWords.ts"), "utf8").toLowerCase();
    for (const w of ["certified", "certification", "partner", "endorse"]) expect(text).not.toContain(w);
  });
});

describe("n201: the empty view of a mirrored source", () => {
  it("shows the source's kind and the target lakehouse, and no target for a lakehouse", () => {
    const base = { version: 1, platform: "fabric" as const, workspaceId: "ws", itemId: "md", displayName: "sap_mirror", schema: "dbo" };
    const props = { schema: "dbo", schemas: { loading: false }, onSchemaChange: () => {}, onChooseLakehouse: () => {}, onChooseTarget: () => {}, onReview: () => {} };
    const mirror = renderToStaticMarkup(React.createElement(EmptyView, { ...props, source: { ...base, itemType: "MirroredDatabase" } }));
    expect(mirror).toContain("Mirrored database: sap_mirror");
    expect(mirror).toContain("Target lakehouse: the first of this workspace (default)");
    const chosen = renderToStaticMarkup(React.createElement(EmptyView, { ...props, source: { ...base, itemType: "MirroredDatabase", target: { itemId: "lh", displayName: "demo_lh" } } }));
    expect(chosen).toContain("Target lakehouse: demo_lh");
    const lake = renderToStaticMarkup(React.createElement(EmptyView, { ...props, source: { ...base, itemType: "Lakehouse" } }));
    expect(lake).toContain("Lakehouse: sap_mirror");
    expect(lake).not.toContain("Target lakehouse");
  });
});
