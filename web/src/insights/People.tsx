import { useEffect, useMemo, useState } from 'react'
import { api, type GNode, type ListAnime, type ListStatus, type RankedPerson } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'
import type { Thread } from './Timeline'

const TABS: { key: string; label: string }[] = [
  { key: 'va', label: 'Voice actors' },
  { key: 'Director', label: 'Directors' },
  { key: 'Series Composition', label: 'Writers' },
  { key: 'Music', label: 'Composers' },
  { key: 'Character Design', label: 'Character designers' },
  { key: 'Original Creator', label: 'Original creators' },
  { key: 'Theme Song Performance', label: 'Theme song artists' },
  { key: 'studio', label: 'Studios' },
  { key: 'genre', label: 'Genres' },
]

interface Row {
  id: string
  name: string
  image_url: string | null
  anime_ids: number[]
  avg: number | null
  sub?: string
  node?: GNode
}

interface Props {
  anime: ListAnime[] // already filtered by status
  statuses: ListStatus[]
  lang: string | null
  thread: Thread | null
  onThread: (t: Thread | null) => void
}

export function People({ anime, statuses, lang, thread, onThread }: Props) {
  const [tab, setTab] = useState('va')
  const [people, setPeople] = useState<RankedPerson[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [sort, setSort] = useState<'count' | 'score'>('count')
  const mergePayload = useStore((s) => s.mergePayload)
  const select = useStore((s) => s.select)

  const isLocal = tab === 'studio' || tab === 'genre'
  useEffect(() => {
    if (isLocal) return
    setPeople(null)
    setErr(null)
    api
      .insightsPeople(tab, statuses, tab === 'va' ? lang : null)
      .then((r) => setPeople(r.people))
      .catch((e) => setErr((e as Error).message))
  }, [tab, statuses, lang, isLocal])

  const rows = useMemo<Row[]>(() => {
    const scored = (ids: number[]) => {
      const s = anime.filter((a) => ids.includes(a.mal_id) && a.my_score > 0).map((a) => a.my_score)
      return s.length ? s.reduce((x, y) => x + y, 0) / s.length : null
    }
    let out: Row[]
    if (isLocal) {
      const map = new Map<number, Row>()
      for (const a of anime) {
        for (const e of tab === 'studio' ? a.studios : a.genres.filter((g) => g.kind !== 'explicit')) {
          const r = map.get(e.mal_id) ?? { id: `${tab === 'studio' ? 'Studio' : 'Genre'}:${e.mal_id}`, name: e.name, image_url: null, anime_ids: [], avg: null }
          r.anime_ids.push(a.mal_id)
          map.set(e.mal_id, r)
        }
      }
      out = [...map.values()].filter((r) => r.anime_ids.length >= 2).map((r) => ({ ...r, avg: scored(r.anime_ids) }))
    } else {
      out = (people ?? []).map((p) => ({
        id: p.person.id,
        name: p.person.name,
        image_url: p.person.image_url,
        anime_ids: p.anime_ids,
        avg: p.avg_my_score,
        sub: tab === 'va' ? `${p.characters} characters` : undefined,
        node: p.person,
      }))
    }
    out.sort((a, b) => (sort === 'count' ? b.anime_ids.length - a.anime_ids.length : (b.avg ?? 0) - (a.avg ?? 0)) || b.anime_ids.length - a.anime_ids.length)
    return out.slice(0, 40)
  }, [anime, people, tab, isLocal, sort])

  const max = Math.max(1, ...rows.map((r) => r.anime_ids.length))
  const openInGraph = (r: Row) => {
    if (!r.node) return
    mergePayload({ nodes: [r.node], edges: [] })
    select(r.node.id)
    navigate('/')
  }

  return (
    <div>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`chip ${tab === t.key ? 'on' : 'off'}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
        <span className="spacer" />
        <label className="row">
          sort
          <select value={sort} onChange={(e) => setSort(e.target.value as 'count' | 'score')}>
            <option value="count">by anime count</option>
            <option value="score">by my avg score</option>
          </select>
        </label>
      </div>
      {err && <div className="error">{err}</div>}
      {!isLocal && !people && !err && <div className="muted">loading…</div>}
      <ol className="ranked">
        {rows.map((r) => {
          const active = thread?.label === r.name
          return (
            <li key={r.id} className={active ? 'active' : ''}>
              {r.image_url ? <img src={r.image_url} alt="" /> : <span className="noimg" />}
              <div className="ranked-body">
                <div className="ranked-name">
                  <button className="link" onClick={() => onThread(active ? null : { label: r.name, ids: new Set(r.anime_ids) })} title="Highlight on the timeline">
                    {r.name}
                  </button>
                </div>
                <div className="bar-row">
                  <div className="bar" style={{ width: `${(r.anime_ids.length / max) * 60}%` }} />
                  <span className="bar-value">
                    {r.anime_ids.length}
                    {r.avg != null && <> · avg {r.avg.toFixed(1)}</>}
                    {r.sub && <> · {r.sub}</>}
                  </span>
                </div>
              </div>
              <div className="ranked-actions">
                {tab === 'va' && r.node && <a href={`#/roster/${r.node.mal_id}`}>roster</a>}
                {r.node && (
                  <button className="link" onClick={() => openInGraph(r)}>
                    graph
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
