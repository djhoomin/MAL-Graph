import { useRef, useState } from 'react'
import { LABELS, type ListStatus } from '../api'
import { useStore } from '../store'
import { useDismiss } from './useDismiss'

const SHOWN = 50

/** The graph as a list, for anyone who can't point at the canvas. Its button only shows when the keyboard reaches it. */
export function NodeList() {
  const nodes = useStore((s) => s.nodes)
  const filters = useStore((s) => s.filters)
  const picking = useStore((s) => s.pathPicking)
  const pathFrom = useStore((s) => s.pathFrom)
  const { select, completePath } = useStore.getState()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useDismiss(ref, open, () => setOpen(false))

  // The same nodes the filters leave on the canvas.
  const onCanvas = Object.values(nodes)
    .filter((n) => filters.labels[n.label] && (n.label !== 'Anime' || filters.statuses[(n.list_status ?? 'none') as ListStatus]))
    .sort((a, b) => LABELS.indexOf(a.label) - LABELS.indexOf(b.label) || a.name.localeCompare(b.name))
  if (onCanvas.length === 0) return null
  const found = onCanvas.filter((n) => n.name.toLowerCase().includes(q.trim().toLowerCase()) && !(picking && n.id === pathFrom))

  const pick = (id: string) => {
    setOpen(false)
    setQ('')
    if (picking) void completePath(id)
    else select(id)
    // The card opens on the next render, and reading on from it is the point of picking a node.
    setTimeout(() => document.querySelector<HTMLElement>(picking ? '.path-bar' : '.node-card')?.focus())
  }

  return (
    <div className="node-list anchor" ref={ref}>
      <button id="node-list-button" className="fab" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        List what's on the graph
      </button>
      {open && (
        <div className="popover node-list-pop" role="group" aria-label="On the graph">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter the list" placeholder="Filter by name" />
          <div className="muted small-text" role="status">
            {found.length > SHOWN ? `First ${SHOWN} of ${found.length}` : found.length === 1 ? '1 result' : `${found.length} results`}
          </div>
          <ul>
            {found.slice(0, SHOWN).map((n) => (
              <li key={n.id}>
                <button onClick={() => pick(n.id)}>
                  <span>{n.name}</span> <small className="muted">{n.label}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
