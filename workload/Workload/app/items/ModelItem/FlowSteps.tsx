/** W13: the step indicator at the top of the canvas (stepWords.ts): a named navigation landmark, the current step
 * marked aria-current="step", done steps as buttons back, a one-line form on a narrow canvas (ModelItem.scss). */
import React from "react";
import { Caption1 } from "@fluentui/react-components";
import type { ModelView } from "./ModelItemDefinition";
import { FlowStep, stepLine } from "./stepWords";

export function FlowSteps(props: { steps: FlowStep[]; onGo: (v: ModelView) => void }) {
  return (
    <nav className="kg-steps" aria-label="Where you are">
      <ol className="kg-steps-row">
        {props.steps.map((s, i) => (
          <li key={s.view} className={`kg-step kg-step-${s.state}`} aria-current={s.state === "now" ? "step" : undefined}>
            <span className="kg-step-mark" aria-hidden="true">{s.state === "done" ? "✓" : i + 1}</span>
            {s.canGo && s.state !== "now" ? (
              <button type="button" className="kg-step-go" onClick={() => props.onGo(s.view)}>
                {s.label}<span className="kg-sr">{s.state === "done" ? " (done)" : ""}</span>
              </button>
            ) : (
              <span className="kg-step-label">{s.label}<span className="kg-sr">{s.state === "done" ? " (done)" : s.state === "ahead" ? " (not yet)" : ""}</span></span>
            )}
          </li>
        ))}
      </ol>
      <Caption1 className="kg-steps-line" aria-hidden="true">{stepLine(props.steps)}</Caption1>
    </nav>
  );
}
