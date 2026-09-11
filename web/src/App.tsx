import { FilterBar } from './components/FilterBar'
import { GraphCanvas } from './components/GraphCanvas'
import { NodePanel } from './components/NodePanel'
import { PathFinder } from './components/PathFinder'
import { SearchBar } from './components/SearchBar'
import { StatusBar } from './components/StatusBar'
import { VaView } from './components/VaView'
import { useStore } from './store'

export default function App() {
  const view = useStore((s) => s.view)
  return (
    <div className="app">
      <aside className="sidebar left">
        <h1>MAL·Graph</h1>
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
