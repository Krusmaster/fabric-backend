/**
 * WB11: the Fabric item icon beside the name of a Fabric item type, wherever the editor names one (fabricIcons.ts has
 * the source, the terms and the map). Native elements only, so the Data product page (its own CSS) and the Fluent views
 * both use it. The icon is a label for the item type: it always stands next to the type's name in text, its alt is
 * empty when that text already names the type (altBeside), and width and height are set so nothing moves when it loads.
 */
import React from "react";
import { ICON_SIZE, altBeside, typeIcon } from "./fabricIcons";

/** The icon of a Fabric item type, or nothing for a type without one. `beside` is the text it stands next to. */
export function TypeIcon(props: { type?: string | null; beside?: string }) {
  const icon = typeIcon(props.type ?? undefined);
  if (!icon) return null;
  return <img className="krusgraph-item-icon" src={icon.src} alt={altBeside(icon.alt, props.beside)} width={ICON_SIZE} height={ICON_SIZE} />;
}

/** The type's name with its icon at its left: "[icon] Lakehouse". `text` defaults to the type's own word. */
export function TypeName(props: { type?: string | null; text: string; className?: string }) {
  return (
    <span className={`krusgraph-item-title${props.className ? ` ${props.className}` : ""}`}>
      <TypeIcon type={props.type} beside={props.text} />
      {props.text}
    </span>
  );
}
