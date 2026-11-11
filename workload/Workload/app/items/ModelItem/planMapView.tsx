/**
 * The map, drawn by the MCP Apps cards' own code (cardMap.ts); redrawn when the map or a decision changes.
 * n223: its own file, loaded when a review shows it (lazyParts.tsx), so opening the editor does not wait for it.
 */
import React, { useEffect, useMemo, useRef } from "react";
import { Body1 } from "@fluentui/react-components";
import { MapData, drawPlanMap, overlay } from "./cardMap";
import { MAP_CSS } from "./cardMap.generated";
import { ReviewFile } from "./ModelItemDefinition";

export function PlanMap(props: { map?: MapData; review?: ReviewFile }) {
  const box = useRef<HTMLDivElement>(null);
  const shown = useMemo(() => (props.map ? overlay(props.map, props.review) : undefined), [props.map, props.review]);
  useEffect(() => {
    if (!box.current) return;
    try {
      drawPlanMap(box.current, shown);
    } catch {
      box.current.textContent = "The map could not be drawn here; the list shows the same keys and links.";
    }
  }, [shown]);
  if (!shown) return <Body1>The map appears after the next review. The list has every key and link.</Body1>;
  return (
    <div className="krusgraph-map">
      <style>{MAP_CSS}</style>
      <div ref={box} />
    </div>
  );
}
