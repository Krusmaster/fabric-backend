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

/**
 * SM3 (docs/SMOOTH/PLAN.md row 2): the same five steps and words as the Start Krusgraph card in the chat
 * (fabric_backend/start_flow.py, SHORT). tests/test_sm3_same_path.py reads both and fails when they differ.
 * Your data is the source; Check runs on its own after Find keys; Decide is what to build (the person's choice: the
 * three defaults ticked); Dry run is the preview; Create is the result and, after it, the data product.
 */
export const STEP_WORDS = ["Your data", "Check", "Decide", "Dry run", "Create"] as const;

const ORDER: { view: ModelView; label: string; also?: ModelView[] }[] = [
  { view: "empty", label: STEP_WORDS[0] },
  { view: "review", label: STEP_WORDS[1] },
  { view: "outputs", label: STEP_WORDS[2] },
  { view: "preview", label: STEP_WORDS[3] },
  { view: "result", label: STEP_WORDS[4], also: ["product"] },
];

/**
 * SM3: the default build, the same as the chat's (start_flow.SUGGESTED: create_pipeline, create_semantic_model,
 * create_data_agent). The chat's pipeline includes the silver and gold notebooks it runs, so they are ticked with it.
 */
export const DEFAULT_BUILD = ["pipeline", "semantic_model", "data_agent"] as const;
export const PIPELINE_PARTS = ["silver_notebook", "gold_views"] as const;

/** The steps for the current view; `reached` says how far the item got (a review exists, something was built). */
export function flowSteps(view: ModelView, reached: { review: boolean; preview: boolean; built: boolean }): FlowStep[] {
  const at = ORDER.findIndex((s) => s.view === view || (s.also ?? []).includes(view));
  const open = (v: ModelView) =>
    v === "empty" || (v === "review" || v === "outputs" ? reached.review : v === "preview" ? reached.preview : reached.built);
  return ORDER.map((s, i) => ({
    view: s.view,
    label: s.label,
    state: i < at ? "done" : i === at ? "now" : "ahead",
    canGo: i !== at && open(s.view),
  }));
}

/** The one line a phone shows instead of the row: "Step 2 of 5 · Check · Next: Decide". */
export function stepLine(steps: FlowStep[]): string {
  const i = steps.findIndex((s) => s.state === "now");
  if (i < 0) return "";
  const next = steps[i + 1];
  return `Step ${i + 1} of ${steps.length} · ${steps[i].label}` + (next ? ` · Next: ${next.label}` : "");
}

/** The empty state's one sentence, in the mascots' voice (Onto). */
export const FIRST_LINE = "Pick a lakehouse: I find its keys and links, prove them on the rows, and build only what you choose.";
