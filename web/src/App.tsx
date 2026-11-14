import { useEffect, useRef } from 'react'
import { AppMenu } from './components/AppMenu'
import { AskPanel } from './components/AskPanel'
import { FiltersButton } from './components/FiltersButton'
import { GolfPanel } from './components/GolfPanel'
import { GraphCanvas } from './components/GraphCanvas'
import { ChatIcon, CloseIcon, FitIcon } from './components/icons'
import { NodeCard } from './components/NodeCard'
import { PathBar } from './components/PathBar'
import { PrivacyPage } from './components/PrivacyPage'
import { HelpPage } from './components/HelpPage'
import { KmkPage } from './components/KmkPage'
import { MysteryPage } from './components/MysteryPage'
import { OddPage } from './components/OddPage'
import { RosterPage } from './components/RosterPage'
import { SearchBar } from './components/SearchBar'
import { SyncPill, Welcome } from './components/Welcome'
import { useGolf } from './golf'
import { InsightsPage } from './insights/InsightsPage'
import { useStore } from './store'
import { useHashRoute } from './useHashRoute'

export default function App() {
  const route = useHashRoute()
  if (route[0] === 'roster') return <RosterPage personId={route[1]} />
  if (route[0] === 'insights') return <InsightsPage />
  if (route[0] === 'privacy') return <PrivacyPage />
  if (route[0] === 'help') return <HelpPage />
  if (route[0] === 'kmk') return <KmkPage />
  if (route[0] === 'odd') return <OddPage />
  if (route[0] === 'mystery') return <MysteryPage />
  return <GraphPage />
}

function GraphPage() {
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
    if (!held.current) fit()
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

      {(busy || error) && !showWelcome && (
        <div className={`toast ${error ? 'error' : ''}`} onClick={() => error && useStore.setState({ error: null })} title={error ? 'Dismiss' : undefined}>
          {error ?? busy}
        </div>
      )}

      {selected && !golfing && <NodeCard />}

      <div className="bottom-bar">
        {!golfing && <FiltersButton />}
        {!golfing && <PathBar />}
        <div className="bottom-right">
          <button className="fab" onPointerDown={fitDown} onPointerUp={fitUp} onPointerLeave={() => hold.current && clearTimeout(hold.current)} aria-label="Fit graph to view" title="Fit to view (hold to re-layout)">
            <FitIcon />
          </button>
          {!golfing && (
            <button className={`fab ${askOpen ? 'on' : ''}`} onClick={() => setAskOpen(!askOpen)} aria-label="Ask the graph" title="Ask the graph">
              <ChatIcon />
            </button>
          )}
        </div>
      </div>

      {askOpen && !golfing && (
        <aside className="drawer">
          <button className="icon-btn ghost drawer-close" onClick={() => setAskOpen(false)} aria-label="Close">
            <CloseIcon />
          </button>
          <AskPanel />
        </aside>
      )}
    </div>
  )
}
