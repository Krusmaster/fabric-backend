// @vitest-environment jsdom
// WB10 (Gustav's live test in Fabric, 18 Nov 2026, #57): every download in the editor goes through the engine's
// single-use link, opened by the Fabric host (openBrowserTab), because Fabric's frame blocks downloads and popups; Copy
// falls back to a visible, selected text area when the frame does not allow the clipboard.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CopyText, FileActions, FileContext, NO_CLIPBOARD, NOT_OPENED, OutLink, absolute, dataHref } from "./fileOffer";

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
  vi.restoreAllMocks();
});

const MD = { filename: "fabric-admin.md", mime: "text/markdown", text: "# For the admin\n" };
const files = (over: Partial<{ offer: unknown; open: unknown }> = {}) => ({
  offer: vi.fn(async () => ({ path: "/workload/v1/file/x.1.y", expires_in: 600, filename: MD.filename })),
  open: vi.fn(async () => undefined),
  base: "https://workload.krusgraph.com",
  ...over,
});
const btn = (text: string) => Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith(text)) as HTMLButtonElement;

describe("FileActions", () => {
  it("offers the file to the engine and asks the host to open the link; no data: link", async () => {
    const f = files();
    act(() => root.render(<FileContext.Provider value={f as never}><FileActions file={MD} label="handover/fabric-admin.md" /></FileContext.Provider>));
    await act(async () => { btn("handover/").click(); });
    expect(f.offer).toHaveBeenCalledWith(MD);
    expect(f.open).toHaveBeenCalledWith("https://workload.krusgraph.com/workload/v1/file/x.1.y");
    expect(host.innerHTML).not.toContain("data:");
    expect(host.textContent).toContain("The link works once, for 10 minutes");
  });

  it("shows the link to open by hand when the host does not open the tab", async () => {
    const f = files({ open: vi.fn(async () => { throw new Error("blocked"); }) });
    act(() => root.render(<FileContext.Provider value={f as never}><FileActions file={MD} label="Download" /></FileContext.Provider>));
    await act(async () => { btn("Download").click(); });
    expect(host.textContent).toContain(NOT_OPENED);
    const a = host.querySelector("a.kg-file-link") as HTMLAnchorElement;
    expect(a.href).toBe("https://workload.krusgraph.com/workload/v1/file/x.1.y");
    expect(a.getAttribute("target")).toBe("_blank");
  });

  it("sends a zip as base64 and offers no Copy for it", async () => {
    const f = files();
    const zip = { filename: "app.zip", mime: "application/zip", base64: "UEsDBA==" };
    act(() => root.render(<FileContext.Provider value={f as never}><FileActions file={zip} label="Download the package" /></FileContext.Provider>));
    expect(btn("Copy")).toBeUndefined();
    await act(async () => { btn("Download").click(); });
    expect(f.offer).toHaveBeenCalledWith(zip);
    expect(dataHref(zip)).toBe("data:application/zip;base64,UEsDBA==");
  });

  it("makes absolute links from the engine's path", () => {
    expect(absolute("/workload/v1/file/a.1.b", "https://workload.krusgraph.com")).toBe("https://workload.krusgraph.com/workload/v1/file/a.1.b");
  });
});

describe("CopyText", () => {
  it("copies when the frame allows the clipboard", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    act(() => root.render(<CopyText text="SELECT 1" label="Copy the code" />));
    await act(async () => { btn("Copy the code").click(); });
    expect(writeText).toHaveBeenCalledWith("SELECT 1");
    expect(btn("Copied")).toBeTruthy();
    expect(host.querySelector("textarea")).toBeNull();
  });

  it("shows the text, selected, when the frame refuses the clipboard", async () => {
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async () => { throw new Error("NotAllowedError"); }) }, configurable: true });
    act(() => root.render(<CopyText text="SELECT 1" label="Copy the code" />));
    await act(async () => { btn("Copy the code").click(); });
    const area = host.querySelector("textarea") as HTMLTextAreaElement;
    expect(area.value).toBe("SELECT 1");
    expect(area.readOnly).toBe(true);
    expect(document.activeElement).toBe(area);
    expect(host.textContent).toContain(NO_CLIPBOARD);
  });
});

describe("OutLink", () => {
  it("asks the host to open a page outside Fabric", async () => {
    const f = files();
    act(() => root.render(<FileContext.Provider value={f as never}><OutLink url="https://learn.microsoft.com/fabric/">Learn</OutLink></FileContext.Provider>));
    await act(async () => { (host.querySelector("a") as HTMLAnchorElement).click(); });
    expect(f.open).toHaveBeenCalledWith("https://learn.microsoft.com/fabric/");
  });
});
