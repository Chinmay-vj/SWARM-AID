import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  error: Error | null;
}

/** Catches render errors per route so one failing view does not blank the dashboard. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) console.error("View error", error, info.componentStack);
  }

  override componentDidUpdate(prev: { resetKey?: string }): void {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  override render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="panel state" role="alert">
        <h3>This view failed to render</h3>
        <p>
          The rest of the dashboard is still available. The error was not caused by any action being executed.
        </p>
        <button className="btn" onClick={() => this.setState({ error: null })}>
          Try again
        </button>
      </div>
    );
  }
}
