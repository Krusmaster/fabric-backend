// @vitest-environment jsdom
// WB14 (#108): "Save to lakehouse Files" with OneLake's answers mocked: 201 Created, 403 without consent, 409 a file
// already there (then Replace), and a timeout. The switch is off unless the hosting server's meta tag says on.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FileActions, FileContext, OneLakeContext } from "./fileOffer";
import {
  NO_ACCESS, STORAGE_SCOPE, TIMED_OUT, dryRunWords, filesPath, onelakeUrl, safeSegment, saveEnabled, saveToOneLake, shownPath,
} from "./onelakeSave";

const TARGET = { workspaceId: "11111111-1111-1111-1111-111111111111", lakehouseId: "22222222-2222-2222-2222-222222222222",
  lakehouseName: "demo_lh", itemName: "shop_model" };
const MAP = { filename: "demo_lh.shop-map.drawio", mime: "application/xml", text: "<mxfile/>" };

function answer(status: number, id = "req-" + status): Response {
  return new Response(status === 201 || status === 202 || status === 200 ? null : "{}", { status, headers: { "x-ms-request-id": id } });
}

describe("onelakeSave (no UI)", () => {
  it("is off unless the meta tag says on", () => {
    const doc = (v: string | null) => ({ querySelector: () => (v === null ? null : ({ getAttribute: () => v } as unknown as Element)) });
    expect(saveEnabled(undefined)).toBe(false);
    expect(saveEnabled(doc(null))).toBe(false);
    expect(saveEnabled(doc("off"))).toBe(false);
    expect(saveEnabled(doc("on"))).toBe(true);
  });

  it("writes under Files/krusgraph/<item name>/ by GUIDs, and shows the full path", () => {
    expect(filesPath(TARGET, MAP.filename)).toBe("Files/krusgraph/shop_model/demo_lh.shop-map.drawio");
    expect(shownPath(TARGET, MAP.filename)).toBe("demo_lh › Files/krusgraph/shop_model/demo_lh.shop-map.drawio");
    expect(onelakeUrl(TARGET, MAP.filename)).toBe(
      "https://onelake.dfs.fabric.microsoft.com/11111111-1111-1111-1111-111111111111/22222222-2222-2222-2222-222222222222/Files/krusgraph/shop_model/demo_lh.shop-map.drawio");
    expect(safeSegment("../a/b\\c")).toBe("_a_b_c");
    expect(safeSegment("  ")).toBe("model");
    expect(onelakeUrl({ ...TARGET, itemName: "my model" }, "x y.md")).toContain("/Files/krusgraph/my%20model/x%20y.md");
    expect(dryRunWords(TARGET, MAP)).toMatch(/^Dry run: Save would write demo_lh\.shop-map\.drawio \(9 bytes\) to demo_lh › Files\/krusgraph\/shop_model\//);
  });

  it("201: create without overwrite, append, flush; logs status and request id only", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fetch = vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return answer(url.includes("resource=file") ? 201 : url.includes("action=append") ? 202 : 200);
    });
    const log = vi.fn();
    const out = await saveToOneLake({ token: async () => "tok", fetch, log }, TARGET, MAP);
    expect(out).toEqual({ kind: "saved", status: 200, activityId: "req-200" });
    expect(calls.map((c) => `${c.init.method} ${c.url.split("?")[1]}`)).toEqual(
      ["PUT resource=file", "PATCH action=append&position=0", "PATCH action=flush&position=9"]);
    const h = calls[0].init.headers as Record<string, string>;
    expect(h["If-None-Match"]).toBe("*");
    expect(h.Authorization).toBe("Bearer tok");
    for (const [fields] of log.mock.calls) {
      expect(Object.keys(fields).sort()).toEqual(["activity_id", "status"]);
      expect(JSON.stringify(fields)).not.toContain("tok");
      expect(JSON.stringify(fields)).not.toContain("mxfile");
    }
  });

  it("403 (no consent): no_access, nothing else sent", async () => {
    const fetch = vi.fn(async () => answer(403));
    const out = await saveToOneLake({ token: async () => "tok", fetch, log: (): void => undefined }, TARGET, MAP);
    expect(out.kind).toBe("no_access");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("a token the host will not give (consent missing): no_access, OneLake not called", async () => {
    const fetch = vi.fn();
    const out = await saveToOneLake({ token: async () => { throw Object.assign(new Error("AADSTS65001"), { code: "consent_required" }); }, fetch, log: (): void => undefined }, TARGET, MAP);
    expect(out).toEqual({ kind: "no_access" });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("409 (already there): exists, the file is not touched; Replace sends the create without If-None-Match", async () => {
    const fetch = vi.fn(async () => answer(409));
    const out = await saveToOneLake({ token: async () => "tok", fetch, log: (): void => undefined }, TARGET, MAP);
    expect(out.kind).toBe("exists");
    expect(fetch).toHaveBeenCalledTimes(1);
    const again = vi.fn(async (url: string, init: RequestInit) => answer(url.includes("resource=file") ? 201 : 200));
    await saveToOneLake({ token: async () => "tok", fetch: again, log: (): void => undefined }, TARGET, MAP, { replace: true });
    expect((again.mock.calls[0][1].headers as Record<string, string>)["If-None-Match"]).toBeUndefined();
  });

  it("a timeout: timeout, said plainly", async () => {
    const fetch = vi.fn(() => new Promise<Response>(() => undefined));
    const out = await saveToOneLake({ token: async () => "tok", fetch, timeoutMs: 20, log: (): void => undefined }, TARGET, MAP);
    expect(out).toEqual({ kind: "timeout" });
  });

  it("a zip goes as its bytes", async () => {
    const sent: unknown[] = [];
    const fetch = vi.fn(async (url: string, init: RequestInit) => { sent.push(init.body); return answer(url.includes("resource=file") ? 201 : 200); });
    await saveToOneLake({ token: async () => "tok", fetch, log: (): void => undefined }, TARGET, { filename: "app.zip", mime: "application/zip", base64: "UEsDBA==" });
    expect(Array.from(sent[1] as Uint8Array)).toEqual([0x50, 0x4b, 0x03, 0x04]);
  });
});

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

const btn = (text: string) => Array.from(host.querySelectorAll("button")).find((b) => b.textContent?.startsWith(text)) as HTMLButtonElement;
const files = { offer: vi.fn(async () => ({ path: "/workload/v1/file/x", expires_in: 600, filename: MAP.filename })), open: vi.fn(async () => undefined), base: "https://workload.krusgraph.com" };

function render(fetch: (u: string, i: RequestInit) => Promise<Response>, on = true) {
  const src = on ? { target: TARGET, token: async () => "tok", fetch, log: (): void => undefined } : undefined;
  act(() => root.render(
    <FileContext.Provider value={files as never}>
      <OneLakeContext.Provider value={src}>
        <FileActions file={MAP} label="Download as draw.io" />
      </OneLakeContext.Provider>
    </FileContext.Provider>));
}

describe("Save to lakehouse Files (the button)", () => {
  it("is not shown when the switch is off; Download and Copy are", () => {
    render(vi.fn(), false);
    expect(btn("Save to lakehouse Files")).toBeUndefined();
    expect(btn("Download as draw.io")).toBeDefined();
    expect(btn("Copy")).toBeDefined();
  });

  it("dry run first (the full path, nothing sent), then Save writes", async () => {
    const fetch = vi.fn(async (url: string) => answer(url.includes("resource=file") ? 201 : 200));
    render(fetch);
    await act(async () => { btn("Save to lakehouse Files").click(); });
    expect(fetch).not.toHaveBeenCalled();
    expect(host.textContent).toContain("Dry run: Save would write demo_lh.shop-map.drawio");
    expect(host.textContent).toContain("demo_lh › Files/krusgraph/shop_model/demo_lh.shop-map.drawio");
    await act(async () => { btn("Save").click(); });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(host.textContent).toContain("Saved to demo_lh › Files/krusgraph/shop_model/demo_lh.shop-map.drawio");
  });

  it("409: asks Replace; Keep leaves it; Replace overwrites", async () => {
    let n = 0;
    const fetch = vi.fn(async (url: string, init: RequestInit) => {
      n++;
      if (url.includes("resource=file")) return answer((init.headers as Record<string, string>)["If-None-Match"] ? 409 : 201);
      return answer(200);
    });
    render(fetch);
    await act(async () => { btn("Save to lakehouse Files").click(); });
    await act(async () => { btn("Save").click(); });
    expect(host.textContent).toContain("is already in demo_lh › Files/krusgraph/shop_model/. Nothing was written. Replace it");
    expect(n).toBe(1);
    await act(async () => { btn("Replace").click(); });
    expect(n).toBe(4);
    expect(host.textContent).toContain("Saved to demo_lh");
  });

  it("403: the plain message, and Download still works", async () => {
    render(vi.fn(async () => answer(403)));
    await act(async () => { btn("Save to lakehouse Files").click(); });
    await act(async () => { btn("Save").click(); });
    expect(host.textContent).toContain(NO_ACCESS);
    await act(async () => { btn("Download as draw.io").click(); });
    expect(files.offer).toHaveBeenCalled();
    expect(files.open).toHaveBeenCalled();
  });

  it("a timeout: says so, and nothing is replaced", async () => {
    act(() => root.render(
      <OneLakeContext.Provider value={{ target: TARGET, token: async () => "tok", fetch: () => new Promise<Response>(() => undefined), timeoutMs: 20, log: (): void => undefined }}>
        <FileActions file={MAP} label="Download" />
      </OneLakeContext.Provider>));
    await act(async () => { btn("Save to lakehouse Files").click(); });
    await act(async () => { btn("Save").click(); await new Promise((r) => setTimeout(r, 60)); });
    expect(host.textContent).toContain(TIMED_OUT);
  });

  it("asks the host for the Storage scope", () => {
    expect(STORAGE_SCOPE).toBe("https://storage.azure.com/user_impersonation");
  });
});
