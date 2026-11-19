// FA1 (19 Nov 2026): once this item has built a semantic model, the next steps point to Microsoft's Power BI Desktop for
// Apps (preview), which builds a Fabric app from a semantic model. Guide only: a link to Microsoft's Learn page, the
// Fabric app item's icon from @fabric-msft/svg-icons (fabricIcons.json), no product logo, nothing built by Krusgraph.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import FIXTURE from "./w13Review.fixture.json";
import { ReviewFile } from "./ModelItemDefinition";
import { LEARN, nextSteps, workloadLine } from "./nextSteps";
import { NextStepsPanel } from "./NextStepsView";

const REVIEW = FIXTURE.review as unknown as ReviewFile;
const SOURCE = { displayName: "shop_lh", schema: "shop", itemType: "Lakehouse" };
const MODEL = { type: "SemanticModel", id: "sm-1", name: "shop_lh_model", workspace: "ws", output: "semantic_model" };

describe("FA1: Build an app in Power BI Desktop for Apps", () => {
  it("is not suggested before a semantic model is built", () => {
    expect(nextSteps({ review: REVIEW, created: [], source: SOURCE }).steps.map((s) => s.id)).not.toContain("desktop-apps");
  });

  it("is a guide to Microsoft's Learn page once the model exists, last, with the Fabric app item's type", () => {
    const steps = nextSteps({ review: REVIEW, created: [MODEL], source: SOURCE }).steps;
    const d = steps[steps.length - 1];
    expect(d.id).toBe("desktop-apps");
    expect(d.title).toBe("Build an app in Power BI Desktop for Apps");
    expect(d.status).toBe("guide only");
    expect(d.how).toEqual({ kind: "guide", label: "Open Microsoft's guide", url: LEARN.desktopForApps });
    expect(LEARN.desktopForApps).toBe("https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/overview");
    expect(d.items).toEqual(["AppBackend"]);
    expect(workloadLine(d)).toBe("Apps · App");
    expect(d.why).toMatch(/^Every app built there starts from a semantic model; this one's \d+ relationships? rest on links proven on the rows\.$/);
    expect(d.note).toContain("preview");
    expect(d.note).toContain("GitHub Copilot");
    for (const word of ["partner", "endorsed", "certified", "faster", "minutes"]) {
      expect(`${d.title} ${d.why} ${d.note}`.toLowerCase()).not.toContain(word);
    }
  });

  it("renders as a link with Microsoft's item icon beside the words, and no button that builds", () => {
    const html = renderToStaticMarkup(<NextStepsPanel review={REVIEW} created={[MODEL]} source={SOURCE} onBuild={() => undefined} />);
    const card = html.slice(html.indexOf('data-step="desktop-apps"'));
    expect(card).toContain("Build an app in Power BI Desktop for Apps");
    expect(card).toContain(LEARN.desktopForApps);
    expect(card).toContain("fabric_apps_24_item.svg");
    expect(card).toContain("Guide only");
  });
});
