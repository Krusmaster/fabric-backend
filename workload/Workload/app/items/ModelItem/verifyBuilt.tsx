/**
 * Krusgraph (n229): "Verify what was built", after a Create. The founder, 12 November 2026: "an agent that
 * double-checks Krusgraph's deployed proposals", and "no more suggestions after we built what was proposed".
 *
 * Krusgraph for Fabric uses no AI model, so this is a check by rules and the view says so: the engine reads back what
 * this Model built (POST /workload/v1/verify, fabric_backend/verify_build.py), compares each item with its dry run,
 * counts the report's cards again from the rows and says what was never refreshed or run. One line per item: verified,
 * differs, or not checked with the reason. Under it, the next steps of the data product in the order of what it still
 * lacks, each with one sentence of reason; what is already built is listed as built, not suggested again.
 *
 * Nothing is written. The editor (ModelItemEditor.tsx) provides the call through VerifyContext; where nothing provides
 * it (a test of a view alone, an older host) the button is not shown.
 */
import React, { createContext, useContext, useState } from "react";

export type VerifyState = "verified" | "differs" | "not checked";

export interface VerifyFigure {
  kpi: string;
  measure: string;
  state: VerifyState;
  said: string;
  sql?: string;
  dax?: string;
}

export interface VerifyLine {
  item: string;
  kind: string;
  state: VerifyState;
  said: string;
  differences?: { what: string; said: string }[];
  differences_total?: number;
  figures?: VerifyFigure[];
  doubled_totals?: { kpi: string; said: string; sql?: string[] }[];
  fix?: { label: string; how: string };
}

export interface VerifyStep {
  step: string;
  label: string;
  who: string;
  why: string;
  how?: string;
  state?: string;
  item?: string;
}

export interface VerifyAnswer {
  label: string;
  summary: string;
  counts: { verified?: number; differs?: number; not_checked?: number; items?: number };
  lines: VerifyLine[];
  sql?: { item: string; what: string; sql: string; dax?: string }[];
  next_steps?: VerifyStep[];
  already_built?: { step: string; label: string; name?: string }[];
  more?: VerifyStep[];
  time_budget?: { seconds: number; used?: number };
  compared_with?: string;
  error?: string;
  hint?: string;
}

export interface VerifySource {
  /** Runs the verifier on what this Model built; rejects when the engine cannot be reached. */
  run: () => Promise<VerifyAnswer>;
}

export const VerifyContext = createContext<VerifySource | undefined>(undefined);

export const VERIFY_LABEL = "Verify what was built";
export const BY_RULES = "A check by rules, not a review by AI.";
const WHO: Record<string, string> = { builder: "Builder", thinker: "Thinker", onto: "Onto" };
const STATE_WORD: Record<VerifyState, string> = { verified: "Verified", differs: "Differs", "not checked": "Not checked" };

/** The states in the order a person should read them: what differs first, then what was not checked, then what holds. */
export function sortLines(lines: VerifyLine[]): VerifyLine[] {
  const rank: Record<string, number> = { differs: 0, "not checked": 1, verified: 2 };
  return lines.map((l, i) => ({ l, i })).sort((a, b) => (rank[a.l.state] ?? 3) - (rank[b.l.state] ?? 3) || a.i - b.i).map((x) => x.l);
}

/** "2 verified, 1 differs, 1 not checked" from the answer's counts. */
export function countsLine(c: VerifyAnswer["counts"]): string {
  return `${c.verified ?? 0} verified, ${c.differs ?? 0} ${(c.differs ?? 0) === 1 ? "differs" : "differ"}, ${c.not_checked ?? 0} not checked`;
}

