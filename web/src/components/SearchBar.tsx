import { useEffect, useState } from 'react'
import { api, type GNode, type Label } from '../api'
import { useStore } from '../store'
import { LABEL_COLORS } from '../graph/style'

export function SearchBar() {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Partial<Record<Label, GNode[]>>>({})
  const [open, setOpen] = useState(false)
  const mergePayload = useStore((s) => s.mergePayload)
  const loadNeighbors = useStore((s) => s.loadNeighbors)

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

  const pick = (n: GNode) => {
    mergePayload({ nodes: [n], edges: [] }, { select: n.id })
    void loadNeighbors(n.id)
    setOpen(false)
    setQ('')
  }

  const groups = Object.entries(results).filter(([, v]) => v && v.length > 0) as [Label, GNode[]][]
  return (
    <div className="search">
      <input
        placeholder="Search anime, characters, people, studios…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
          if (e.key === 'Enter' && groups[0]?.[1][0]) pick(groups[0][1][0])
        }}
      />
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
