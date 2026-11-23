/**
 * WB5: SAP in the review. The SAP fields in plain words (only what the SAP pack documents, sourceWords.sapFieldRows),
 * and the CSN file chosen in the editor (csnUpload.ts): read in the browser, kept in the item, sent with the review.
 */
import React, { useRef, useState } from "react";
import { Body1, Button, Caption1, MessageBar, MessageBarBody } from "@fluentui/react-components";
import { CsnUpload, entityCount, readCsn } from "./csnUpload";
import { SapOffer, sapFieldRows } from "./sourceWords";

export function SapFields(props: { sap?: SapOffer }) {
  const rows = sapFieldRows(props.sap);
  if (!rows.length) return null;
  return (
    <details className="krusgraph-sap-fields">
      <summary><Body1>SAP fields in plain words ({rows.length})</Body1></summary>
      <Caption1>From the SAP pack's documentation of SAP's tables; fields it says nothing about are left out.</Caption1>
      <table aria-label="SAP fields in plain words">
        <thead><tr><th scope="col">Table</th><th scope="col">Field</th><th scope="col">What it is</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.table}.${r.column}`}><td>{r.table}</td><td><code>{r.column}</code></td><td>{r.words}</td></tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export function CsnChooser(props: { csn?: CsnUpload; disabled?: boolean; onCsn: (v: CsnUpload | null) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  async function picked(files: FileList | null) {
    const f = files?.[0];
    if (!f) return;
    const r = readCsn(f.name, f.size, await f.text());
    if (input.current) input.current.value = "";
    if ("error" in r) {
      setError(r.error);
      return;
    }
    setError(undefined);
    props.onCsn(r.value);
  }
  return (
    <section className="krusgraph-csn" aria-label="SAP data model (CSN file)">
      <Body1>
        {props.csn
          ? `CSN file: ${props.csn.name} (${entityCount(props.csn.csn)} entities). Its keys and links come first in the review.`
          : "Have a CSN export of the SAP data model? Choose it, and its declared keys and links come first in the review."}
      </Body1>
      <input ref={input} type="file" accept=".json,.csn,application/json" hidden aria-hidden="true"
        onChange={(e) => void picked(e.target.files)} />
      <div className="krusgraph-actions">
        <Button disabled={props.disabled} onClick={() => input.current?.click()}>
          {props.csn ? "Choose another CSN file" : "Choose a CSN file"}
        </Button>
        {props.csn && <Button disabled={props.disabled} onClick={() => props.onCsn(null)}>Remove the CSN file</Button>}
      </div>
      <Caption1>Read in your browser and kept only in this item. At most 5 MB.</Caption1>
      {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
    </section>
  );
}

export interface SapDemoAnswer {
  would: "create" | "exists" | "created";
  words: string;
  confirm?: string | null;
  note?: string;
  error?: string;
  hint?: string;
}

/** WB5: Load SAP demo data, for a source without SAP tables: the sap_demo36 generator notebook, a dry run first, then
 * Create with the dry run's confirm. Krusgraph never runs it; the notebook itself writes nothing until DRY_RUN = False. */
export function SapDemo(props: { send: (dryRun: boolean, confirm?: string) => Promise<SapDemoAnswer> }) {
  const [answer, setAnswer] = useState<SapDemoAnswer>();
  const [busy, setBusy] = useState(false);
  async function go(dryRun: boolean) {
    setBusy(true);
    try {
      setAnswer(await props.send(dryRun, dryRun ? undefined : answer?.confirm ?? undefined));
    } catch (e) {
      const err = e as { answer?: SapDemoAnswer; message?: string };
      setAnswer(err.answer ?? { would: "create", words: "", error: err.message ?? "The engine did not answer." });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="krusgraph-sap-demo" aria-label="Load SAP demo data">
      <Body1>No SAP tables here? Load SAP demo data: a notebook that writes synthetic, SAP-shaped tables (36 months, made-up
        names) to a new schema, so you can try the SAP path. Krusgraph creates it; it does not run it.</Body1>
      <div className="krusgraph-actions">
        <Button disabled={busy} onClick={() => { void go(true); }}>Dry run: Load SAP demo data</Button>
        {answer?.would === "create" && answer.confirm && !answer.error && (
          <Button appearance="primary" disabled={busy} onClick={() => { void go(false); }}>Create the notebook</Button>
        )}
      </div>
      {answer?.error && (
        <MessageBar intent="error"><MessageBarBody>{answer.error}{answer.hint ? ` ${answer.hint}` : ""}</MessageBarBody></MessageBar>
      )}
      {answer && !answer.error && <Body1>{answer.words}</Body1>}
      {answer?.note && <Caption1>{answer.note}</Caption1>}
    </section>
  );
}
