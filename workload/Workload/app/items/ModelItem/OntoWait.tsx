/**
 * n223: the one loading component of the Krusgraph Model editor. Onto at the top with a gentle motion (still under
 * prefers-reduced-motion), the step's name, its progress where the parts are known ("3 of 7 tables counted"), after
 * SLOW_AFTER_S one honest line about what is slow and after OFFER_AFTER_S what the person can do (keep waiting, see the
 * steps so far, cancel when the step only reads). Skeleton rows below stand in for the page that is coming, so a wait is
 * never a blank page. The words are waitWords.ts's; this file only draws them.
 *
 * With the mascots off the figure is left out and the same words show. Native elements and Fabric's tokens with light
 * and dark fallbacks; the step and the slow line are announced politely (aria-live), the buttons are in the tab order.
 */
import React, { useEffect, useState } from "react";
import { MascotFigure } from "./mascotFigure";
import { Wait, waitLines } from "./waitWords";

export const WAIT_CSS = `
.kg-wait{--kg-w-fg:var(--colorNeutralForeground1,#1f1f1f);--kg-w-fg2:var(--colorNeutralForeground2,#424242);
--kg-w-bg2:var(--colorNeutralBackground2,#f5f5f5);--kg-w-bg3:var(--colorNeutralBackground3,#ebebeb);
--kg-w-line:var(--colorNeutralStroke2,#e0e0e0);--kg-w-brand:var(--colorBrandForeground1,#0f6cbd);--kg-w-focus:var(--colorStrokeFocus2,#000000);
color:var(--kg-w-fg);font-family:var(--fontFamilyBase,"Segoe UI",system-ui,sans-serif);font-size:14px;line-height:1.45;
padding:16px 0;max-width:720px}
@media (prefers-color-scheme:dark){.kg-wait{--kg-w-fg:var(--colorNeutralForeground1,#f0f0f0);--kg-w-fg2:var(--colorNeutralForeground2,#d6d6d6);
--kg-w-bg2:var(--colorNeutralBackground2,#2b2b2b);--kg-w-bg3:var(--colorNeutralBackground3,#333333);--kg-w-line:var(--colorNeutralStroke2,#525252);
--kg-w-brand:var(--colorBrandForeground1,#479ef5);--kg-w-focus:var(--colorStrokeFocus2,#ffffff)}}
.kg-wait-top{display:flex;align-items:flex-start;gap:12px}
.kg-wait-fig{flex:0 0 auto;animation:kg-wait-bob 2.4s ease-in-out infinite}
.kg-wait-spin{flex:0 0 auto;width:20px;height:20px;margin-top:2px;border-radius:50%;border:2px solid var(--kg-w-line);
border-top-color:var(--kg-w-brand);animation:kg-wait-turn 1s linear infinite}
.kg-wait-text{display:flex;flex-direction:column;gap:2px;min-width:0}
.kg-wait-label{font-weight:600}
.kg-wait-muted{color:var(--kg-w-fg2)}
.kg-wait-bar{height:4px;border-radius:2px;background:var(--kg-w-line);overflow:hidden;margin:6px 0 2px;max-width:320px}
.kg-wait-bar span{display:block;height:100%;background:var(--kg-w-brand);transition:width .3s ease}
.kg-wait-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.kg-wait button{font:inherit;padding:4px 12px;border-radius:4px;border:1px solid var(--kg-w-line);background:var(--kg-w-bg2);color:var(--kg-w-fg);cursor:pointer}
.kg-wait button:focus-visible{outline:2px solid var(--kg-w-focus);outline-offset:2px}
.kg-wait ol{margin:8px 0 0;padding-left:20px;color:var(--kg-w-fg2)}
.kg-skel{display:flex;flex-direction:column;gap:10px;margin-top:20px}
.kg-skel span{display:block;height:14px;border-radius:4px;background:linear-gradient(90deg,var(--kg-w-bg2) 0%,var(--kg-w-bg3) 50%,var(--kg-w-bg2) 100%);
background-size:200% 100%;animation:kg-wait-shine 1.6s ease-in-out infinite}
.kg-skel span:nth-child(1){width:42%;height:20px}.kg-skel span:nth-child(2){width:88%}.kg-skel span:nth-child(3){width:76%}
.kg-skel span:nth-child(4){width:82%}.kg-skel span:nth-child(5){width:64%}
@keyframes kg-wait-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
@keyframes kg-wait-turn{to{transform:rotate(360deg)}}
@keyframes kg-wait-shine{0%{background-position:100% 0}100%{background-position:-100% 0}}
@media (prefers-reduced-motion:reduce){.kg-wait-fig,.kg-wait-spin,.kg-skel span{animation:none}.kg-wait-bar span{transition:none}}
`;

