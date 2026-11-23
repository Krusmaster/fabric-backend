import { describe, expect, it } from "vitest";
import { CSN_MAX_BYTES, entityCount, readCsn } from "./csnUpload";

const CSN = { $version: "2.0", definitions: { "sales.Orders": { kind: "entity", elements: { ID: { key: true } } }, T: { kind: "type" } } };

describe("WB5 CSN upload", () => {
  it("reads a CSN export", () => {
    const r = readCsn("orders.json", 100, JSON.stringify(CSN));
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.value.name).toBe("orders.json");
      expect(entityCount(r.value.csn)).toBe(1);
    }
  });
  it("says why a file is refused, in one sentence", () => {
    expect(readCsn("x.txt", 10, "{}")).toEqual({ ok: false, error: expect.stringContaining(".json or .csn") });
    expect(readCsn("x.json", CSN_MAX_BYTES + 1, "{}")).toEqual({ ok: false, error: expect.stringContaining("larger than 5 MB") });
    expect(readCsn("x.json", 5, "{not json")).toEqual({ ok: false, error: "The file is not valid JSON." });
    expect(readCsn("x.json", 5, JSON.stringify({ a: 1 }))).toEqual({ ok: false, error: expect.stringContaining("no 'definitions'") });
    expect(readCsn("x.json", 5, JSON.stringify({ definitions: {} }))).toEqual({ ok: false, error: expect.stringContaining("not recognised as CSN") });
  });
  it("accepts a byte-order mark and the Interop marker", () => {
    expect(readCsn("x.csn", 5, "﻿" + JSON.stringify({ csnInteropEffective: "1.0", definitions: {} })).ok).toBe(true);
  });
});
