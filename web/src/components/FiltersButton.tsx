import { useRef, useState } from 'react'
import { LABELS, LIST_STATUSES, LIST_STATUS_LABELS, REL_TYPES } from '../api'
import { LABEL_COLORS, REL_COLORS, REL_LABELS, STATUS_COLORS } from '../graph/style'
import { chipFiltersChanged, DEFAULT_LABELS, DEFAULT_RELS, DEFAULT_STATUSES, useStore } from '../store'
import { FilterIcon } from './icons'
import { useDismiss } from './useDismiss'

const LANGS = ['Japanese', 'English', 'Korean', 'Mandarin', 'Spanish', 'French', 'German', 'Italian', 'Portuguese (BR)']

export function FiltersButton() {
  const filters = useStore((s) => s.filters)
  const { toggleLabel, toggleRel, toggleStatus, setFilter } = useStore.getState()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useDismiss(ref, open, () => setOpen(false))
  const changed = chipFiltersChanged(filters)

  return (
    <div className="anchor" ref={ref}>
      <button className={`fab ${open ? 'on' : ''}`} onClick={() => setOpen((v) => !v)} aria-label="Filters" aria-expanded={open} title="Hide kinds of nodes or connections">
        <FilterIcon />
        <span className="fab-label">Filters</span>
        {changed && <span className="badge-dot" />}
      </button>
      {open && (
        <div className="popover up filters-pop">
          <div className="pop-head">
            <h3>Node types</h3>
            {changed && (
              <button className="link" onClick={() => setFilter({ labels: DEFAULT_LABELS, rels: DEFAULT_RELS, statuses: DEFAULT_STATUSES })}>
                Reset
              </button>
            )}
          </div>
          <div className="chips">
            {LABELS.map((l) => (
              <button key={l} className={`chip ${filters.labels[l] ? '' : 'off'}`} aria-pressed={filters.labels[l]} onClick={() => toggleLabel(l)}>
                <i style={{ background: LABEL_COLORS[l] }} /> {l}
              </button>
            ))}
          </div>
          <h3>My list</h3>
          <div className="chips">
            {LIST_STATUSES.map((st) => (
              <button key={st} className={`chip ${filters.statuses[st] ? '' : 'off'}`} aria-pressed={filters.statuses[st]} onClick={() => toggleStatus(st)}>
                <i className="ring" style={{ borderColor: STATUS_COLORS[st] }} /> {LIST_STATUS_LABELS[st]}
              </button>
            ))}
          </div>
          <h3>Connections</h3>
          <div className="chips">
            {REL_TYPES.map((r) => (
              <button key={r} className={`chip ${filters.rels[r] ? '' : 'off'}`} aria-pressed={filters.rels[r]} onClick={() => toggleRel(r)}>
                <i className="line" style={{ background: REL_COLORS[r] }} /> {REL_LABELS[r]}
              </button>
            ))}
          </div>
          <label className="row">
            Voice language
            <select value={filters.lang ?? ''} onChange={(e) => setFilter({ lang: e.target.value || null })}>
              <option value="">All</option>
              {LANGS.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
        </div>
      )}
    </div>
  )
}
