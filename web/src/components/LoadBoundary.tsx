import { Component, type ReactNode } from 'react'

export function PageLoading() {
  return (
    <div className="page-loading muted" role="status">
      Loading…
    </div>
  )
}

/** Catches a page that can't be shown, most often because an update replaced its file since this tab was opened. */
export class LoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(error: unknown) {
    console.error(error)
  }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="load-failed" role="alert">
        <p>This didn't load. Aniweb may have been updated since you opened it, or the connection dropped.</p>
        <button className="primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
