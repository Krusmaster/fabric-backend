import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CORRELATION_HEADER, EngineCallError, newCorrelationId, sapDemo } from "./engineClient";
import { ErrorBar } from "./ModelItemViews";

describe("WB8 correlation id", () => {
  afterEach(() => { delete process.env.KRUSGRAPH_ENGINE_SCOPE; });
  const client = { auth: { acquireFrontendAccessToken: async () => ({ token: "t" }) } } as never;

  it("is fresh for every call", () => {
    const a = newCorrelationId(), b = newCorrelationId();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9-]{8,64}$/);
  });

  it("goes with the call and comes back on an error, also when no answer came", async () => {
    process.env.KRUSGRAPH_ENGINE_SCOPE = "api://x/user_impersonation";
    let sent = "";
    const refuse = async (_u: string, init: RequestInit) => {
      sent = (init.headers as Record<string, string>)[CORRELATION_HEADER];
      return new Response(JSON.stringify({ error: "no", kind: "no_access" }), { status: 403 });
    };
    const e = (await sapDemo(client, {}, refuse).catch((x) => x)) as EngineCallError;
    expect(e).toBeInstanceOf(EngineCallError);
    expect(sent).toMatch(/^[A-Za-z0-9-]{8,64}$/);
    expect(e.answer.correlation_id).toBe(sent);
    const lost = (await sapDemo(client, {}, async () => { throw new TypeError("Failed to fetch"); }).catch((x) => x)) as EngineCallError;
    expect(lost.answer.correlation_id).toMatch(/^[A-Za-z0-9-]{8,64}$/);
  });

  it("is shown as the reference for support", () => {
    const html = renderToStaticMarkup(<ErrorBar error={{ error: "x", kind: "no_access", correlation_id: "abc12345" }} />);
    expect(html).toContain("Reference for support");
    expect(html).toContain("abc12345");
  });
});
