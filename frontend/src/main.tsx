import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SystemModeProvider } from "./hooks/useSystemMode";
import App from "./App";
import "./index.css";

// Error boundary: a crashing panel must not take the whole console down.
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6">
          <div className="rounded-lg border border-neg/30 bg-neg/5 p-4">
            <div className="text-sm font-medium text-neg">Uncaught render error</div>
            <div className="mt-1 text-xs text-muted">{this.state.error.message}</div>
            <button
              onClick={() => window.location.reload()}
              className="mt-3 rounded border border-ink-600 px-3 py-1 text-xs text-muted hover:text-accent"
            >
              Reload console
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <SystemModeProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </SystemModeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
