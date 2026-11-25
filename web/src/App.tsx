import { useEffect, useRef } from 'react'
import { AppMenu } from './components/AppMenu'
import { AskPanel } from './components/AskPanel'
import { FiltersButton } from './components/FiltersButton'
import { GolfPanel } from './components/GolfPanel'
import { GraphCanvas } from './components/GraphCanvas'
import { ChatIcon, CloseIcon, FitIcon } from './components/icons'
import { NodeCard } from './components/NodeCard'
import { NodeList } from './components/NodeList'
import { PathBar } from './components/PathBar'
import { PrivacyPage } from './components/PrivacyPage'
import { HelpPage } from './components/HelpPage'
import { KmkPage } from './components/KmkPage'
import { MatchPage, PENDING_INVITE_KEY } from './components/MatchPage'
import { MysteryPage } from './components/MysteryPage'
import { OddPage } from './components/OddPage'
import { RosterPage } from './components/RosterPage'
import { SearchBar } from './components/SearchBar'
import { TourPage } from './components/TourPage'
import { YayPage } from './components/YayPage'
import { SyncPill, Welcome } from './components/Welcome'
import { useGolf } from './golf'
import { InsightsPage } from './insights/InsightsPage'
import { useStore } from './store'
import { navigate, useHashRoute } from './useHashRoute'

const TITLES: Record<string, string> = {
  roster: 'Voice actor roster',
  insights: 'Insights',
  privacy: 'Privacy',
  help: 'Help',
  tour: 'Graph tour',
  kmk: 'Kiss Marry Kill',
  odd: 'Odd one out',
  mystery: 'Mystery character',
  yay: 'Yay or Nay',
  match: 'Taste match',
}

export default function App() {
  const route = useHashRoute()
  const main = useRef<HTMLElement>(null)
  const page = route[0] in TITLES ? route[0] : ''
  const shown = useRef(page)
  useEffect(() => {
    document.title = page ? `${TITLES[page]} · Aniweb` : 'Aniweb'
    if (shown.current === page) return
    shown.current = page
    main.current?.focus({ preventScroll: true }) // the link that led here is gone, so start from the new page
  }, [page])
  // Someone opened an invite before signing in, and signing in brought them back to the start page.
  useEffect(() => {
    try {
      const token = localStorage.getItem(PENDING_INVITE_KEY)
      if (!token) return
      localStorage.removeItem(PENDING_INVITE_KEY)
      if (!window.location.hash.replace(/^#\/?/, '')) navigate(`match/join/${token}`)
    } catch {
      /* storage blocked */
    }
  }, [])
  return (
    <main ref={main} tabIndex={-1}>
      <Page route={route} />
    </main>
  )
}

function Page({ route }: { route: string[] }) {
  if (route[0] === 'roster') return <RosterPage personId={route[1]} />
  if (route[0] === 'insights') return <InsightsPage />
  if (route[0] === 'privacy') return <PrivacyPage />
  if (route[0] === 'help') return <HelpPage />
  if (route[0] === 'tour') return <TourPage />
  if (route[0] === 'kmk') return <KmkPage />
  if (route[0] === 'odd') return <OddPage />
  if (route[0] === 'mystery') return <MysteryPage />
  if (route[0] === 'yay') return <YayPage />
  if (route[0] === 'match') return <MatchPage route={route} />
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
          <AskPanel />
        </aside>
      )}
    </div>
  )
}
