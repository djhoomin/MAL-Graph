import { lazy, Suspense, useEffect, useRef } from 'react'
import { AppMenu } from './components/AppMenu'
import { FiltersButton } from './components/FiltersButton'
import { GolfPanel } from './components/GolfPanel'
import { GraphCanvas } from './components/GraphCanvas'
import { ChatIcon, CloseIcon, FitIcon } from './components/icons'
import { LoadBoundary, PageLoading } from './components/LoadBoundary'
import { NodeCard } from './components/NodeCard'
import { NodeList } from './components/NodeList'
import { PathBar } from './components/PathBar'
import { SearchBar } from './components/SearchBar'
import { SyncPill, Welcome } from './components/Welcome'
import { useGolf } from './golf'
import { useStore } from './store'

// The markdown libraries come with Ask, so they wait until it's opened.
const AskPanel = lazy(() => import('./components/AskPanel').then((m) => ({ default: m.AskPanel })))

export function GraphPage() {
  const selected = useStore((s) => s.selected)
  const askOpen = useStore((s) => s.askOpen)
  const busy = useStore((s) => s.busy)
  const error = useStore((s) => s.error)
  const syncRunning = useStore((s) => !!s.sync?.running)
  // Graph Golf takes over the canvas: only the golf panel and the fit button stay.
  const golfing = useGolf((s) => !!s.golf || s.starting || !!s.startError)
  // A visitor who hasn't signed in (only when the server has MAL sign-in configured).
  const showWelcome = useStore((s) => !!s.me?.sign_in && !s.me.username)
  const { setAskOpen, fit, relayout, refreshUser, pollSync, loadMe } = useStore.getState()

  // Who is signed in, the list summary for the menu, and a background MAL fetch that's already running.
  useEffect(() => {
    void loadMe()
    void refreshUser()
    void pollSync()
  }, [loadMe, refreshUser, pollSync])
  useEffect(() => {
    if (!syncRunning) return
    const t = setInterval(() => void pollSync(), 2000)
    return () => clearInterval(t)
  }, [syncRunning, pollSync])

  // Click fits the graph to the view, a long press re-runs the layout.
  const hold = useRef<ReturnType<typeof setTimeout> | null>(null)
  const held = useRef(false)
  const fitDown = () => {
    held.current = false
    hold.current = setTimeout(() => {
      held.current = true
      relayout()
    }, 500)
  }
  const fitUp = () => {
    if (hold.current) clearTimeout(hold.current)
  }
  // A click covers the keyboard too. The one that ends a long press has already re-laid the graph out.
  const fitClick = () => {
    if (!held.current) fit()
    held.current = false
  }

  return (
    <div className={`shell ${askOpen ? 'ask-open' : ''} ${selected ? 'has-card' : ''} ${showWelcome ? 'welcoming' : ''} ${golfing ? 'golfing' : ''}`}>
      <GraphCanvas />

      {!golfing && (
        <div className="top-bar">
          <SearchBar />
          <AppMenu />
        </div>
      )}

      {showWelcome && <Welcome />}
      {!showWelcome && !golfing && <SyncPill />}
      {golfing && !showWelcome && <GolfPanel />}

      {/* These two stay mounted, so screen readers notice when their text changes. */}
      <div role="status">{busy && !error && !showWelcome && <div className="toast">{busy}</div>}</div>
      <div role="alert">
        {error && !showWelcome && (
          <div className="toast error">
            <span>{error}</span>
            <button className="toast-close" onClick={() => useStore.setState({ error: null })} aria-label="Dismiss">
              <CloseIcon size={14} />
            </button>
          </div>
        )}
      </div>

      {selected && !golfing && <NodeCard />}

      <div className="bottom-bar">
        {!golfing && <FiltersButton />}
        {!golfing && !showWelcome && <NodeList />}
        {!golfing && <PathBar />}
        <div className="bottom-right">
          <button className="fab" onPointerDown={fitDown} onPointerUp={fitUp} onPointerLeave={fitUp} onPointerCancel={fitUp} onClick={fitClick} aria-label="Fit graph to view" title="Fit to view (hold to re-layout)">
            <FitIcon />
          </button>
          {!golfing && (
            <button id="ask-button" className={`fab ${askOpen ? 'on' : ''}`} aria-expanded={askOpen} onClick={() => setAskOpen(!askOpen)} aria-label="Ask the graph" title="Ask the graph">
              <ChatIcon />
            </button>
          )}
        </div>
      </div>

      {askOpen && !golfing && (
        <aside className="drawer" aria-label="Ask the graph">
          <button className="icon-btn ghost drawer-close" onClick={() => {
              setAskOpen(false)
              setTimeout(() => document.getElementById('ask-button')?.focus())
            }} aria-label="Close">
            <CloseIcon />
          </button>
          <LoadBoundary>
            <Suspense fallback={<PageLoading />}>
              <AskPanel />
            </Suspense>
          </LoadBoundary>
        </aside>
      )}
    </div>
  )
}
