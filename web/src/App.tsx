import { useEffect, useState } from 'react'
import { FilterBar } from './components/FilterBar'
import { GraphCanvas } from './components/GraphCanvas'
import { NodePanel } from './components/NodePanel'
import { PathFinder } from './components/PathFinder'
import { SearchBar } from './components/SearchBar'
import { StatusBar } from './components/StatusBar'
import { VaView } from './components/VaView'
import { RosterPage } from './components/RosterPage'
import { InsightsPage } from './insights/InsightsPage'
import { useStore } from './store'
import { useHashRoute } from './useHashRoute'
import { useIsMobile } from './useMediaQuery'

type Sheet = 'none' | 'tools' | 'node'

export default function App() {
  const view = useStore((s) => s.view)
  const route = useHashRoute()
  const isMobile = useIsMobile()
  if (route[0] === 'roster') return <RosterPage personId={route[1]} />
  if (route[0] === 'insights') return <InsightsPage />
  return isMobile ? <MobileLayout view={view} /> : <DesktopLayout view={view} />
}

function DesktopLayout({ view }: { view: 'node' | 'va' }) {
  return (
    <div className="app">
      <aside className="sidebar left">
        <h1>
          MAL·Graph <a href="#/roster" className="nav">VA roster</a>
          <a href="#/insights" className="nav">Insights</a>
        </h1>
        <SearchBar />
        <PathFinder />
        <FilterBar />
      </aside>
      <main>
        <GraphCanvas />
        <StatusBar />
      </main>
      <aside className="sidebar right">{view === 'va' ? <VaView /> : <NodePanel />}</aside>
    </div>
  )
}

function MobileLayout({ view }: { view: 'node' | 'va' }) {
  const [sheet, setSheet] = useState<Sheet>('none')
  const selected = useStore((s) => s.selected)
  const selectedName = useStore((s) => (s.selected ? s.nodes[s.selected]?.name : undefined))
  const busy = useStore((s) => s.busy)
  const error = useStore((s) => s.error)

  // "Voice roles" / roster links switch the view; make sure the node sheet is showing it.
  useEffect(() => {
    if (view === 'va') setSheet('node')
  }, [view])

  const toggle = (s: Sheet) => setSheet((cur) => (cur === s ? 'none' : s))
  return (
    <div className={`app mobile ${sheet !== 'none' ? 'sheet-open' : ''}`}>
      <main>
        <GraphCanvas />
      </main>
      <div className="topbar">
        <SearchBar />
      </div>
      {(busy || error) && <div className={`toast ${error ? 'error' : ''}`}>{error ?? `⏳ ${busy}`}</div>}
      {sheet !== 'none' && (
        <div className="sheet">
          <div className="sheet-handle" onClick={() => setSheet('none')}>
            <span />
          </div>
          <div className="sheet-body">
            {sheet === 'tools' && (
              <>
                <PathFinder />
                <FilterBar />
                <StatusBar />
              </>
            )}
            {sheet === 'node' && (view === 'va' ? <VaView /> : <NodePanel />)}
          </div>
        </div>
      )}
      <nav className="tabbar">
        <button className={sheet === 'none' ? 'active' : ''} onClick={() => setSheet('none')}>
          Graph
        </button>
        <button className={sheet === 'tools' ? 'active' : ''} onClick={() => toggle('tools')}>
          Tools
        </button>
        <button className={sheet === 'node' ? 'active' : ''} disabled={!selected} onClick={() => toggle('node')}>
          {selectedName ? <span className="ellipsis">{selectedName}</span> : 'Node'}
        </button>
        <a href="#/roster">Roster</a>
        <a href="#/insights">Insights</a>
      </nav>
    </div>
  )
}
