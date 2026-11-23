import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ErrorBar, upgradeLink } from "./ModelItemViews";

describe("WB7 upgrade link on a refused Create", () => {
  const refused = { error: "Creating items in Fabric needs a Krusgraph subscription.", kind: "upgrade",
    hint: "The dry run is free.", upgrade_url: "https://marketplace.microsoft.com/product/x" };
  it("links only an https offer on kind upgrade", () => {
    expect(upgradeLink(refused)).toBe(refused.upgrade_url);
    expect(upgradeLink({ ...refused, upgrade_url: "javascript:alert(1)" })).toBeUndefined();
    expect(upgradeLink({ ...refused, kind: "no_access" })).toBeUndefined();
    expect(upgradeLink(undefined)).toBeUndefined();
  });
  it("shows the sentence and the link, no dead end", () => {
    const html = renderToStaticMarkup(<ErrorBar error={refused} />);
    expect(html).toContain("needs a Krusgraph subscription");
    expect(html).toContain('href="https://marketplace.microsoft.com/product/x"');
    expect(html).toContain("Subscribe in Microsoft Marketplace");
    expect(renderToStaticMarkup(<ErrorBar error={{ error: "x", kind: "no_access" }} />)).not.toContain("Marketplace");
  });
});
