/**
 * n223: the editor's heavy parts load when they are first shown, not with the editor: the map (planMapView.tsx), the
 * data flow (FlowView.tsx) and the Data product page (DataProductView.tsx). Each is its own chunk; webpackPrefetch asks
 * the browser to fetch it while idle after the editor has loaded, so the next step rarely waits for it. While a chunk
 * loads, grey skeleton rows stand where it will be (OntoWait.Skeleton), never a blank space.
 */
import React, { Suspense } from "react";
import type { MapData } from "./cardMap";
import type { DataFlow } from "./engineClient";
import type { ReviewFile } from "./ModelItemDefinition";
import type { DataProductProps } from "./DataProductView";
import { Skeleton } from "./OntoWait";

export const loadPlanMap = () => import(/* webpackChunkName: "kg-map", webpackPrefetch: true */ "./planMapView");
export const loadFlowView = () => import(/* webpackChunkName: "kg-flow", webpackPrefetch: true */ "./FlowView");
export const loadDataProduct = () => import(/* webpackChunkName: "kg-product", webpackPrefetch: true */ "./DataProductView");

const LazyPlanMap = React.lazy(() => loadPlanMap().then((m) => ({ default: m.PlanMap })));
const LazyFlowView = React.lazy(() => loadFlowView().then((m) => ({ default: m.FlowView })));
const LazyDataProduct = React.lazy(() => loadDataProduct().then((m) => ({ default: m.DataProductView })));

/** Fetch every lazy part now (after the first paint), so a later step shows it at once. Errors are left to the step. */
export function preloadParts(): void {
  for (const load of [loadPlanMap, loadFlowView, loadDataProduct]) void load().catch((): undefined => undefined);
}

export function PlanMap(props: { map?: MapData; review?: ReviewFile }) {
  return (
    <Suspense fallback={<Skeleton rows={4} label="Drawing the map…" />}>
      <LazyPlanMap {...props} />
    </Suspense>
  );
}

export function FlowView(props: { flow: DataFlow; mascotsOn?: boolean; initialOpen?: string; idPrefix?: string }) {
  return (
    <Suspense fallback={<Skeleton rows={4} label="Drawing the data flow…" />}>
      <LazyFlowView {...props} />
    </Suspense>
  );
}

export function DataProductPage(props: DataProductProps) {
  return (
    <Suspense fallback={<Skeleton rows={5} label="Opening the Data product page…" />}>
      <LazyDataProduct {...props} />
    </Suspense>
  );
}