/** Grey rows where the page will be: shown under a wait and while a lazy part of the editor loads. */
export function Skeleton(props: { rows?: number; label?: string }) {
  const n = Math.max(1, Math.min(props.rows ?? 5, 5));
  return (
    <div className="kg-skel" aria-hidden={props.label ? undefined : true} role={props.label ? "status" : undefined} aria-label={props.label}>
      {Array.from({ length: n }, (_, i) => <span key={i} />)}
    </div>
  );
}

/** The clock of a wait: re-renders once a second while it runs, so the 10 and 30 second lines appear. */
export function useNow(running: boolean, tick = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return undefined;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), tick);
    return () => clearInterval(t);
  }, [running, tick]);
  return now;
}

export interface OntoWaitProps {
  wait: Wait;
  mascotsOn?: boolean;
  /** stop waiting (offered only when the wait is cancellable) */
  onCancel?: () => void;
  /** the page that is coming: grey rows under the words (false: the page stays and the wait is a line above it) */
  skeleton?: number | false;
  /** for tests and the static renders: the clock instead of Date.now() */
  now?: number;
}

export function OntoWait(props: OntoWaitProps) {
  const clock = useNow(props.now === undefined);
  const now = props.now ?? clock;
  const lines = waitLines(props.wait, now);
  const [kept, setKept] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const p = props.wait.progress;
  const pct = p && p.total > 0 ? Math.round((100 * Math.min(p.done, p.total)) / p.total) : undefined;
  return (
    <div className="kg-wait" aria-busy="true" data-wait-kind={props.wait.kind} data-testid="kg-wait">
      <style>{WAIT_CSS}</style>
      <div className="kg-wait-top">
        {props.mascotsOn !== false
          ? <span className="kg-wait-fig"><MascotFigure kind="onto" pose="think" /></span>
          : <span className="kg-wait-spin" aria-hidden="true" />}
        <div className="kg-wait-text">
          {/* the step and its progress are announced once each as they change; the seconds are not */}
          <div role="status" aria-live="polite">
            <span className="kg-wait-label">{props.mascotsOn !== false ? "Onto: " : ""}{lines.label}</span>
            {lines.progress && <span className="kg-wait-muted"> {lines.progress}.</span>}
          </div>
          {pct !== undefined && (
            <div className="kg-wait-bar" role="progressbar" aria-valuemin={0} aria-valuemax={p!.total} aria-valuenow={Math.min(p!.done, p!.total)}
              aria-valuetext={lines.progress} aria-label={lines.label}>
              <span style={{ width: `${pct}%` }} />
            </div>
          )}
          {lines.words && <span className="kg-wait-muted">{lines.words}</span>}
          <div aria-live="polite">
            {lines.slow && <span className="kg-wait-muted" data-wait-line="slow">{lines.slow}</span>}
            {lines.offer && !kept && <div data-wait-line="offer">{lines.offer}</div>}
          </div>
          {lines.offer && (
            <div className="kg-wait-actions">
              {!kept && <button type="button" onClick={() => setKept(true)}>Keep waiting</button>}
              {lines.canSeeSteps && (
                <button type="button" aria-expanded={showSteps} onClick={() => setShowSteps((s) => !s)}>
                  {showSteps ? "Hide the steps" : "See the steps so far"}
                </button>
              )}
              {lines.canCancel && props.onCancel && <button type="button" onClick={props.onCancel}>Cancel</button>}
            </div>
          )}
          {showSteps && lines.canSeeSteps && (
            <ol aria-label="The steps so far">
              {props.wait.steps.map((s, i) => <li key={i}>{s.at}s: {s.text}</li>)}
            </ol>
          )}
        </div>
      </div>
      {props.skeleton !== false && <Skeleton rows={typeof props.skeleton === "number" ? props.skeleton : 5} />}
    </div>
  );
}
