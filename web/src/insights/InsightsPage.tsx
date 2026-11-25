import { useEffect, useMemo, useState } from 'react'
import { api, LIST_STATUS_LABELS, type ListAnime, type ListStatus } from '../api'
import { STATUS_COLORS } from '../graph/style'
import { useStore } from '../store'
import { fmt, SEEN, type Bucket } from './data'
import { Gaps } from './Gaps'
import { People } from './People'
import { AnimeCard } from './AnimeCard'
import { Recommendations } from './Recommendations'
import { AlmostDone, Gems, GenreTaste, HotTakes } from './Taste'
import { Timeline, type Thread } from './Timeline'

const LANGS = ['Japanese', 'English', 'Korean', 'Mandarin', 'Spanish', 'French', 'German', 'Italian', 'Portuguese (BR)']
const STATUS_ORDER: ListStatus[] = ['completed', 'watching', 'on_hold', 'dropped', 'plan_to_watch']

export function InsightsPage() {
  const [all, setAll] = useState<ListAnime[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [statuses, setStatuses] = useState<Set<ListStatus>>(new Set(SEEN))
  const [lang, setLang] = useState<string | null>('Japanese')
  const [granularity, setGranularity] = useState<'season' | 'year'>('season')
  const [thread, setThread] = useState<Thread | null>(null)
  const [picked, setPicked] = useState<Bucket | null>(null)
  const user = useStore((s) => s.user)
  const refreshUser = useStore((s) => s.refreshUser)

  useEffect(() => {
    void refreshUser()
    api
      .insightsList()
      .then((r) => setAll(r.anime))
      .catch((e) => setErr((e as Error).message))
  }, [refreshUser])

  const statusList = useMemo(() => STATUS_ORDER.filter((s) => statuses.has(s)), [statuses])
  // Gaps only follow on from anime you're still with, not ones you dropped or put on hold.
  const gapStatuses = useMemo(() => statusList.filter((s) => s === 'completed' || s === 'watching'), [statusList])
  const anime = useMemo(() => (all ?? []).filter((a) => statuses.has(a.status)), [all, statuses])

  const kpi = useMemo(() => {
    const scored = anime.filter((a) => a.my_score > 0)
    const eps = anime.reduce((n, a) => n + (a.episodes_watched ?? 0), 0)
    const byYear = new Map<number, number>()
    for (const a of anime) if (a.year) byYear.set(a.year, (byYear.get(a.year) ?? 0) + 1)
    const topYear = [...byYear.entries()].sort((x, y) => y[1] - x[1])[0]
    const tens = scored.filter((a) => a.my_score === 10).length
    return {
      count: anime.length,
      eps,
      mean: scored.length ? scored.reduce((n, a) => n + a.my_score, 0) / scored.length : null,
      scored: scored.length,
      topYear,
      tens,
      hours: Math.round((eps * 23) / 60),
    }
  }, [anime])

  const toggleStatus = (s: ListStatus) =>
    setStatuses((cur) => {
      const n = new Set(cur)
      if (n.has(s)) n.delete(s)
      else n.add(s)
      return n
    })

  return (
    <div className="insights">
      <header className="roster-head">
        <a href="#/" className="back">← graph</a>
        <h1>Insights{user?.username ? ` · ${user.username}` : ''}</h1>
        <a href="#/roster" className="nav">VA roster</a>
      </header>

      <div className="filter-row">
        <span className="muted">include</span>
        {STATUS_ORDER.map((s) => (
          <button key={s} className={`chip ${statuses.has(s) ? '' : 'off'}`} aria-pressed={statuses.has(s)} style={{ borderColor: STATUS_COLORS[s] }} onClick={() => toggleStatus(s)}>
            <i style={{ background: STATUS_COLORS[s] }} /> {LIST_STATUS_LABELS[s]}
          </button>
        ))}
        <label className="row">
          VA language
          <select value={lang ?? ''} onChange={(e) => setLang(e.target.value || null)}>
            <option value="">all</option>
            {LANGS.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </label>
      </div>

      {err && <div className="error" role="alert">{err}</div>}
      {!all && !err && <div className="muted" style={{ padding: 20 }} role="status">loading…</div>}

      {all && (
        <div className="insights-body">
          <section className="kpis">
            <Stat label="anime" value={fmt(kpi.count)} sub={`${kpi.scored} scored`} />
            <Stat label="episodes watched" value={fmt(kpi.eps)} sub={`≈ ${fmt(kpi.hours)} hours`} />
            <Stat label="my mean score" value={kpi.mean != null ? kpi.mean.toFixed(2) : '–'} sub={`${kpi.tens} × 10/10`} />
            <Stat label="peak year (by air date)" value={kpi.topYear ? String(kpi.topYear[0]) : '–'} sub={kpi.topYear ? `${kpi.topYear[1]} anime` : ''} />
          </section>

          <section>
            <div className="section-head">
              <h2>Timeline</h2>
              <div className="row">
                <button className={`chip ${granularity === 'season' ? 'on' : 'off'}`} aria-pressed={granularity === 'season'} onClick={() => setGranularity('season')}>
                  by season
                </button>
                <button className={`chip ${granularity === 'year' ? 'on' : 'off'}`} aria-pressed={granularity === 'year'} onClick={() => setGranularity('year')}>
                  by year
                </button>
                {thread && (
                  <button className="small" onClick={() => setThread(null)}>
                    clear highlight: {thread.label}
                  </button>
                )}
              </div>
            </div>
            <Timeline anime={anime} granularity={granularity} thread={thread} picked={picked?.key ?? null} onPick={(b) => setPicked((p) => (p?.key === b.key ? null : b))} />
            {picked && (
              <div className="season-detail">
                <div className="section-head">
                  <h3>
                    {picked.label} · {picked.anime.length} anime
                  </h3>
                  <button className="small" onClick={() => setPicked(null)}>
                    close
                  </button>
                </div>
                <div className="roster-grid people">
                  {picked.anime
                    .slice()
                    .sort((a, b) => b.my_score - a.my_score)
                    .map((a) => (
                      <AnimeCard key={a.id} a={a} dim={!!thread && !thread.ids.has(a.id)} />
                    ))}
                </div>
              </div>
            )}
          </section>

          <section>
            <div className="section-head">
              <h2>Your people</h2>
              <span className="muted">click a name to highlight their anime on the timeline</span>
            </div>
            <People anime={anime} statuses={statusList} lang={lang} thread={thread} onThread={setThread} />
          </section>

          <HotTakes anime={anime} />
          <GenreTaste anime={anime} />
          <Gems anime={anime} />
          <AlmostDone anime={anime} />

          <section>
            <div className="section-head">
              <h2>Recommendations</h2>
              <span className="muted">unseen anime connected to your people</span>
            </div>
            <Recommendations />
          </section>

          <section>
            <div className="section-head">
              <h2>Gaps</h2>
              <span className="muted">related anime you haven't seen</span>
            </div>
            <Gaps statuses={gapStatuses} />
          </section>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub muted">{sub}</div>}
    </div>
  )
}