function Sql(props: { statements: { what: string; sql: string; dax?: string }[] }) {
  const [open, setOpen] = useState(false);
  if (!props.statements.length) return null;
  return (
    <div className="krusgraph-verify-sql">
      <button type="button" className="kg-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide the SQL" : "Show the SQL"}
      </button>
      {open && (
        <ul>
          {props.statements.map((s, i) => (
            <li key={`${s.what}-${i}`}>
              <span>{s.what}</span>
              <pre>{s.sql}</pre>
              {s.dax && <pre>{s.dax}</pre>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function VerifyResult(props: { answer: VerifyAnswer }) {
  const a = props.answer;
  if (a.error) {
    return (
      <p role="status" className="krusgraph-verify-error">
        {a.error} {a.hint ?? ""}
      </p>
    );
  }
  const steps = a.next_steps ?? [];
  return (
    <section className="krusgraph-verify-result" aria-label="What the verifier found">
      <p className="krusgraph-verify-label">{a.label || BY_RULES}</p>
      <p role="status">
        <strong>{a.summary}</strong>
      </p>
      <ul className="krusgraph-verify-lines">
        {sortLines(a.lines).map((l) => (
          <li key={`${l.kind}:${l.item}`} data-state={l.state}>
            <span className={`kg-state kg-state-${l.state.replace(" ", "-")}`}>{STATE_WORD[l.state] ?? l.state}</span> {l.said}
            {(l.differences ?? []).length > 1 && (
              <ul>
                {(l.differences ?? []).map((d, i) => (
                  <li key={i}>{d.said}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      <Sql statements={a.sql ?? []} />
      {a.time_budget && (
        <p className="krusgraph-verify-budget">
          {a.time_budget.used !== undefined
            ? `The time budget of ${a.time_budget.seconds} s ran out; what it did not reach is not checked.`
            : `Within a time budget of ${a.time_budget.seconds} s for the whole check.`}
        </p>
      )}
      {(steps.length > 0 || (a.already_built ?? []).length > 0) && (
        <section aria-label="Next steps" className="krusgraph-verify-next">
          <h4>Next steps</h4>
          <ol>
            {steps.map((s, i) => (
              <li key={`${s.step}-${i}`}>
                <strong>{s.label}</strong>
                {s.item ? ` (${s.item})` : ""}
                {s.state ? `: ${s.state}` : ""}
                <br />
                <span>
                  {WHO[s.who] ?? "Builder"}: {s.why}
                </span>
                {s.how && (
                  <>
                    <br />
                    <span className="kg-how">{s.how}</span>
                  </>
                )}
              </li>
            ))}
          </ol>
          {(a.already_built ?? []).map((d) => (
            <p key={d.step} className="kg-built">
              {d.label}: already built{d.name ? ` (${d.name})` : ""}.
            </p>
          ))}
          {(a.more ?? []).length > 0 && (
            <details>
              <summary>More</summary>
              <ul>
                {(a.more ?? []).map((m) => (
                  <li key={m.step}>
                    <strong>{m.label}</strong>
                    <br />
                    <span>
                      {WHO[m.who] ?? "Builder"}: {m.why}
                    </span>
                    {m.how && (
                      <>
                        <br />
                        <span className="kg-how">{m.how}</span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
    </section>
  );
}

/** The button and, once pressed, the result under it. `built`: how many items this Model has built (none: no button). */
export function VerifyButton(props: { built: number; busy?: boolean }) {
  const source = useContext(VerifyContext);
  const [state, setState] = useState<{ busy?: boolean; answer?: VerifyAnswer; error?: string }>({});
  if (!source || props.built <= 0) return null;
  const run = async () => {
    setState({ busy: true });
    try {
      setState({ answer: await source.run() });
    } catch {
      setState({ error: "The verifier could not be reached just now. Nothing was changed; try again." });
    }
  };
  return (
    <section className="krusgraph-verify" aria-label={VERIFY_LABEL}>
      <p>
        <button type="button" className="kg-toggle" disabled={state.busy || props.busy} onClick={() => void run()}>
          {state.busy ? "Reading back what was built…" : state.answer ? "Verify again" : VERIFY_LABEL}
        </button>{" "}
        <span className="krusgraph-verify-by">{BY_RULES} It only reads.</span>
      </p>
      {state.error && <p role="status">{state.error}</p>}
      {state.answer && <VerifyResult answer={state.answer} />}
    </section>
  );
}
