import { useEffect, useState } from 'react'
import { api, type Recommendation } from '../api'
import { useSource, useStore } from '../store'
import { navigate } from '../useHashRoute'

const VIA: { key: 'va' | 'staff' | 'studio'; label: string; hint: string }[] = [
  { key: 'va', label: 'Voice actors', hint: 'unseen anime whose main cast is your favourite VAs' },
  { key: 'staff', label: 'Directors & staff', hint: 'directed, written, scored or designed by people behind anime you rated well' },
  { key: 'studio', label: 'Studios', hint: 'from studios you keep coming back to' },
]

export function Recommendations() {
  const src = useSource()
  const [via, setVia] = useState<'va' | 'staff' | 'studio'>('va')
  const [minScore, setMinScore] = useState(7)
  const [movies, setMovies] = useState(true)
  const [recs, setRecs] = useState<Recommendation[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const mergePayload = useStore((s) => s.mergePayload)
  const select = useStore((s) => s.select)

  useEffect(() => {
    setRecs(null)
    setErr(null)
    api
      .insightsRecommendations(via, minScore, movies ? 'TV,Movie,ONA' : 'TV,ONA')
      .then((r) => setRecs(r.recommendations))
      .catch((e) => setErr((e as Error).message))
  }, [via, minScore, movies])

  const open = (r: Recommendation) => {
    mergePayload({ nodes: [r.anime], edges: [] })
    select(r.anime.id)
    navigate('/')
  }

  return (
    <div>
      <div className="tabs">
        {VIA.map((v) => (
          <button key={v.key} className={`chip ${via === v.key ? 'on' : 'off'}`} aria-pressed={via === v.key} onClick={() => setVia(v.key)} title={v.hint}>
            {v.label}
          </button>
        ))}
        <span className="spacer" />
        <label className="row">
          {src.short} score ≥
          <input type="number" min={0} max={10} step={0.5} value={minScore} onChange={(e) => setMinScore(+e.target.value)} style={{ width: 60 }} />
        </label>
        <label className="row">
          <input type="checkbox" checked={movies} onChange={(e) => setMovies(e.target.checked)} /> include movies
        </label>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        {VIA.find((v) => v.key === via)?.hint}. Sequels and prequels of anime you have seen are under Gaps instead.
      </div>
      {err && <div className="error" role="alert">{err}</div>}
      {recs && recs.length === 0 && (
        <div className="muted">
          Nothing matches these settings yet. Try a lower score or another way of finding shows.
        </div>
      )}
      <div className="gap-grid">
        {recs?.map((r) => (
          <div key={r.anime.id} className="gap">
            {r.anime.image_url ? <img src={r.anime.image_url} alt="" loading="lazy" decoding="async" /> : <span className="noimg" />}
            <div className="gap-body">
              <button className="link gap-title" onClick={() => open(r)} title="Open in graph">
                {r.anime.name}
              </button>
              <div className="muted">
                {String(r.anime.props.type ?? '')} {String(r.anime.props.year ?? '')}
                {r.anime.props.score ? ` · ${src.short} ${String(r.anime.props.score)}` : ''}
                {r.anime.props.episodes ? ` · ${String(r.anime.props.episodes)} ep` : ''}
              </div>
              <div className="via">
                {via === 'studio' ? 'by' : 'with'} <em>{r.via.slice(0, 4).join(', ')}</em>
                {r.n_people > 4 && <span className="muted"> +{r.n_people - 4} more</span>}
              </div>
              <a className="muted" href={String(r.anime.props.url ?? '')} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>
                {src.short} ↗
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
