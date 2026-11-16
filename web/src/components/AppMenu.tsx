import { useRef, useState } from 'react'
import { useGolf } from '../golf'
import { useSource, useStore } from '../store'
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
  const src = useSource()
  const user = useStore((s) => s.user)
  const busy = useStore((s) => s.busy)
  const sync = useStore((s) => s.sync)
  const syncMsg = useStore((s) => s.syncMsg)
  const filters = useStore((s) => s.filters)
  const nodeCount = useStore((s) => Object.keys(s.nodes).length)
  const edgeCount = useStore((s) => Object.keys(s.edges).length)
  const me = useStore((s) => s.me)
  const { startSync, uploadList, setFilter, loadNeighbors, relayout, clear, signOut } = useStore.getState()
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
            {user.unfetched > 0 && <div className="muted small-text">{user.unfetched} not fetched yet</div>}
          </>
        ) : (
          <div className="muted">{me?.sign_in ? 'Not signed in' : 'No list synced yet'}</div>
        )}
        <button className="wide" hidden={!user?.username} disabled={!!busy || !!sync?.running} onClick={() => void startSync()} title="Re-read your list, then fetch any new anime">
          {sync?.running ? `Fetching ${sync.done} of ${sync.total}…` : 'Sync list'}
        </button>
        {user?.username && (
          <label className={`button wide menu-upload ${busy || sync?.running ? 'disabled' : ''}`} title="Replace your list with the file from Export lists on MyAnimeList (.xml or .xml.gz)">
            Upload MyAnimeList export
            <input
              type="file"
              accept=".xml,.gz,application/xml,text/xml,application/gzip"
              disabled={!!busy || !!sync?.running}
              onChange={(e) => {
                const file = e.currentTarget.files?.[0]
                e.currentTarget.value = '' // the same file can be picked again
                if (file) void uploadList(file)
              }}
            />
          </label>
        )}
        {syncMsg && <div className="muted small-text">{syncMsg}</div>}
      </section>

      {me?.sign_in && me.username && (
        <section className="menu-list">
          <button onClick={act(() => void signOut())}>Sign out</button>
        </section>
      )}

      <section className="menu-list">
        <button onClick={act(() => void useGolf.getState().start('daily'))} title="Get from one thing to another along the graph in as few moves as you can">Graph Golf</button>
        <a href="#/kmk" onClick={close} title="Kiss one, marry one, kill one">Kiss Marry Kill</a>
        <a href="#/yay" onClick={close} title="Swipe right or left on characters">Yay or Nay</a>
        <a href="#/odd" onClick={close} title="Find the character who doesn't share the others' link">Odd one out</a>
        <a href="#/mystery" onClick={close} title="Guess today's character from clues">Mystery character</a>
        <a href="#/match" onClick={close} title="Compare your list with a friend's">Taste match</a>
        <a href="#/tour" onClick={close} title="What the shape of your graph says about your taste">Graph tour</a>
        <a href="#/insights" onClick={close} title="A summary of your list">Insights</a>
        <a href="#/roster" onClick={close} title="The voice actors in your anime">VA roster</a>
        <a href="#/help" onClick={close}>Help</a>
        <a href="#/privacy" onClick={close}>Privacy and your data</a>
      </section>

      <section className="menu-list">
        {user?.username && <button onClick={act(() => void loadNeighbors(`User:${user.username}`))} title="Put every anime on your list on the graph">Add my list to the graph</button>}
        <button onClick={act(relayout)} title="Rearrange the graph">Re-layout</button>
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

      <div className="muted small-text menu-credit">
        {src.anilist
          ? 'Data from AniList via the AniList API. Not affiliated with AniList.'
          : 'Data from MyAnimeList via the MyAnimeList API and Jikan, and character genders from AniList. Not affiliated with MyAnimeList or AniList.'}
      </div>
    </div>
  )
}
