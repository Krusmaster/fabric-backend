import React from "react";
import { Body1, Caption1 } from "@fluentui/react-components";
import type { MascotKind } from "./ModelItemViews";
import { MASCOT_COLOURS, MASCOT_GLAD, MASCOT_NAMES } from "./cardMap.generated";

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

/** One mascot with its bubble. n216: the figure is the 3D one from the film and the site (mascotFigure.tsx),
 * decorative (aria-hidden); the sentence is the bubble's text. Glad poses only when a check passed (MASCOT_GLAD). */
export function MascotSays(props: { kind: MascotKind; text?: string; pose?: string; glad?: boolean; children?: React.ReactNode }) {
  if (!props.text && !props.children) return null;
  let pose = props.pose ?? "rest";
  if (!props.glad && MASCOT_GLAD.includes(pose)) pose = "explain";
  return (
    <li className={`krusgraph-say krusgraph-say-${props.kind}${props.glad ? " glad" : ""}`} data-mascot={props.kind}
      style={{ ["--kg-mascot" as string]: MASCOT_COLOURS[props.kind].fill }}>
      <MascotFigure kind={props.kind} pose={pose} />
      <div className="krusgraph-bubble">
        <Caption1 className="krusgraph-who">{MASCOT_NAMES[props.kind]}</Caption1>
        {props.text && <Body1>{props.text}</Body1>}
        {props.children}
      </div>
    </li>
  );
}
