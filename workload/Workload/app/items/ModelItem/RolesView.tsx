/**
 * BL58: the semantic model card's row-level security roles (BL46), one tick box per proposed role, unticked by default.
 * Each box is named by the role and described by its column, rule, the tables it filters and whether it fits this
 * model's tables (aria-describedby); a role that does not fit is shown disabled with the reason. Without onRoles (the
 * result after Create) the roles are listed as added or not added. Words come from roleWords.ts; nothing here calls
 * Fabric, and no row value is ever shown.
 */
import React from "react";
import { Body1, Button, Caption1, Checkbox, Subtitle2 } from "@fluentui/react-components";
import { BuildCard } from "./engineClient";
import { ROLES_AGAIN, ROLES_TITLE, ROLES_UNCHANGED, mapTableLine, roleLine, rolesOf, tickedRoles, ticksDiffer, toggleRole } from "./roleWords";

function idOf(prefix: string, column: string): string {
  return `${prefix}-${column.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

export function RolesPanel(props: { card: BuildCard; saved?: string[]; onRoles?: (roles: string[]) => void; onDryRunAgain?: () => void; busy?: boolean }) {
  const r = rolesOf(props.card);
  if (!r) return null;
  if (!props.onRoles) {
    return (
      <div className="kg-roles" data-bl58="roles">
        <Subtitle2>Row-level security roles</Subtitle2>
        <ul className="krusgraph-list" aria-label="Row-level security roles">
          {r.proposed.map((x) => (
            <li key={x.column}><Body1>{`${x.role}: ${x.added ? "added to the model" : "not added"}. ${roleLine(x)}`}</Body1></li>
          ))}
        </ul>
      </div>
    );
  }
  const now = tickedRoles(r, props.saved);
  const prefix = `kg-role-${props.card.name}`;
  return (
    <fieldset className="krusgraph-output kg-roles" data-bl58="roles">
      <legend>{ROLES_TITLE}</legend>
      <Caption1 as="p" block>{ROLES_UNCHANGED}</Caption1>
      {r.proposed.map((x) => {
        const desc = idOf(prefix, x.column);
        return (
          <div key={x.column} className="kg-role" data-role={x.column} data-fits={x.fits ? "yes" : "no"}>
            <Checkbox label={x.role} checked={now.includes(x.column)} disabled={!x.fits || !!props.busy} aria-describedby={desc}
              onChange={(_, d) => props.onRoles?.(toggleRole(r, now, x.column, !!d.checked))} />
            <Caption1 as="p" block id={desc} className="kg-role-line" style={{ margin: "0 0 8px 32px" }}>{roleLine(x)}</Caption1>
          </div>
        );
      })}
      <Caption1 as="p" block>{mapTableLine(r.map_table)}</Caption1>
      {/* a live region that is always there, so a screen reader hears the line when a tick changes it */}
      <div role="status">
        {ticksDiffer(r, props.saved) && <Caption1 as="p" block>{ROLES_AGAIN}</Caption1>}
      </div>
      {ticksDiffer(r, props.saved) && props.onDryRunAgain && (
        <Button size="small" appearance="secondary" disabled={!!props.busy} onClick={() => props.onDryRunAgain?.()}>Dry run again</Button>
      )}
    </fieldset>
  );
}
