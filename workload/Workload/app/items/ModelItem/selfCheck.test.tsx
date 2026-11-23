import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SelfCheck, selfCheckLine } from "./SelfCheck";

describe("WB9 self-check", () => {
  it("names what is missing, or says nothing is", () => {
    expect(selfCheckLine({ checks: [{ id: "consent", state: "ok", words: "" }, { id: "tenant_setting", state: "unknown", words: "" }] }))
      .toBe("Nothing is missing: choose a source to start.");
    expect(selfCheckLine({ checks: [{ id: "capacity", state: "missing", words: "" }, { id: "lakehouse", state: "missing", words: "" }] }))
      .toBe("2 things to fix first: Fabric capacity, A lakehouse.");
    expect(selfCheckLine({ error: "x" })).toBe("");
  });
  it("shows nothing without a workspace to check", () => {
    expect(renderToStaticMarkup(<SelfCheck />)).toBe("");
    expect(renderToStaticMarkup(<SelfCheck send={async () => ({})} />)).toContain("Run the self-check");
  });
});
