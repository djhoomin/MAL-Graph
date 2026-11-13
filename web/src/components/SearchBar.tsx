import { useEffect, useRef, useState } from 'react'
import { api, type GNode, type Label } from '../api'
import { useStore } from '../store'
import { LABEL_COLORS } from '../graph/style'
import { CloseIcon, SearchIcon } from './icons'
import { useDismiss } from './useDismiss'

export function SearchBar() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Partial<Record<Label, GNode[]>>>({})
  const [open, setOpen] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  useDismiss(wrap, open, () => setOpen(false))
  const picking = useStore((s) => s.pathPicking)
  const fromName = useStore((s) => (s.pathFrom ? s.nodes[s.pathFrom]?.name : undefined))
  const { mergePayload, loadNeighbors, completePath, clearPath } = useStore.getState()

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults({})
      return
    }
    const t = setTimeout(() => {
      api.search(q).then((r) => {
        setResults(r.results)
        setOpen(true)
      })
    }, 250)
    return () => clearTimeout(t)
  }, [q])

  // Entering path mode on a desktop puts the cursor straight into the search box.
  useEffect(() => {
    if (picking && window.matchMedia('(hover: hover)').matches) input.current?.focus()
  }, [picking])

  const pick = (n: GNode) => {
    if (picking) {
      mergePayload({ nodes: [n], edges: [] })
      void completePath(n.id)
    } else {
      mergePayload({ nodes: [n], edges: [] }, { select: n.id })
      void loadNeighbors(n.id)
    }
    setOpen(false)
    setQ('')
    input.current?.blur()
  }

  const groups = Object.entries(results).filter(([, v]) => v && v.length > 0) as [Label, GNode[]][]
  return (
    <div className={`search ${picking ? 'picking' : ''}`} ref={wrap}>
      <div className="search-box">
        {picking ? (
          <span className="path-chip">
            {fromName} to
            <button onClick={clearPath} aria-label="Cancel path">
              <CloseIcon size={12} />
            </button>
          </span>
        ) : (
          <SearchIcon />
        )}
        <input
          ref={input}
          placeholder={picking ? 'Destination…' : 'Search anime, characters, people…'}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setOpen(false)
              if (picking && !q) clearPath()
            }
            if (e.key === 'Enter' && groups[0]?.[1][0]) pick(groups[0][1][0])
          }}
        />
      </div>
      {open && groups.length > 0 && (
        <div className="search-results">
          {groups.map(([label, items]) => (
            <div key={label}>
              <div className="group-title" style={{ color: LABEL_COLORS[label] }}>
                {label}
              </div>
              {items.map((n) => (
                <button key={n.id} className="result" onClick={() => pick(n)}>
                  {n.image_url && <img src={n.image_url} alt="" />}
                  <span>
                    {n.name}
                    {n.watched && <em title={n.list_status ?? ''}> ✓</em>}
                    {n.label === 'Anime' && n.props.year != null && <small> ({String(n.props.year)})</small>}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
