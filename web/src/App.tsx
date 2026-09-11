import { FilterBar } from './components/FilterBar'
import { GraphCanvas } from './components/GraphCanvas'
import { NodePanel } from './components/NodePanel'
import { PathFinder } from './components/PathFinder'
import { SearchBar } from './components/SearchBar'
import { StatusBar } from './components/StatusBar'
import { VaView } from './components/VaView'
import { RosterPage } from './components/RosterPage'
import { useStore } from './store'
import { useHashRoute } from './useHashRoute'

export default function App() {
  const view = useStore((s) => s.view)
  const route = useHashRoute()
  if (route[0] === 'roster') return <RosterPage personId={route[1]} />
  return (
    <div className="app">
      <aside className="sidebar left">
        <h1>
          MAL·Graph <a href="#/roster" className="nav">VA roster</a>
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
