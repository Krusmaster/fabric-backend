// n168: the hosted editor takes its engine scope from the meta tag the server writes into index.html
// (fabric_backend/workload_host.py) when the build carries none.
import { describe, expect, it } from "vitest";
import { engineScope } from "./engineClient";

function docWith(content: string | null) {
  return {
    querySelector: (selector: string) =>
      selector === 'meta[name="krusgraph-engine-scope"]' && content !== null
        ? ({ getAttribute: (name: string) => (name === "content" ? content : null) } as unknown as Element)
        : null,
  };
}

describe("engineScope", () => {
  it("prefers the scope the build was made with", () => {
    expect(engineScope("api://dev/x/user_impersonation", docWith("https://other/user_impersonation"))).toBe(
      "api://dev/x/user_impersonation"
    );
  });
  it("falls back to the hosting server's meta tag", () => {
    expect(engineScope("", docWith(" https://workload.krusgraph.com/x/user_impersonation "))).toBe(
      "https://workload.krusgraph.com/x/user_impersonation"
    );
  });
  it("is empty with neither", () => {
    expect(engineScope(undefined, docWith(null))).toBe("");
    expect(engineScope(undefined, undefined)).toBe("");
  });
});
