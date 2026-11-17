/**
 * W13: where you are in the Model item, shown at the top of the canvas (FlowSteps.tsx), as docs/WORKLOAD-UX-DESIGN.md
 * section 3 designed it: each step done, now or ahead, the current one marked for screen readers. Ribbon tabs never
 * switch the view (Learn, publishing requirements for items, 3.1), so this lives in the canvas. Pure, no React.
 */
import type { ModelView } from "./ModelItemDefinition";

export interface FlowStep {
  view: ModelView;
  label: string;
  state: "done" | "now" | "ahead";
  /** a done step can be gone back to */
  canGo: boolean;
}

const ORDER: { view: ModelView; label: string }[] = [
  { view: "empty", label: "Source" },
  { view: "review", label: "Keys and links" },
  { view: "outputs", label: "Choose" },
  { view: "preview", label: "Dry run" },
  { view: "result", label: "Built" },
  { view: "product", label: "Data product" },
];

/** The steps for the current view; `reached` says how far the item got (a review exists, something was built). */
export function flowSteps(view: ModelView, reached: { review: boolean; preview: boolean; built: boolean }): FlowStep[] {
  const at = ORDER.findIndex((s) => s.view === view);
  const open = (v: ModelView) =>
    v === "empty" || (v === "review" || v === "outputs" ? reached.review : v === "preview" ? reached.preview : reached.built);
  return ORDER.map((s, i) => ({
    view: s.view,
    label: s.label,
    state: i < at ? "done" : i === at ? "now" : "ahead",
    canGo: i !== at && open(s.view),
  }));
}

/** The one line a phone shows instead of the row: "Step 2 of 6 · Keys and links · Next: Choose". */
export function stepLine(steps: FlowStep[]): string {
  const i = steps.findIndex((s) => s.state === "now");
  if (i < 0) return "";
  const next = steps[i + 1];
  return `Step ${i + 1} of ${steps.length} · ${steps[i].label}` + (next ? ` · Next: ${next.label}` : "");
}

/** The empty state's one sentence, in the mascots' voice (Onto). */
export const FIRST_LINE = "Pick a lakehouse: I find its keys and links, prove them on the rows, and build only what you choose.";
