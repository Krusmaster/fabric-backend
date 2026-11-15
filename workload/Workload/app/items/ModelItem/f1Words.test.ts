// F1 (15 November 2026), docs/FINDINGS-13NOV.md: four texts a first tester read in the Model editor.
import { readFileSync } from "fs";
import { join } from "path";
import { describe, expect, it } from "vitest";
import { peopleWords } from "./productWords";
import { savedWords } from "./saveState";

const APP = join(__dirname, "..", "..");

describe("F1: the editor's small words", () => {
  it("counts one person or group in the singular", () => {
    expect(peopleWords(1)).toBe("1 person or group has a role in this workspace.");
    expect(peopleWords(3)).toBe("3 people and groups have a role in this workspace.");
  });

  it("says 1 try, not 1 tries, when the first save was not confirmed", () => {
    const one = savedWords({ state: "failed", at: "2026-11-12T09:06:00.000Z", tries: 1 }).words;
    expect(one).toContain("after 1 try (");
    expect(one).not.toContain("1 tries");
    expect(savedWords({ state: "failed", at: "2026-11-12T09:06:00.000Z", tries: 4 }).words).toContain("after 4 tries (");
  });

  it("names the page Krusgraph Model, not the starter kit's sample", () => {
    const html = readFileSync(join(APP, "index.html"), "utf8");
    expect(html).toContain("<title>Krusgraph Model</title>");
    expect(html).not.toContain("Sample Workload");
  });

  it("says which mirrored data is read in a sentence that parses", () => {
    const views = readFileSync(join(__dirname, "ModelItemViews.tsx"), "utf8");
    expect(views).toContain("including SAP through SAP Datasphere");
    expect(views).not.toContain("among it");
  });
});
