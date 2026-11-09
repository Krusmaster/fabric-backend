// n168: the hosted editor takes its engine scope from the meta tag the server writes into index.html
// (fabric_backend/workload_host.py) when the build carries none.
import { describe, expect, it } from "vitest";
import { engineScope, pickScope } from "./engineClient";
import { getWorkloadName, rememberWorkloadOf, workloadNameOf } from "../../controller/ConfigurationController";

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

// n176: one hosted editor for Org.Krusgraph and Krusgraph.Modeler; the item type says which, and the scope follows it.
const MODELER = "https://krusgraph.com/workload/workload/Krusgraph.Modeler/user_impersonation";
const DEV = "https://krusgraph.com/workload/workload/Org.Krusgraph/user_impersonation";

function docWithMany(many: string | null, one: string | null = null) {
  return {
    querySelector: (selector: string) => {
      const content = selector === 'meta[name="krusgraph-engine-scopes"]' ? many : selector === 'meta[name="krusgraph-engine-scope"]' ? one : null;
      return content === null ? null : ({ getAttribute: (name: string) => (name === "content" ? content : null) } as unknown as Element);
    },
  };
}

describe("the workload name at run time", () => {
  it("is the item type without its item part", () => {
    expect(workloadNameOf("Krusgraph.Modeler.Model")).toBe("Krusgraph.Modeler");
    expect(workloadNameOf("Org.Krusgraph.Model")).toBe("Org.Krusgraph");
    expect(workloadNameOf("Model")).toBe("");
    expect(workloadNameOf(undefined)).toBe("");
  });
  it("follows the item being edited and keeps the last known one", () => {
    expect(rememberWorkloadOf("Krusgraph.Modeler.Model")).toBe("Krusgraph.Modeler");
    expect(rememberWorkloadOf("")).toBe("Krusgraph.Modeler");
    expect(getWorkloadName()).toBe("Krusgraph.Modeler");
  });
});

describe("pickScope and the scopes meta tag", () => {
  it("takes the scope of the editor's own workload, whole path parts only", () => {
    expect(pickScope([DEV, MODELER], "Krusgraph.Modeler")).toBe(MODELER);
    expect(pickScope([MODELER, DEV], "Org.Krusgraph")).toBe(DEV);
    expect(pickScope([MODELER, DEV], "Krusgraph")).toBe(MODELER);         // no whole match: the first
    expect(pickScope([], "Org.Krusgraph")).toBe("");
  });
  it("reads every scope the server lists and falls back to the single tag", () => {
    expect(engineScope(undefined, docWithMany(`${MODELER} ${DEV}`), "Org.Krusgraph")).toBe(DEV);
    expect(engineScope(undefined, docWithMany("", DEV), "Krusgraph.Modeler")).toBe(DEV);
    expect(engineScope("api://built/user_impersonation", docWithMany(MODELER), "Krusgraph.Modeler")).toBe("api://built/user_impersonation");
  });
});
