// n223: what Onto says while the editor waits, at 0, 10 and 30 seconds, for every kind of wait (waitWords.ts), and the
// component that draws it (OntoWait.tsx): the mascots toggle, the offer's buttons, Cancel only for a step that only reads.
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  OFFER_AFTER_S, SLOW_AFTER_S, Wait, WaitKind, checkLabel, newWait, offerLine, progressWords, reviewLabel, slowLine, waitLines, withSignal,
} from "./waitWords";
import { OntoWait, WAIT_CSS } from "./OntoWait";

const T0 = 1_800_000_000_000;
const at = (s: number) => T0 + s * 1000;
const KINDS: WaitKind[] = ["starting", "item", "sql", "capacity", "fabric", "network", "engine"];

/** what each kind may say after 10 s: the thing the code waits on, or "Still working on it." when it does not know */
const SLOW: Record<WaitKind, RegExp> = {
  starting: /^Still working on it\.$/,
  engine: /^Still working on it\.$/,
  item: /Fabric is taking its time to hand over this item's saved state/,
  sql: /Fabric's SQL endpoint is taking its time today; I am still (reading|counting)\./,
  capacity: /Your Fabric capacity is busy; this can take a minute\./,
  fabric: /Fabric is still finishing its part of this step; I am following its operation\./,
  network: /The last few reads did not get through; I keep asking\. Nothing is lost\./,
};

function wait(kind: WaitKind, extra: Partial<Wait> = {}): Wait {
  return { ...newWait("Reading the tables in shop…", T0, { kind }), ...extra };
}

describe("Onto's words while the editor waits", () => {
  for (const kind of KINDS) {
    it(`${kind}: the step at 0 s, one honest line at ${SLOW_AFTER_S} s, the offer at ${OFFER_AFTER_S} s`, () => {
      const w = wait(kind);
      const zero = waitLines(w, at(0));
      expect(zero.label).toBe("Reading the tables in shop…");
      expect(zero.slow).toBeUndefined();
      expect(zero.offer).toBeUndefined();
      expect(waitLines(w, at(9.9)).slow).toBeUndefined();

      const ten = waitLines(w, at(10));
      expect(ten.slow).toMatch(SLOW[kind]);
      expect(ten.offer).toBeUndefined();
      expect(ten.canCancel).toBe(false);

      const thirty = waitLines(w, at(30));
      expect(thirty.slow).toMatch(SLOW[kind]);
      expect(thirty.offer).toMatch(/^You can keep waiting/);
      expect(thirty.canSeeSteps).toBe(true);           // "Sent to the Krusgraph engine." is a step
      expect(thirty.canCancel).toBe(false);            // not cancellable unless the step only reads
    });
  }

  it("never blames without a signal: an unknown wait says only 'Still working on it.'", () => {
    for (const kind of ["starting", "engine"] as WaitKind[]) {
      const line = slowLine(kind);
      expect(line).toBe("Still working on it.");
      expect(line).not.toMatch(/SQL|capacity|Fabric|network/i);
    }
  });

  it("says counting for the check and reading for the review", () => {
    expect(slowLine("sql", "counting")).toContain("I am still counting");
    expect(slowLine("sql", "reading")).toContain("I am still reading");
    expect(reviewLabel("shop")).toBe("Reading the tables in shop and finding keys and links…");
    expect(checkLabel("shop")).toMatch(/^Counting the rows in shop/);
    expect(reviewLabel()).toMatch(/^Reading the lakehouse/);
  });

  it("offers Cancel only for a step that only reads, and says nothing in Fabric changes", () => {
    const w = wait("sql", { cancellable: true });
    expect(waitLines(w, at(29)).canCancel).toBe(false);
    const l = waitLines(w, at(30));
    expect(l.canCancel).toBe(true);
    expect(l.offer).toBe("You can keep waiting, see the steps done so far, or cancel: this step only reads, so nothing in Fabric changes.");
  });

  it("says a step that goes on without the editor (a Create) is safe to leave", () => {
    expect(offerLine({ leaveSafe: true }, true)).toBe(
      "You can keep waiting, see the steps done so far, or close the item: this step goes on, and reopening the item shows where it is.");
    expect(offerLine({}, true)).toBe("You can keep waiting or see the steps done so far.");
    expect(offerLine({}, false)).toBe("You can keep waiting.");
  });

  it("shows progress where the parts are known: 3 of 7 keys and links counted", () => {
    expect(progressWords({ done: 3, total: 7, unit: "keys and links counted" })).toBe("3 of 7 keys and links counted");
    expect(progressWords({ done: 9, total: 7, unit: "tables" })).toBe("7 of 7 tables");
    expect(progressWords({ done: 1, total: 0, unit: "x" })).toBeUndefined();
  });

  it("takes the engine's signals: the kind, its words and progress, each new thing once in the steps so far", () => {
    let w = wait("starting");
    w = withSignal(w, { kind: "sql" }, at(1));
    w = withSignal(w, { kind: "sql" }, at(2));                                         // nothing new: no new step
    w = withSignal(w, { kind: "sql", progress: { done: 3, total: 7, unit: "keys and links counted" } }, at(4));
    w = withSignal(w, { kind: "capacity", words: "Fabric's capacity is busy (429); trying again in 30 s." }, at(12));
    expect(w.kind).toBe("capacity");
    expect(w.steps.map((s) => s.text)).toEqual([
      "Sent to the Krusgraph engine.",
      "The engine is reading the SQL analytics endpoint.",
      "3 of 7 keys and links counted",
      "Fabric's capacity is busy (429); trying again in 30 s.",
    ]);
    expect(w.steps.map((s) => s.at)).toEqual([0, 1, 4, 12]);
    expect(waitLines(w, at(12)).progress).toBe("3 of 7 keys and links counted");     // the progress stays
    expect(waitLines(w, at(12)).slow).toMatch(SLOW.capacity);
  });
});

