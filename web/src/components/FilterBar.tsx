import { LABELS, REL_TYPES } from '../api'
import { LABEL_COLORS, REL_COLORS, REL_LABELS } from '../graph/style'
import { useStore } from '../store'

const LANGS = ['Japanese', 'English', 'Korean', 'Mandarin', 'Spanish', 'French', 'German', 'Italian', 'Portuguese (BR)']

export function FilterBar() {
  const filters = useStore((s) => s.filters)
  const user = useStore((s) => s.user)
  const { toggleLabel, toggleRel, setFilter, relayout, clear, loadNeighbors } = useStore.getState()
  return (
    <div className="section">
      <h3>Show</h3>
      <div className="chips">
        {LABELS.map((l) => (
          <button key={l} className={`chip ${filters.labels[l] ? '' : 'off'}`} style={{ borderColor: LABEL_COLORS[l] }} onClick={() => toggleLabel(l)}>
            <i style={{ background: LABEL_COLORS[l] }} /> {l}
          </button>
        ))}
      </div>
      <div className="chips">
        {REL_TYPES.map((r) => (
          <button key={r} className={`chip ${filters.rels[r] ? '' : 'off'}`} style={{ borderColor: REL_COLORS[r] }} onClick={() => toggleRel(r)}>
            <i style={{ background: REL_COLORS[r] }} /> {REL_LABELS[r]}
          </button>
        ))}
      </div>
      <label className="row">
        VA language
        <select value={filters.lang ?? ''} onChange={(e) => setFilter({ lang: e.target.value || null })}>
          <option value="">all</option>
          {LANGS.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
      </label>
      <label className="row">
        <input type="checkbox" checked={filters.onlyWatched} onChange={(e) => setFilter({ onlyWatched: e.target.checked })} />
        only load anime I've seen
      </label>
      <label className="row">
        <input type="checkbox" checked={filters.highlightNeighbors} onChange={(e) => setFilter({ highlightNeighbors: e.target.checked })} />
        highlight neighbours of selection
      </label>
      <div className="row">
        <button onClick={relayout}>Re-layout</button>
        <button onClick={clear}>Clear canvas</button>
        {user?.username && (
          <button title="Adds every anime on your list (watched only if the toggle above is on)" onClick={() => void loadNeighbors(`User:${user.username}`)}>
            Add my list
          </button>
        )}
      </div>
    </div>
  )
}
