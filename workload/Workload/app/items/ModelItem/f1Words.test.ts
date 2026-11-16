// F1 (docs/FINDINGS-13NOV.md): four texts a first user reads in the Model editor.
import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";
import { roleLine } from "./DataProductView";
import { CHOOSE_SOURCE_WORDS } from "./ModelItemViews";
import { savedWords } from "./saveState";

describe("F1: words a first user reads", () => {
  it("counts one person or group in the singular", () => {
    expect(roleLine(1)).toBe("1 person or group has a role in this workspace.");
    expect(roleLine(2)).toBe("2 people and groups have a role in this workspace.");
  });

  it("says 1 try and 4 tries", () => {
    const at = "2026-11-12T09:06:00Z";
    expect(savedWords({ state: "failed", at, tries: 1 }).words).toContain("after 1 try (");
    expect(savedWords({ state: "failed", at, tries: 4 }).words).toContain("after 4 tries (");
  });

  it("names the page after the item, not after the starter kit's sample", () => {
    const html = fs.readFileSync(path.resolve(__dirname, "../../index.html"), "utf-8");
    expect(html).toContain("<title>Krusgraph Model</title>");
    expect(html).not.toContain("Sample Workload");
  });

  it("says where mirrored data may come from in plain words", () => {
    expect(CHOOSE_SOURCE_WORDS).toContain("for example SAP through SAP Datasphere");
    expect(CHOOSE_SOURCE_WORDS).not.toContain("among it");
    expect(CHOOSE_SOURCE_WORDS).toContain("Nothing is created until you choose Create.");
  });
});
