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
    statuses.length === 0
      ? Promise.resolve(setGaps([]))
      : api
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
  const out = rows.filter((g) => g.airing !== 'Not yet aired')
  const coming = rows
    .filter((g) => g.airing === 'Not yet aired')
    .sort((a, b) => (a.aired_from ?? '9999').localeCompare(b.aired_from ?? '9999') || a.title.localeCompare(b.title))

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
        <span className="muted">
          {out.length} to watch{coming.length > 0 && `, ${coming.length} not aired yet`}
        </span>
        {unfetched > 0 && (
          <button className="small" disabled={!!progress} onClick={() => void fetchAll()}>
            {progress ? `fetching ${progress.done}/${progress.total}…` : `fetch details for all (${unfetched})`}
          </button>
        )}
      </div>
      {err && <div className="error">{err}</div>}
      <p className="muted small-text">These follow on from anime you've completed or are watching, not ones you dropped or put on hold. Anything already on your list is left out, Plan to Watch included.</p>
      {gaps && rows.length === 0 && <div className="muted">You're caught up on these.</div>}
      <GapGrid rows={out.slice(0, 60)} fetchOne={fetchOne} />
      {coming.length > 0 && (
        <>
          <h3 className="gap-head">Not aired yet</h3>
          <GapGrid rows={coming.slice(0, 60)} fetchOne={fetchOne} />
        </>
      )}
    </div>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** When an anime that hasn't aired is due, as precisely as MyAnimeList knows it. */
function due(g: Gap): string {
  if (g.season && g.year) return `${g.season[0].toUpperCase()}${g.season.slice(1)} ${g.year}`
  const m = g.aired_from?.match(/^(\d{4})-(\d{2})/)
  if (m) return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`
  return g.year ? String(g.year) : 'No date yet'
}

function GapGrid({ rows, fetchOne }: { rows: Gap[]; fetchOne: (g: Gap) => Promise<void> }) {
  return (
    <div className="gap-grid">
      {rows.map((g) => (
        <div key={g.mal_id} className="gap">
          {g.image_url ? <img src={g.image_url} alt="" /> : <span className="noimg" />}
          <div className="gap-body">
            <a href={`https://myanimelist.net/anime/${g.mal_id}`} target="_blank" rel="noreferrer" className="gap-title">
              {g.title}
            </a>
            <div className="muted">
              {g.airing === 'Not yet aired' ? `${g.type ?? ''} ${due(g)}` : `${g.type ?? ''} ${g.year ?? ''} ${g.score ? `· MAL ${g.score}` : ''}`}
              {g.airing === 'Currently Airing' && ' · airing'}
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
  )
}
