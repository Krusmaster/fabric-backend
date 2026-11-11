import React from "react";
import type { MascotKind } from "./ModelItemViews";

/* Krusgraph (n216): the editor's mascots are the glossy 3D figures of the overview film and krusgraph.com's home page,
 * the same characters as the website and the sales deck. The images are cut from the film's closing frame by
 * tools/mascot_renders.py (112 x 112 px, transparent ground) and served from /assets/mascots/ (app/assets is copied
 * by webpack). They show at 48 px, so 2x displays get the full render.
 *
 * The film has one pose per figure (resting). The poses the editor asks for (point, explain, think, notice, calm,
 * celebrate) are kept as data-pose and drawn as a small motion of the whole figure (ModelItem.scss): a lean, a tilt or
 * a hop, stilled under prefers-reduced-motion. Renders of each pose are listed in docs/MASCOT-ART-NEEDED.md.
 * The figure is decorative (alt=""): the name and the sentence are in the bubble beside it. */
export const MASCOT_IMG: Record<MascotKind, string> = {
  onto: "/assets/mascots/onto.png",
  thinker: "/assets/mascots/thinker.png",
  builder: "/assets/mascots/builder.png",
};

export function MascotFigure(props: { kind: MascotKind; pose?: string }) {
  return (
    <span className="krusgraph-fig" data-kind={props.kind} data-pose={props.pose ?? "rest"} aria-hidden="true">
      <img src={MASCOT_IMG[props.kind]} alt="" width={48} height={48} draggable={false} />
    </span>
  );
}
