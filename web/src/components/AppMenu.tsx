import { useRef, useState } from 'react'
import { useStore } from '../store'
import { MenuIcon } from './icons'
import { useDismiss } from './useDismiss'

export function AppMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const close = () => setOpen(false)
  useDismiss(ref, open, close)
  const sync = useStore((s) => s.sync)

  return (
    <div className="anchor" ref={ref}>
      <button className={`fab ${open ? 'on' : ''}`} onClick={() => setOpen((v) => !v)} aria-label="Menu">
        <MenuIcon />
        {sync?.running && <span className="badge-dot busy" />}
      </button>
      {open && <MenuBody close={close} />}
    </div>
  )
}

function MenuBody({ close }: { close: () => void }) {
  const user = useStore((s) => s.user)
  const busy = useStore((s) => s.busy)
  const sync = useStore((s) => s.sync)
  const syncMsg = useStore((s) => s.syncMsg)
  const filters = useStore((s) => s.filters)
  const nodeCount = useStore((s) => Object.keys(s.nodes).length)
  const edgeCount = useStore((s) => Object.keys(s.edges).length)
  const { startSync, setFilter, loadNeighbors, relayout, clear } = useStore.getState()
  const act = (fn: () => void) => () => {
    fn()
    close()
  }

  return (
    <div className="popover down menu-pop">
      <section>
        {user?.username ? (
          <>
            <div className="menu-user">
              <strong>{user.username}</strong>
              <span className="muted">{user.total} on list</span>
            </div>
            {user.unfetched > 0 && <div className="muted small-text">{user.unfetched} not fetched from MAL yet</div>}
          </>
        ) : (
          <div className="muted">No MAL list synced yet</div>
        )}
        <button className="wide" disabled={!!busy || !!sync?.running} onClick={() => void startSync()} title="Re-fetch your MAL list, then fetch any new anime from MAL">
          {sync?.running ? `Fetching ${sync.done} of ${sync.total}…` : 'Sync list'}
        </button>
        {syncMsg && <div className="muted small-text">{syncMsg}</div>}
      </section>

      <section className="menu-list">
        <a href="#/insights" onClick={close}>Insights</a>
        <a href="#/roster" onClick={close}>VA roster</a>
      </section>

      <section className="menu-list">
        {user?.username && <button onClick={act(() => void loadNeighbors(`User:${user.username}`))}>Add my list to the graph</button>}
        <button onClick={act(relayout)}>Re-layout</button>
        <button onClick={act(clear)} disabled={nodeCount === 0}>
          Clear graph
        </button>
        <div className="muted small-text menu-meta">
          {nodeCount} nodes · {edgeCount} edges
        </div>
      </section>

      <section>
        <label className="toggle">
          <input type="checkbox" checked={filters.expandOnClick} onChange={(e) => setFilter({ expandOnClick: e.target.checked })} />
          Expand nodes on click
        </label>
        <label className="toggle">
          <input type="checkbox" checked={filters.highlightNeighbors} onChange={(e) => setFilter({ highlightNeighbors: e.target.checked })} />
          Highlight neighbours of selection
        </label>
        <label className="toggle">
          <input type="checkbox" checked={filters.onlyWatched} onChange={(e) => setFilter({ onlyWatched: e.target.checked })} />
          Only load anime I've seen
        </label>
      </section>
    </div>
  )
}
