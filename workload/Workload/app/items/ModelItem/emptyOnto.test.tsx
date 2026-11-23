import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { EmptyView } from "./ModelItemViews";
import { ONTO_EMPTY } from "./stepWords";

const base = { schema: "", schemas: { loading: false }, onSchemaChange: (): void => undefined, onChooseLakehouse: (): void => undefined,
  onReview: (): void => undefined } as const;

describe("WB6 Onto on the empty view", () => {
  it("shows Onto and one plain sentence instead of the kit's check-mark picture", () => {
    const html = renderToStaticMarkup(<EmptyView {...base} />);
    expect(html).not.toContain("EditorEmpty.svg");
    expect(html).toContain("/assets/mascots/onto.png");
    expect(html).toContain(ONTO_EMPTY.replace(/'/g, "&#x27;"));
    expect(html).toMatch(/<img[^>]*onto\.png[^>]*alt=""|alt=""[^>]*onto\.png/);   // decorative: the sentence is the text
  });
  it("leaves Onto out when the mascots are off", () => {
    const html = renderToStaticMarkup(<EmptyView {...base} mascotsOn={false} />);
    expect(html).not.toContain("onto.png");
    expect(html).not.toContain("EditorEmpty.svg");
  });
});
