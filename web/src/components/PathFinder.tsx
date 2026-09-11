import { useState } from 'react'
import { api, type PathResult } from '../api'
import { useStore } from '../store'

export function PathFinder() {
  const pathFrom = useStore((s) => s.pathFrom)
  const pathTo = useStore((s) => s.pathTo)
  const nodes = useStore((s) => s.nodes)
  const filters = useStore((s) => s.filters)
  const { setPathEnd, mergePayload, setHighlight, run } = useStore.getState()
  const [maxHops, setMaxHops] = useState(8)
  const [onlyWatched, setOnlyWatched] = useState(false)
  const [via, setVia] = useState({ va: true, staff: true, related: true, studio: true, genre: false })
  const toggleVia = (k: keyof typeof via) => setVia((v) => ({ ...v, [k]: !v[k] }))
  const [allPaths, setAllPaths] = useState(false)
  const [result, setResult] = useState<PathResult | null>(null)

  const find = async () => {
    if (!pathFrom || !pathTo) return
    const exclude = ['User', ...(via.genre ? [] : ['Genre']), ...(via.studio ? [] : ['Studio'])].join(',')
    const rels = [
      ...(via.va ? ['VOICES', 'HAS_CHARACTER'] : []),
      ...(via.staff ? ['WORKED_ON'] : []),
      ...(via.related ? ['RELATED_TO'] : []),
      ...(via.studio ? ['PRODUCED_BY'] : []),
      ...(via.genre ? ['HAS_GENRE'] : []),
    ].join(',')
    const r = await run('Finding path…', () =>
      api.path(pathFrom, pathTo, { max_hops: maxHops, only_watched: onlyWatched, exclude, rels, lang: filters.lang, all_paths: allPaths, limit: 10 }),
    )
    if (!r) return
    setResult(r)
    if (r.found) {
      mergePayload(r)
      setHighlight([...r.nodes.map((n) => n.id), ...r.edges.map((e) => e.id)])
    } else {
      setHighlight([])
    }
  }

  const chip = (end: 'from' | 'to', id: string | null) => (
    <span className={`endpoint ${end}`}>
      {id ? nodes[id]?.name ?? id : <i>right-click / long-press a node → "path {end === 'from' ? 'start' : 'end'}"</i>}
      {id && <button onClick={() => setPathEnd(end, null)}>×</button>}
    </span>
  )

  return (
    <div className="section">
      <h3>Shortest path</h3>
      <div className="row">from {chip('from', pathFrom)}</div>
      <div className="row">to {chip('to', pathTo)}</div>
      <label className="row">
        max hops <input type="range" min={1} max={15} value={maxHops} onChange={(e) => setMaxHops(+e.target.value)} /> {maxHops}
      </label>
      <label className="row">
        <input type="checkbox" checked={onlyWatched} onChange={(e) => setOnlyWatched(e.target.checked)} /> only via anime I've seen
      </label>
      <div className="row muted" style={{ marginBottom: 0 }}>hop via</div>
      <div className="chips">
        {(
          [
            ['va', 'voice actors'],
            ['staff', 'staff'],
            ['related', 'related anime'],
            ['studio', 'studios'],
            ['genre', 'genres'],
          ] as const
        ).map(([k, label]) => (
          <button key={k} className={`chip ${via[k] ? '' : 'off'}`} onClick={() => toggleVia(k)}>
            {label}
          </button>
        ))}
      </div>
      <label className="row">
        <input type="checkbox" checked={allPaths} onChange={(e) => setAllPaths(e.target.checked)} /> all shortest paths (max 10)
      </label>
      <div className="row">
        <button disabled={!pathFrom || !pathTo || !Object.values(via).some(Boolean)} onClick={() => void find()}>
          Find
        </button>
        {result && (
          <button
            onClick={() => {
              setHighlight([])
              setResult(null)
            }}
          >
            Clear highlight
          </button>
        )}
      </div>
      {result && !result.found && <div className="error">No path within {maxHops} hops (in the data fetched so far).</div>}
      {result?.found && (
        <div className="path-list">
          <div className="muted">{result.hops} hops · {result.paths.length} path{result.paths.length > 1 ? 's' : ''}</div>
          {result.paths.slice(0, 5).map((p, i) => (
            <div key={i} className="path">
              {p.map((id, j) => (
                <span key={id}>
                  {j > 0 && ' → '}
                  <button className="link" onClick={() => useStore.getState().select(id)}>
                    {nodes[id]?.name ?? id}
                  </button>
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
