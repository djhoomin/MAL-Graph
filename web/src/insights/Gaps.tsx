import { useEffect, useMemo, useState } from 'react'
import { api, type Gap, type ListStatus } from '../api'
import { useStore } from '../store'

const RELATIONS = ['Sequel', 'Prequel', 'Side Story', 'Spin-Off', 'Alternative Version', 'Parent Story', 'Alternative Setting']

export function Gaps({ statuses }: { statuses: ListStatus[] }) {
  const [gaps, setGaps] = useState<Gap[] | null>(null)
  const [rels, setRels] = useState<Set<string>>(new Set(['Sequel', 'Prequel']))
  const [err, setErr] = useState<string | null>(null)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  const run = useStore((s) => s.run)

  const load = () =>
    api
      .insightsGaps(statuses)
      .then((r) => setGaps(r.gaps))
      .catch((e) => setErr((e as Error).message))
  useEffect(() => {
    setGaps(null)
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statuses])

  const rows = useMemo(() => {
    return (gaps ?? [])
      .map((g) => ({ ...g, via: g.via.filter((v) => rels.has(v.relation)) }))
      .filter((g) => g.via.length > 0)
      .sort((a, b) => Math.max(...b.via.map((v) => v.my_score)) - Math.max(...a.via.map((v) => v.my_score)) || (b.score ?? 0) - (a.score ?? 0))
  }, [gaps, rels])

  const fetchOne = async (g: Gap) => {
    await run(`Fetching ${g.title}…`, () => api.expand(`Anime:${g.mal_id}`))
    await load()
  }
  // Sequentially fetch every unfetched gap in the current view (the API rate-limits Jikan calls).
  const fetchAll = async () => {
    const todo = rows.filter((g) => !g.fetched)
    setProgress({ done: 0, total: todo.length })
    for (const [i, g] of todo.entries()) {
      try {
        await api.expand(`Anime:${g.mal_id}`)
      } catch {
        /* keep going; the item stays a stub */
      }
      setProgress({ done: i + 1, total: todo.length })
      if ((i + 1) % 10 === 0) await load()
    }
    setProgress(null)
    await load()
  }
  const unfetched = rows.filter((g) => !g.fetched).length

  return (
    <div>
      <div className="tabs">
        {RELATIONS.map((r) => (
          <button
            key={r}
            className={`chip ${rels.has(r) ? 'on' : 'off'}`}
            onClick={() =>
              setRels((s) => {
                const n = new Set(s)
                if (n.has(r)) n.delete(r)
                else n.add(r)
                return n
              })
            }
          >
            {r}
          </button>
        ))}
        <span className="spacer" />
        <span className="muted">{rows.length} unseen</span>
        {unfetched > 0 && (
          <button className="small" disabled={!!progress} onClick={() => void fetchAll()}>
            {progress ? `fetching ${progress.done}/${progress.total}…` : `fetch details for all (${unfetched})`}
          </button>
        )}
      </div>
      {err && <div className="error">{err}</div>}
      {gaps && rows.length === 0 && <div className="muted">Nothing — you're caught up on these.</div>}
      <div className="gap-grid">
        {rows.slice(0, 60).map((g) => (
          <div key={g.mal_id} className="gap">
            {g.image_url ? <img src={g.image_url} alt="" /> : <span className="noimg" />}
            <div className="gap-body">
              <a href={`https://myanimelist.net/anime/${g.mal_id}`} target="_blank" rel="noreferrer" className="gap-title">
                {g.title}
              </a>
              <div className="muted">
                {g.type ?? ''} {g.year ?? ''} {g.score ? `· MAL ${g.score}` : ''}
                {!g.fetched && (
                  <button className="link" onClick={() => void fetchOne(g)}>
                    {' '}
                    fetch details
                  </button>
                )}
              </div>
              {g.via.slice(0, 2).map((v) => (
                <div key={v.mal_id + v.relation} className="via">
                  {v.relation.toLowerCase()} of <em>{v.title}</em>
                  {v.my_score > 0 && <span className="muted"> · you gave it {v.my_score}</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
