/**
 * n215: an error while the editor renders unmounted the whole React tree and left Fabric's frame white. This boundary
 * keeps the error visible: what went wrong, in the error's own words, and Reload. Nothing is sent anywhere.
 */
import React from "react";
import { Body1, Button, Caption1, Title3 } from "@fluentui/react-components";

interface State {
  error?: Error;
}

export class EditorErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = {};

  static getDerivedStateFromError(error: unknown): State {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    console.error("Krusgraph Model editor:", error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div role="alert" style={{ padding: 24, display: "flex", flexDirection: "column", gap: 12, maxWidth: 720 }}>
        <Title3>Something went wrong in the editor</Title3>
        <Body1>Your saved model is not changed. Reload the editor; if this comes back, send this text to Krusgraph's support.</Body1>
        <Caption1 style={{ fontFamily: "monospace", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {error.name}: {error.message}
        </Caption1>
        <div>
          <Button appearance="primary" onClick={() => window.location.reload()}>Reload</Button>
        </div>
      </div>
    );
  }
}
