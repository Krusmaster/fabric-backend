import { describe, expect, it } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { existsSync, readFileSync } from "fs";
import { resolve } from "path";
import { MASCOT_IMG, MascotFigure } from "./mascotFigure";
import { MascotSays, Mascots } from "./ModelItemViews";

// n216: the editor's Onto, Thinker and Builder are the 3D figures of the film and the site, not the flat SVG.
const ASSETS = resolve(__dirname, "../../assets");

function pngSize(path: string): [number, number] {
  const b = readFileSync(path);
  expect(b.subarray(1, 4).toString("ascii")).toBe("PNG");
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}

describe("the editor's mascots (n216)", () => {
  it("are the 3D renders: one transparent 112 px PNG per figure, shown at 48 px (2x)", () => {
    for (const kind of ["onto", "thinker", "builder"] as const) {
      const file = resolve(ASSETS, MASCOT_IMG[kind].replace(/^\/assets\//, ""));
      expect(existsSync(file)).toBe(true);
      expect(pngSize(file)).toEqual([112, 112]);
      const b = readFileSync(file);
      expect(b[25]).toBe(6);                              // colour type 6: RGBA, so the ground is transparent
      expect(b.length).toBeLessThan(20000);
    }
  });

  it("draw an image with the pose kept as data-pose, decorative, and no flat SVG figure", () => {
    const html = renderToStaticMarkup(React.createElement(MascotSays, { kind: "thinker", text: "Two keys to look at.", pose: "think" }));
    expect(html).toContain('<img src="/assets/mascots/thinker.png" alt=""');
    expect(html).toContain('data-pose="think"');
    expect(html).toContain('aria-hidden="true"');
    expect(html).not.toContain("<svg");
    expect(html).toContain("Two keys to look at.");
    expect(renderToStaticMarkup(React.createElement(MascotFigure, { kind: "builder" }))).toContain('data-pose="rest"');
  });

  it("are gone when the switch is off: the sentences stay as plain text", () => {
    const off = renderToStaticMarkup(
      <Mascots on={false} onToggle={(): void => undefined} plain={["Onto says this."]}>
        <MascotSays kind="onto" text="Onto says this." />
      </Mascots>);
    expect(off).not.toContain("/assets/mascots/");
    expect(off).toContain("Mascots: off");
    expect(off).toContain("Onto says this.");
  });
});
