import { describe, expect, it } from "vitest";
import { sapFieldRows } from "./sourceWords";

describe("WB5 SAP fields in plain words", () => {
  it("lists the pack's field meanings table by table, nothing when there is no offer", () => {
    expect(sapFieldRows(undefined)).toEqual([]);
    const offer = { fields: { VBAP: [{ column: "MANDT", words: "SAP client" }], VBAK: [{ column: "KUNNR", words: "links to the customer" }] } };
    expect(sapFieldRows(offer as never)).toEqual([
      { table: "VBAK", column: "KUNNR", words: "links to the customer" },
      { table: "VBAP", column: "MANDT", words: "SAP client" },
    ]);
  });
});
