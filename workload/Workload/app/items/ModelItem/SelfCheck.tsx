/**
 * WB9: the pilot's self-check on the empty view. One click reads, as the signed-in user, what is still missing before a
 * first session: admin consent, a Fabric capacity, access to the workspace, a lakehouse. Read only
 * (POST /workload/v1/selfcheck, fabric_backend/workload_api.run_selfcheck). The tenant setting cannot be read without a
 * Fabric administrator, so it is said to be unknown, never guessed.
 */
import React, { useState } from "react";
import { Body1, Button, Caption1, MessageBar, MessageBarBody } from "@fluentui/react-components";

export interface SelfCheckItem { id: string; state: "ok" | "missing" | "unknown"; words: string }
export interface SelfCheckAnswer { checks?: SelfCheckItem[]; ready?: boolean; note?: string; error?: string; hint?: string }

export const SELFCHECK_LABELS: Record<string, string> = {
  consent: "Admin consent",
  capacity: "Fabric capacity",
  workspace: "Workspace access",
  lakehouse: "A lakehouse",
  tenant_setting: "Tenant setting",
};
const MARK: Record<string, string> = { ok: "OK", missing: "Missing", unknown: "Unknown" };

/** The headline: what to do first, in one sentence. */
export function selfCheckLine(a: SelfCheckAnswer): string {
  if (a.error) return "";
  const missing = (a.checks ?? []).filter((c) => c.state === "missing");
  if (!missing.length) return "Nothing is missing: choose a source to start.";
  return `${missing.length} thing${missing.length > 1 ? "s" : ""} to fix first: ${missing.map((c) => SELFCHECK_LABELS[c.id] ?? c.id).join(", ")}.`;
}

export function SelfCheck(props: { send?: () => Promise<SelfCheckAnswer> }) {
  const [answer, setAnswer] = useState<SelfCheckAnswer>();
  const [busy, setBusy] = useState(false);
  if (!props.send) return null;
  const send = props.send;
  async function go() {
    setBusy(true);
    try {
      setAnswer(await send());
    } catch (e) {
      const err = e as { answer?: SelfCheckAnswer; message?: string };
      setAnswer(err.answer ?? { error: err.message ?? "The engine did not answer." });
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="krusgraph-selfcheck kg-how">
      <summary><Caption1>Is everything ready? Check this workspace</Caption1></summary>
      <Caption1 as="p">Reads your permissions and this workspace; changes nothing.</Caption1>
      <Button appearance="secondary" disabled={busy} onClick={() => { void go(); }}>{busy ? "Checking…" : "Run the self-check"}</Button>
      {answer?.error && (
        <MessageBar intent="error"><MessageBarBody>{answer.error}{answer.hint ? ` ${answer.hint}` : ""}</MessageBarBody></MessageBar>
      )}
      {answer && !answer.error && (
        <>
          <Body1 role="status">{selfCheckLine(answer)}</Body1>
          <ul aria-label="Self-check">
            {(answer.checks ?? []).map((c) => (
              <li key={c.id} data-state={c.state}>
                <Caption1><strong>{SELFCHECK_LABELS[c.id] ?? c.id}: {MARK[c.state] ?? c.state}.</strong> {c.words}</Caption1>
              </li>
            ))}
          </ul>
        </>
      )}
    </details>
  );
}
