/**
 * Screenshot harness: the Krusgraph Model editor's own view components (workload/Workload/app/items/ModelItem/) with the
 * engine's answers on seed.py's synthetic shop schema (fixtures/, written by build_fixtures.py). One view per URL hash:
 * #review, #outputs, #preview, #flow. FluentProvider with the app's theme as index.ui.tsx wraps the editor; mascots on;
 * every callback is a no-op. The fixed label above each view says the data is synthetic.
 * Bundled and photographed by shoot.js.
 */
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { FluentProvider } from "@fluentui/react-components";
import { fabricLightTheme } from "../../Workload/app/theme";
import { OutputsView, PreviewView, ReviewView } from "../../Workload/app/items/ModelItem/ModelItemViews";
import { FlowView } from "../../Workload/app/items/ModelItem/FlowView";
import { MASCOT_CSS } from "../../Workload/app/items/ModelItem/cardMap.generated";
import { createLabel } from "../../Workload/app/items/ModelItem/buildWords";
import review from "./fixtures/review.json";
import outputs from "./fixtures/outputs.json";
import preview from "./fixtures/preview.json";
import flow from "./fixtures/flow.json";

const LABEL = "Synthetic data (shop schema) — rendered from the Krusgraph Model editor's components";
const none = () => undefined;

function View({ name }: { name: string }) {
  switch (name) {
    case "review":
      return (
        <ReviewView source={review.source as never} review={review.review as never} map={review.map as never} answered={{}}
          checking={false} mascotsOn onToggleMascots={none} onDecide={none} onAcceptAll={none} onCheck={none} onChoice={none} />
      );
    case "outputs":
      return (
        <OutputsView choices={outputs.choices as never} onChange={none} created={[]} product={outputs.product}
          onProduct={none} onOpen={none} onPreview={none} />
      );
    case "preview":
      return <PreviewView answer={preview.answer as never} onCreate={none} mascotsOn createLabel={createLabel(preview.answer as never)} />;
    case "flow":
      // FlowView as PreviewView places it (inside .krusgraph-view, after the mascots' styles), with one box unfolded.
      return (
        <div className="krusgraph-view">
          <style>{MASCOT_CSS}</style>
          <FlowView flow={flow.flow as never} mascotsOn initialOpen={flow.open} idPrefix="kg-flow-preview" />
        </div>
      );
    default:
      return <p style={{ padding: 24 }}>Choose #review, #outputs, #preview or #flow.</p>;
  }
}

function Harness() {
  const [name, setName] = useState(location.hash.slice(1));
  useEffect(() => {
    const on = () => setName(location.hash.slice(1));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return (
    <FluentProvider theme={fabricLightTheme}>
      <div className="screens-label" role="note">{LABEL}</div>
      <main id="screen" data-view={name} key={name}>
        <View name={name} />
      </main>
    </FluentProvider>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