describe("OntoWait, the one loading component", () => {
  const html = (w: Wait, s: number, extra: Record<string, unknown> = {}) =>
    renderToStaticMarkup(React.createElement(OntoWait, { wait: w, now: at(s), onCancel: () => undefined, ...extra }));

  it("shows Onto, the step and skeleton rows at 0 s, announced politely", () => {
    const h = html(wait("sql"), 0);
    expect(h).toContain('src="/assets/mascots/onto.png"');
    expect(h).toContain("Onto: Reading the tables in shop…");
    expect(h).toContain('aria-live="polite"');
    expect(h).toContain('aria-busy="true"');
    expect(h).toContain('class="kg-skel"');
    expect(h).not.toContain("SQL endpoint");
    expect(h).not.toContain("<button");
  });

  it("adds the slow line at 10 s and the offer with its buttons at 30 s", () => {
    const w = wait("sql", { cancellable: true });
    expect(html(w, 10)).toContain("Fabric&#x27;s SQL endpoint is taking its time today");
    expect(html(w, 10)).not.toContain("<button");
    const h = html(w, 30);
    expect(h).toContain("Keep waiting</button>");
    expect(h).toContain("See the steps so far</button>");
    expect(h).toContain("Cancel</button>");
    expect(html(wait("sql"), 30)).not.toContain("Cancel</button>");
  });

  it("draws a progress bar where the parts are known", () => {
    const h = html(wait("sql", { progress: { done: 3, total: 7, unit: "keys and links counted" } }), 2);
    expect(h).toContain('role="progressbar"');
    expect(h).toContain('aria-valuenow="3"');
    expect(h).toContain('aria-valuemax="7"');
    expect(h).toContain("3 of 7 keys and links counted");
    expect(h).toContain("width:43%");
  });

  it("respects the mascots toggle: no figure, the same words", () => {
    const h = html(wait("capacity"), 10, { mascotsOn: false });
    expect(h).not.toContain("onto.png");
    expect(h).not.toContain("Onto:");
    expect(h).toContain("kg-wait-spin");
    expect(h).toContain("Your Fabric capacity is busy");
  });

  it("can stand above a page without skeleton rows (the Data product page, a review read again)", () => {
    expect(html(wait("engine"), 0, { skeleton: false })).not.toContain('class="kg-skel"');
  });

  it("is still under prefers-reduced-motion and has dark colours", () => {
    const motion = WAIT_CSS.indexOf("prefers-reduced-motion:reduce");
    expect(motion).toBeGreaterThan(0);
    expect(WAIT_CSS.slice(motion)).toMatch(/\.kg-wait-fig,\.kg-wait-spin,\.kg-skel span\{animation:none\}/);
    expect(WAIT_CSS).toContain("prefers-color-scheme:dark");
  });
});
