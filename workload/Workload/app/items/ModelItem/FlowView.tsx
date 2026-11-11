/**
 * n174: the data flow, drawn. Bronze -> silver -> gold -> what is built on the source, and the pipeline's steps, with the
 * plan map's classes and colours (kg-pic, the --kg-* tokens). Builder presents it. Every box with code is a button:
 * Enter, Space or a click unfolds its code below the picture (one open at a time), collapsed by default: a silver box's
 * notebook cell, a gold box's CREATE MATERIALIZED LAKE VIEW, a pipeline step's activity, the model's relationships and
 * measures. The code is exactly the dry run's (fabric_backend/data_flow.py); monospace, with a Copy button.
 *
 * Plain elements only (no Fluent component), so the view renders on the server in unit tests (FlowView.test.ts).
 */
import React, { useMemo, useState } from "react";
import { DataFlow } from "./engineClient";
import { boxLabel, layoutFlow, toggleOpen, togglesOn } from "./dataFlow";
import { MAP_CSS, MASCOT_COLOURS, MASCOT_NAMES } from "./cardMap.generated";
import { MascotFigure } from "./mascotFigure";

export function FlowView(props: { flow: DataFlow; mascotsOn?: boolean; initialOpen?: string; idPrefix?: string }) {
  const { flow } = props;
  const [open, setOpen] = useState<string | undefined>(props.initialOpen);
  const [copied, setCopied] = useState<string>();
  const lay = useMemo(() => layoutFlow(flow), [flow]);
  const prefix = props.idPrefix ?? "kg-flow";
  const panelId = `${prefix}-code`;
  const node = open ? flow.nodes.find((n) => n.id === open && n.code) : undefined;
  const toggle = (id: string) => {
    setOpen((o) => toggleOpen(o, id));
    setCopied(undefined);
  };
  const copy = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
    } catch {
      setCopied(undefined);
    }
  };
  return (
    <section className="krusgraph-flow" aria-label="The data flow, bronze to gold">
      <style>{MAP_CSS}</style>
      {props.mascotsOn !== false ? (
        <ul className="krusgraph-mascots">
          <li className="krusgraph-say krusgraph-say-builder" data-mascot="builder" style={{ ["--kg-mascot" as string]: MASCOT_COLOURS.builder.fill }}>
            <MascotFigure kind="builder" pose="point" />
            <div className="krusgraph-bubble">
              <span className="krusgraph-who">{MASCOT_NAMES.builder}</span>
              <p>{flow.said}</p>
            </div>
          </li>
        </ul>
      ) : (
        <p>{flow.said}</p>
      )}
      <div className="kg-pic krusgraph-flow-pic">
        <svg viewBox={`0 0 ${lay.width} ${lay.height}`} width={lay.width} height={lay.height} role="group"
          aria-label="Bronze tables, silver tables, gold views and what is built on them; each box with code is a button">
          {lay.columns.map((c) => (
            <text key={c.id} className="kgf-col" x={c.x} y={14}>
              {c.title}
            </text>
          ))}
          {lay.pipelineTitle && (
            <text className="kgf-col" x={lay.pipelineTitle.x} y={lay.pipelineTitle.y}>
              {lay.pipelineTitle.text}
            </text>
          )}
          {lay.paths.map((p, i) => (
            <path key={`${p.edge.from}>${p.edge.to}:${i}`} className={`kgf-e${p.dashed ? " off" : ""}`} d={p.d}
              data-from={p.edge.from} data-to={p.edge.to}>
              <title>{[p.edge.label, p.edge.rule ? `rule ${p.edge.rule}` : ""].filter(Boolean).join(", ")}</title>
            </path>
          ))}
          {lay.boxes.map((b) => {
            const n = b.node;
            const isOpen = open === n.id;
            const clickable = !!n.code;
            const cls = `kgc-n kgf-n kgf-${n.column}${n.built ? "" : " off"}${isOpen ? " open" : ""}${clickable ? " has-code" : ""}`;
            const extra = clickable
              ? {
                  role: "button",
                  tabIndex: 0,
                  "aria-expanded": isOpen,
                  "aria-controls": panelId,
                  onClick: () => toggle(n.id),
                  onKeyDown: (e: React.KeyboardEvent) => {
                    if (togglesOn(e.key)) {
                      e.preventDefault();
                      toggle(n.id);
                    }
                  },
                }
              : { role: "img" };
            return (
              <g key={n.id} className={cls} data-id={n.id} transform={`translate(${b.x},${b.y})`} aria-label={boxLabel(n, isOpen)} {...extra}>
                <title>{n.label}</title>
                <rect width={b.w} height={b.h} rx={6} />
                <text x={10} y={18}>
                  {b.label}
                </text>
                {b.lines.map((l, i) => (
                  <text key={i} className="kgc-sub" x={10} y={34 + i * 15}>
                    {l}
                  </text>
                ))}
                {n.pills.length > 0 && (
                  <g className="kgf-pills" transform={`translate(10,${b.h - 18})`}>
                    {n.pills.slice(0, 6).map((r, i) => (
                      <g key={i} className="kgc-lab" transform={`translate(${i * 30},0)`}>
                        <rect width={26} height={13} rx={6} />
                        <text className="r" x={13} y={10} textAnchor="middle">
                          {r}
                        </text>
                      </g>
                    ))}
                  </g>
                )}
                {clickable && (
                  <text className="kgf-more" x={b.w - 10} y={18} textAnchor="end" aria-hidden="true">
                    {isOpen ? "−" : "+"}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="kg-legend krusgraph-flow-legend">
        <span className="lg">Solid: part of this build</span>
        <span className="lg off">Dashed: not part of this build</span>
        <span>Click a box, or press Enter on it, to see its code.</span>
      </p>
      {flow.notes.map((t) => (
        <p key={t} className="krusgraph-flow-note">
          {t}
        </p>
      ))}
      <div id={panelId} className="krusgraph-code" role="region" aria-label={node ? node.code_title || node.label : "Code"} hidden={!node}>
        {node && (
          <>
            <div className="krusgraph-code-head">
              <strong>{node.code_title || node.label}</strong>
              <span className="krusgraph-code-lang">{node.language}</span>
              <button type="button" className="kg-toggle" onClick={() => copy(node.code as string, node.id)}>
                {copied === node.id ? "Copied" : "Copy"}
              </button>
              <button type="button" className="kg-toggle" onClick={() => toggle(node.id)}>
                Close
              </button>
            </div>
            <pre tabIndex={0}>
              <code>{node.code}</code>
            </pre>
          </>
        )}
      </div>
    </section>
  );
}
