// @vitest-environment jsdom
// n229: "Verify what was built" after a Create. The button asks the engine to read back what this Model built
// (POST /workload/v1/verify); the result says it is a check by rules, lists one line per item with what differs first,
// shows the SQL on request and then the next steps with one sentence of reason each. Not shown where nothing provides
// the call or nothing is built.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { BY_RULES, VERIFY_LABEL, VerifyAnswer, VerifyButton, VerifyContext, countsLine, sortLines } from "./verifyBuilt";

const ANSWER: VerifyAnswer = {
  label: "A check by rules, not a review by AI: Krusgraph read back what is in Fabric and compared it with the dry run, and counted the figures again from the rows. No AI model was used.",
  summary: "2 item(s): 1 verified, 1 differs, 0 not checked. Figures: 3 verified, 0 differ, 0 not checked.",
  counts: { verified: 1, differs: 1, not_checked: 0, items: 2 },
  lines: [
    { item: "shop_model_report", kind: "report", state: "verified", said: "shop_model_report (report): verified. Definition as the dry run (8 visuals compared). Figures: 3 verified (from the rows: Orders = 60, Order lines = 134, Units = 324). No doubled total found." },
    { item: "shop_model", kind: "semantic_model", state: "differs", said: "shop_model (semantic model): differs. Definition as the dry run (8 tables compared). The model was never refreshed. Fix: Refresh the model once.", fix: { label: "Refresh the model once", how: "In Fabric, open the semantic model and choose Refresh now." } },
  ],
  sql: [{ item: "shop_model_report", what: "Orders", sql: "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]", dax: 'EVALUATE ROW("v", [Rows in orders])' }],
  next_steps: [
    { step: "refresh_model", label: "Refresh the model once", who: "builder", why: "In Fabric, open the semantic model and choose Refresh now.", how: "Choose Create again with the semantic model ticked.", item: "shop_model" },
    { step: "pipeline", label: "Build the pipeline (silver, gold, check)", who: "builder", why: "Nothing keeps the silver tables and the gold views up to date yet.", how: "Tick Pipeline under What to build." },
    { step: "data_product", label: "Register it as a data product", who: "onto", why: "It has items and no owner or contract yet.", how: "Open the Data product page of this Model and set the owner." },
  ],
  already_built: [{ step: "report", label: "Create a report on it", name: "shop_model_report" }],
  more: [{ step: "dbt", label: "Download a dbt project draft (a draft)", who: "builder", why: "A draft only: the dbt drafts are frozen.", how: "Not built from this editor." }],
  time_budget: { seconds: 45 },
};

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const buttons = () => Array.from(host.querySelectorAll("button")) as HTMLButtonElement[];

describe("Verify what was built", () => {
  it("is not shown where nothing provides the engine call, or when nothing is built", () => {
    act(() => root.render(<VerifyButton built={3} />));
    expect(host.innerHTML).toBe("");
    act(() =>
      root.render(
        <VerifyContext.Provider value={{ run: async () => ANSWER }}>
          <VerifyButton built={0} />
        </VerifyContext.Provider>
      )
    );
    expect(host.innerHTML).toBe("");
  });

  it("says it is a check by rules before it runs, then lists what differs first, the SQL on request and the next steps", async () => {
    let calls = 0;
    const run = async () => {
      calls += 1;
      return ANSWER;
    };
    act(() =>
      root.render(
        <VerifyContext.Provider value={{ run }}>
          <VerifyButton built={2} />
        </VerifyContext.Provider>
      )
    );
    expect(buttons()[0].textContent).toBe(VERIFY_LABEL);
    expect(host.textContent).toContain(BY_RULES);
    expect(host.textContent).toContain("It only reads.");
    await act(async () => {
      buttons()[0].click();
    });
    expect(calls).toBe(1);
    expect(host.textContent).toContain("A check by rules, not a review by AI");
    expect(host.textContent).toContain("2 item(s): 1 verified, 1 differs, 0 not checked.");
    const lines = Array.from(host.querySelectorAll(".krusgraph-verify-lines > li"));
    expect(lines.map((l) => l.getAttribute("data-state"))).toEqual(["differs", "verified"]);
    expect(lines[0].textContent).toContain("Differs");
    expect(lines[0].textContent).toContain("never refreshed");
    expect(lines[1].textContent).toContain("Orders = 60");
    // the SQL is folded until asked for
    expect(host.querySelector("pre")).toBeNull();
    const sql = buttons().find((b) => b.textContent === "Show the SQL")!;
    act(() => sql.click());
    expect(Array.from(host.querySelectorAll("pre")).map((p) => p.textContent)).toEqual([
      "SELECT COUNT_BIG(*) AS v FROM [shop].[orders]",
      'EVALUATE ROW("v", [Rows in orders])',
    ]);
    expect(host.textContent).toContain("Within a time budget of 45 s for the whole check.");
    // the next steps: in order, each with who says it and one sentence of reason; what is built is said, not offered
    const steps = Array.from(host.querySelectorAll(".krusgraph-verify-next ol > li")).map((l) => l.textContent ?? "");
    expect(steps.length).toBe(3);
    expect(steps[0]).toContain("Refresh the model once (shop_model)");
    expect(steps[1]).toContain("Builder: Nothing keeps the silver tables");
    expect(steps[2]).toContain("Onto: It has items and no owner or contract yet.");
    expect(host.querySelector(".kg-built")!.textContent).toBe("Create a report on it: already built (shop_model_report).");
    expect(host.querySelector("details")!.textContent).toContain("Download a dbt project draft (a draft)");
    expect(buttons()[0].textContent).toBe("Verify again");
  });

  it("says so when the engine cannot be reached, and when the engine answers an error", async () => {
    act(() =>
      root.render(
        <VerifyContext.Provider value={{ run: () => Promise.reject(new Error("offline")) }}>
          <VerifyButton built={1} />
        </VerifyContext.Provider>
      )
    );
    await act(async () => {
      buttons()[0].click();
    });
    expect(host.querySelector('[role="status"]')!.textContent).toBe("The verifier could not be reached just now. Nothing was changed; try again.");
    act(() =>
      root.render(
        <VerifyContext.Provider value={{ run: async () => ({ ...ANSWER, lines: [], error: "Sign in again.", hint: "Then verify once more." }) }}>
          <VerifyButton built={1} />
        </VerifyContext.Provider>
      )
    );
    await act(async () => {
      buttons()[0].click();
    });
    expect(host.querySelector(".krusgraph-verify-error")!.textContent).toContain("Sign in again. Then verify once more.");
  });

  it("orders lines and words the counts", () => {
    expect(sortLines([{ item: "a", kind: "report", state: "verified", said: "" }, { item: "b", kind: "report", state: "not checked", said: "" }, { item: "c", kind: "report", state: "differs", said: "" }]).map((l) => l.item)).toEqual(["c", "b", "a"]);
    expect(countsLine({ verified: 2, differs: 1, not_checked: 0 })).toBe("2 verified, 1 differs, 0 not checked");
    expect(countsLine({ verified: 0, differs: 2 })).toBe("0 verified, 2 differ, 0 not checked");
  });
});
