// @vitest-environment jsdom
// n228: "Download as draw.io" under the map and the data flow. The button sends what the editor shows to the engine
// (POST /workload/v1/drawio), offers the file as a link with `download`, says so when the engine has no file, and is not
// there when nothing provides the call.
import React from "react";
import { createRoot, Root } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DrawioButton, DrawioContext, DrawioRequest, fileHref, flowForFile } from "./drawioDownload";
import type { DataFlow } from "./engineClient";
import flowFixture from "./flow.fixture.json";

const FILE = { filename: "demo_lh.shop-map.drawio", mime_type: "application/vnd.jgraph.mxfile", content: '<mxfile host="Krusgraph"></mxfile>\n' };
const MAP = { tables: [{ name: "orders", key: ["order_id"], key_rule: "K2", columns: 5 }], relationships: [] as never[] };

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

const button = () => host.querySelector("button") as HTMLButtonElement;

describe("Download as draw.io", () => {
  it("is not shown where nothing provides the engine call", () => {
    act(() => root.render(<DrawioButton what="map" request={() => ({ diagram: "map", map: MAP })} />));
    expect(host.innerHTML).toBe("");
  });

  it("sends the map with the source's name and offers the file as a download link, clicked once", async () => {
    const sent: DrawioRequest[] = [];
    const clicks = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const get = async (body: DrawioRequest) => {
      sent.push(body);
      return FILE;
    };
    act(() =>
      root.render(
        <DrawioContext.Provider value={{ get, name: "demo_lh.shop" }}>
          <DrawioButton what="map" request={() => ({ diagram: "map", map: MAP })} />
        </DrawioContext.Provider>
      )
    );
    expect(button().textContent).toBe("Download as draw.io");
    await act(async () => {
      button().click();
    });
    expect(sent).toEqual([{ diagram: "map", map: MAP, name: "demo_lh.shop" }]);
    const a = host.querySelector("a") as HTMLAnchorElement;
    expect(a.getAttribute("download")).toBe(FILE.filename);
    expect(a.textContent).toBe(`Save ${FILE.filename}`);
    expect(decodeURIComponent(a.getAttribute("href")!.split(",")[1])).toBe(FILE.content);
    expect(a.getAttribute("href")!.startsWith("data:application/vnd.jgraph.mxfile;charset=utf-8,")).toBe(true);
    expect(clicks).toHaveBeenCalledTimes(1);
    clicks.mockRestore();
  });

  it("says what the engine said when the file is too large, and that nothing changed when the call fails", async () => {
    let answer: () => Promise<typeof FILE | { filename: string; mime_type: string; too_large: string }> = async () => ({
      filename: "x.drawio", mime_type: FILE.mime_type, too_large: "The file is 90000 characters; pass tables.",
    });
    act(() =>
      root.render(
        <DrawioContext.Provider value={{ get: () => answer() }}>
          <DrawioButton what="data flow" request={() => ({ diagram: "data_flow", flow: {} })} />
        </DrawioContext.Provider>
      )
    );
    await act(async () => {
      button().click();
    });
    expect(host.querySelector("a")).toBeNull();
    expect(host.textContent).toContain("The file is 90000 characters; pass tables.");
    answer = async () => {
      throw new Error("offline");
    };
    await act(async () => {
      button().click();
    });
    expect(host.textContent).toContain("The data flow could not be made into a draw.io file just now. Nothing changed; try again.");
  });

  it("sends the flow's boxes and arrows without the code a click unfolds", () => {
    const flow = flowFixture as unknown as DataFlow;
    const sent = flowForFile(flow) as { nodes: Record<string, unknown>[]; edges: unknown[]; said: string };
    expect(sent.nodes.length).toBe(flow.nodes.length);
    expect(sent.edges.length).toBe(flow.edges.length);
    expect(sent.nodes.every((n) => !("code" in n))).toBe(true);
    expect(JSON.stringify(sent)).not.toContain("CREATE MATERIALIZED LAKE VIEW");
    expect(sent.said).toBe(flow.said);
  });

  it("keeps every character of the file in the link", () => {
    const content = '<mxCell value="a &amp; b &lt;c&gt; 100% é #1"/>\n';
    expect(decodeURIComponent(fileHref({ ...FILE, content }).split(",")[1])).toBe(content);
  });
});
