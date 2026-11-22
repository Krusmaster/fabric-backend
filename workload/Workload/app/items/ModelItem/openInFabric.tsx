/**
 * ED3 (Gustav's editor test of 21 November 2026, part 3: "jag vill kunna öppna notebooken från Krusgraph eller ha en ny
 * flik"): every item Krusgraph created gets one primary "Open in Fabric", which opens the item in a new browser tab.
 *
 * - The address: the item's page in the Fabric portal, https://app.fabric.microsoft.com + the starter kit's own
 *   getFrontendPath (NavigationController.ts: /groups/<workspace>/<type path>/<id>), the same path navigateToItem
 *   uses on the Data product step.
 * - The tab: the host opens it with the workload client's navigation.openBrowserTab (Microsoft Learn, Fabric
 *   Extensibility Toolkit, "Workload client API: navigation", openBrowserTab), since the editor's frame may not open
 *   tabs itself; the link's own href with target=_blank rel=noopener is the fallback, also for keyboard and screen
 *   readers.
 */
import React, { useContext } from "react";
import { Open20Regular } from "@fluentui/react-icons";
import { getFrontendPath } from "../../controller/NavigationController";
import { FileContext } from "./fileOffer";

export const FABRIC_PORTAL = "https://app.fabric.microsoft.com";

export interface FabricItemRef {
  id: string;
  workspaceId: string;
  type: string;
  displayName?: string;
}

/** The item's page in the Fabric portal (undefined without an id or a workspace). */
export function fabricItemUrl(item: Partial<FabricItemRef> | undefined): string | undefined {
  if (!item?.id || !item.workspaceId || !item.type) return undefined;
  return FABRIC_PORTAL + getFrontendPath(item.type, item.workspaceId, item.id);
}

/** Opens a URL in a new browser tab through the host, else with window.open (noopener). */
export async function openInNewTab(url: string, open?: (url: string) => Promise<void>): Promise<void> {
  try {
    if (open) {
      await open(url);
      return;
    }
  } catch {
    /* the host refused or is missing: the browser's own new tab below */
  }
  if (typeof window !== "undefined") window.open(url, "_blank", "noopener");
}

/** The primary "Open in Fabric" button of a created item: a link styled as a button, opening a new tab. */
export function OpenInFabric(props: { item: Partial<FabricItemRef>; label?: string; appearance?: "primary" | "secondary" }) {
  const source = useContext(FileContext);
  const url = fabricItemUrl(props.item);
  if (!url) return null;
  const label = props.label ?? "Open in Fabric";
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" data-open-in-fabric={props.item.type}
      className={`kg-open-fabric kg-open-fabric-${props.appearance ?? "primary"}`}
      aria-label={props.item.displayName ? `${label}: ${props.item.displayName} (opens a new tab)` : `${label} (opens a new tab)`}
      onClick={(e) => {
        e.preventDefault();
        void openInNewTab(url, source?.open);
      }}>
      <Open20Regular aria-hidden /> {label}
    </a>
  );
}
