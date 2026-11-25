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
  const [searched, setSearched] = useState<string | null>(null) // the text the results are for
  const [failed, setFailed] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  useDismiss(wrap, open, () => setOpen(false))
  const picking = useStore((s) => s.pathPicking)
  const fromName = useStore((s) => (s.pathFrom ? s.nodes[s.pathFrom]?.name : undefined))
  const { mergePayload, loadNeighbors, completePath, clearPath } = useStore.getState()

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults({})
      setSearched(null)
      setFailed(false)
      return
    }
    let live = true // a slow answer to earlier text must not replace a later one
    const t = setTimeout(() => {
      api
        .search(q)
        .then((r) => {
          if (!live) return
          setResults(r.results)
          setSearched(q)
          setFailed(false)
          setOpen(true)
        })
        .catch(() => {
          if (!live) return
          setResults({})
          setSearched(null)
          setFailed(true)
          setOpen(true)
        })
    }, 250)
    return () => {
      live = false
      clearTimeout(t)
    }
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
  const count = groups.reduce((n, [, items]) => n + items.length, 0)
  const note = !open ? '' : failed ? 'The search failed. Check your connection and try again.' : searched !== null && count === 0 ? 'Nothing found.' : ''
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
      <div className="sr-only" role="status">
        {note || (open && count > 0 ? (count === 1 ? '1 result' : `${count} results`) : '')}
      </div>
      {note && (
        <div className="search-results search-note muted" aria-hidden="true">
          {note}
        </div>
      )}
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
