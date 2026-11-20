// W13: a source the sign-in cannot open. Found by the end-to-end run (workload/scripts/e2e, scenario "forbidden"): the
// schema step showed the engine's sentence with the route's name and the workspace's id, then a text field and an
// enabled "Find keys and relationships" that could only lead to the same 403.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { schemaProblem } from "./sourceWords";
import { EmptyView } from "./ModelItemViews";

const NO_ACCESS = {
  error: "The signed-in account has no access to schemas: workspace '11111111-2222-3333-4444-555555555555', source 'demo_lh' (HTTP 403: The caller does not have permission to perform the operation.).",
  kind: "no_access",
  hint: "The signed-in account cannot open it.",
};
const SOURCE = { version: 1, platform: "fabric", workspaceId: "w", itemId: "l", itemType: "Lakehouse", displayName: "demo_lh", schema: "dbo" };

describe("W13: no access to the source", () => {
  it("says what to ask for, without the route or the workspace's id", () => {
    const p = schemaProblem(NO_ACCESS, "demo_lh");
    expect(p.typeIt).toBe(false);
    expect(p.line).toBe("Your sign-in cannot open demo_lh. Ask the workspace's admin for access (Viewer is enough to find keys and links, Contributor to create), or choose another source.");
    expect(p.line).not.toMatch(/11111111|schemas:|HTTP 403/);
  });

  it("keeps the typed schema for other errors", () => {
    const p = schemaProblem({ error: "The SQL endpoint did not answer.", kind: "sql_timeout" }, "demo_lh");
    expect(p.typeIt).toBe(true);
    expect(p.line).toContain("Type the schema as the lakehouse spells it.");
  });

  it("shows a warning instead of the field, and Find keys and relationships is disabled", () => {
    const html = renderToStaticMarkup(
      <EmptyView source={SOURCE as never} schema="dbo" schemas={{ loading: false, error: NO_ACCESS }} onSchemaChange={() => undefined}
        onChooseLakehouse={() => undefined} onReview={() => undefined} />
    );
    expect(html).toContain("Your sign-in cannot open demo_lh.");
    expect(html).not.toContain("11111111");
    expect(html).not.toMatch(/<input[^>]*value="dbo"/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Find keys and relationships<\/button>/);
  });
});
