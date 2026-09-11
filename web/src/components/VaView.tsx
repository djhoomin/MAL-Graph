import { useEffect, useState } from 'react'
import { api, type VaResult } from '../api'
import { useStore } from '../store'

export function VaView() {
  const selected = useStore((s) => s.selected)
  const node = useStore((s) => (s.selected ? s.nodes[s.selected] : undefined))
  const filters = useStore((s) => s.filters)
  const { mergePayload, select, setView } = useStore.getState()
  const [onlyWatched, setOnlyWatched] = useState(true)
  const [data, setData] = useState<VaResult | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setData(null)
    setErr(null)
    if (!node || node.label !== 'Person' || node.mal_id == null) return
    api
      .vaRoles(node.mal_id, onlyWatched, filters.lang)
      .then(setData)
      .catch((e) => setErr((e as Error).message))
  }, [selected, node?.mal_id, node?.label, node?.fetched, onlyWatched, filters.lang])

  if (!node || node.label !== 'Person') return <div className="panel muted">Select a person to list their voice roles.</div>

  const byAnime = new Map<string, VaResult['roles']>()
  for (const r of data?.roles ?? []) {
    const list = byAnime.get(r.anime.id) ?? []
    list.push(r)
    byAnime.set(r.anime.id, list)
  }

  return (
    <div className="panel">
      <div className="row">
        <button onClick={() => setView('node')}>← details</button>
        <h2 style={{ margin: 0 }}>{node.name}</h2>
      </div>
      <label className="row">
        <input type="checkbox" checked={onlyWatched} onChange={(e) => setOnlyWatched(e.target.checked)} />
        only anime I've seen
      </label>
      {!node.fetched && (
        <div className="stub">
          Only roles already in the graph are shown. <button onClick={() => void useStore.getState().fetchFromMal(node.id)}>Fetch full filmography</button>
        </div>
      )}
      {err && <div className="error">{err}</div>}
      {data && (
        <>
          <div className="row">
            <span className="muted">
              {data.roles.length} roles in {byAnime.size} anime{filters.lang ? ` (${filters.lang})` : ''}
            </span>
            <button onClick={() => mergePayload(data)}>Add all to canvas</button>
          </div>
          {[...byAnime.entries()].map(([animeId, roles]) => (
            <div key={animeId} className="va-anime">
              <button className="link" onClick={() => { mergePayload({ nodes: [roles[0].anime], edges: [] }); select(animeId) }}>
                {roles[0].anime.watched && <em>✓ </em>}
                {roles[0].anime.name}
              </button>
              <ul>
                {roles.map((r) => (
                  <li key={r.character.id}>
                    <button
                      className="link"
                      onClick={() => {
                        mergePayload({ nodes: [r.character, r.anime, node], edges: data.edges.filter((e) => e.target === r.character.id || (e.source === r.anime.id && e.target === r.character.id)) })
                        select(r.character.id)
                      }}
                    >
                      {r.character.image_url && <img src={r.character.image_url} alt="" />}
                      {r.character.name}
                    </button>
                    <small> {r.role}</small>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </div>
  )
}
