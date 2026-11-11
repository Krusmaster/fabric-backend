import { describe, expect, it } from "vitest";
import { accessLine } from "./accessWords";

describe("accessLine (n213)", () => {
  it("shows the trial's days left in one line", () => {
    expect(accessLine({ state: "trial", words: "Trial: 12 days left (until 4 December 2026). Subscribe through Microsoft Marketplace: https://x" }))
      .toBe("Trial: 12 days left (until 4 December 2026). Subscribe through Microsoft Marketplace: https://x");
  });
  it("shows nothing when the switch is off, the organisation is exempt or subscribed, or the engine has no route", () => {
    expect(accessLine({ state: "off", words: "" })).toBe("");
    expect(accessLine({ state: "exempt", words: "" })).toBe("");
    expect(accessLine(null)).toBe("");
    expect(accessLine(undefined)).toBe("");
  });
});
