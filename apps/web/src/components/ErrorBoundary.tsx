import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      const e = this.state.error;
      return (
        <div
          style={{
            minHeight: "100vh",
            padding: "1.5rem",
            background: "#0c0f12",
            color: "#e8eef5",
            fontFamily: "system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: "1.25rem", marginBottom: "0.75rem" }}>Page crashed</h1>
          <p style={{ color: "#8b98a8", marginBottom: "1rem" }}>
            Open DevTools (F12) → Console for details. Hard refresh (Ctrl+Shift+R) after fixing.
          </p>
          <pre
            style={{
              fontSize: "0.8rem",
              overflow: "auto",
              padding: "1rem",
              borderRadius: "8px",
              background: "#141a21",
              border: "1px solid #243040",
              whiteSpace: "pre-wrap",
            }}
          >
            {e.stack || e.message}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}
