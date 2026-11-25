import { useMemo, useState } from 'react'
import type { ListAnime } from '../api'
import { fmt } from './data'
import { AnimeCard } from './AnimeCard'
import { useSource } from '../store'

const SHOW = 8
const GEM_SCORE = 8 // your score for a hidden gem, at least
const GEM_MEMBERS = 100_000 // members (people with it on their list) for a hidden gem, at most
const MIN_GENRE = 3 // scored anime a genre needs before its average means anything

const members = (n: number) => (n >= 1000 ? `${fmt(Math.round(n / 1000))}k` : fmt(n))
const signed = (n: number) => `${n > 0 ? '+' : ''}${n.toFixed(1)}`

/** The anime where your score is furthest from the site's average, both ways. */
export function HotTakes({ anime }: { anime: ListAnime[] }) {
  const src = useSource()
  const [side, setSide] = useState<'above' | 'below'>('above')
  const takes = useMemo(() => {
    const scored = anime.filter((a) => a.my_score > 0 && a.score != null).map((a) => ({ a, d: a.my_score - a.score! }))
    return {
      above: scored.filter((x) => x.d > 0).sort((x, y) => y.d - x.d).slice(0, SHOW),
      below: scored.filter((x) => x.d < 0).sort((x, y) => x.d - y.d).slice(0, SHOW),
    }
  }, [anime])
  if (!takes.above.length && !takes.below.length) return null
  const shown = takes[side]
  return (
    <section>
      <div className="section-head">
        <h2>Hot takes</h2>
        <span className="muted">where your score is furthest from {src.name}'s average</span>
        <div className="row">
          <button className={`chip ${side === 'above' ? 'on' : 'off'}`} aria-pressed={side === 'above'} onClick={() => setSide('above')}>
            you rate higher
          </button>
          <button className={`chip ${side === 'below' ? 'on' : 'off'}`} aria-pressed={side === 'below'} onClick={() => setSide('below')}>
            you rate lower
          </button>
        </div>
      </div>
      {shown.length ? (
        <div className="roster-grid people">
          {shown.map(({ a, d }) => (
            <AnimeCard key={a.id} a={a} note={`${src.short} ${a.score!.toFixed(2)} · ${signed(d)}`} />
          ))}
        </div>
      ) : (
        <p className="muted small-text">{side === 'above' ? 'You never score above the average.' : 'You never score below the average.'}</p>
      )}
    </section>
  )
}

interface GenreRow {
  name: string
  count: number
  scored: number
  mean: number | null
}

/** How much of your list each genre and theme is, and whether you score it above or below your own average. */
export function GenreTaste({ anime }: { anime: ListAnime[] }) {
  const [sort, setSort] = useState<'count' | 'score'>('count')
  const [all, setAll] = useState(false)
  const { rows, mean } = useMemo(() => {
    const scored = anime.filter((a) => a.my_score > 0)
    const mean = scored.length ? scored.reduce((n, a) => n + a.my_score, 0) / scored.length : null
    const by = new Map<string, { count: number; total: number; scored: number }>()
    for (const a of anime) {
      for (const g of a.genres) {
        if (g.kind !== 'genre' && g.kind !== 'theme') continue
        const r = by.get(g.name) ?? { count: 0, total: 0, scored: 0 }
        r.count++
        if (a.my_score > 0) {
          r.total += a.my_score
          r.scored++
        }
        by.set(g.name, r)
      }
    }
    const rows: GenreRow[] = [...by.entries()].map(([name, r]) => ({ name, count: r.count, scored: r.scored, mean: r.scored >= MIN_GENRE ? r.total / r.scored : null }))
    return { rows, mean }
  }, [anime])
  if (!rows.length) return null

  const sorted = [...rows].sort((x, y) => (sort === 'count' ? y.count - x.count : (y.mean ?? -1) - (x.mean ?? -1) || y.count - x.count))
  const shown = all ? sorted : sorted.slice(0, 12)
  const most = Math.max(...rows.map((r) => r.count))
  return (
    <section>
      <div className="section-head">
        <h2>Your genres</h2>
        <span className="muted">{mean != null ? `compared with your mean score of ${mean.toFixed(2)}` : 'score some anime to compare genres'}</span>
        <div className="row">
          <button className={`chip ${sort === 'count' ? 'on' : 'off'}`} aria-pressed={sort === 'count'} onClick={() => setSort('count')}>
            most watched
          </button>
          <button className={`chip ${sort === 'score' ? 'on' : 'off'}`} aria-pressed={sort === 'score'} onClick={() => setSort('score')}>
            best scored
          </button>
        </div>
      </div>
      <div className="genre-rows">
        {shown.map((r) => {
          const d = r.mean != null && mean != null ? r.mean - mean : null
          return (
            <div key={r.name} className="genre-row">
              <span className="genre-name">{r.name}</span>
              <span className="genre-bar">
                <i style={{ width: `${(100 * r.count) / most}%` }} />
              </span>
              <span className="genre-count muted">{r.count}</span>
              <span className={`genre-delta ${d == null ? 'muted' : d >= 0.15 ? 'good' : d <= -0.15 ? 'bad' : 'muted'}`} title={r.mean != null ? `Your mean score for ${r.name} is ${r.mean.toFixed(2)}` : `Fewer than ${MIN_GENRE} scored`}>
                {d == null ? '–' : signed(d)}
              </span>
            </div>
          )
        })}
      </div>
      {rows.length > 12 && (
        <button className="small" onClick={() => setAll((v) => !v)}>
          {all ? 'show fewer' : `show all ${rows.length}`}
        </button>
      )}
    </section>
  )
}

/** Anime you scored highly that few people on the site have watched. */
export function Gems({ anime }: { anime: ListAnime[] }) {
  const src = useSource()
  const gems = useMemo(
    () =>
      anime
        .filter((a) => a.my_score >= GEM_SCORE && !a.follow_up && a.members != null && a.members < GEM_MEMBERS)
        .sort((x, y) => y.my_score - x.my_score || x.members! - y.members!)
        .slice(0, SHOW * 2),
    [anime],
  )
  if (!gems.length) return null
  return (
    <section>
      <div className="section-head">
        <h2>Hidden gems</h2>
        <span className="muted">
          scored {GEM_SCORE} or more by you, with fewer than {members(GEM_MEMBERS)} members on {src.name}, leaving out sequels
        </span>
      </div>
      <div className="roster-grid people">
        {gems.map((a) => (
          <AnimeCard key={a.id} a={a} note={`${members(a.members!)} members`} />
        ))}
      </div>
    </section>
  )
}

/** Shows you've stopped or paused near the end. Watching is left out, since that's mostly shows still airing. */
export function AlmostDone({ anime }: { anime: ListAnime[] }) {
  const close = useMemo(
    () =>
      anime
        .filter((a) => (a.status === 'on_hold' || a.status === 'dropped') && a.episodes && a.episodes_watched > 0)
        .map((a) => ({ a, left: a.episodes! - a.episodes_watched }))
        .filter(({ a, left }) => left > 0 && (left <= 3 || left <= a.episodes! / 4))
        .sort((x, y) => x.left - y.left || y.a.episodes_watched - x.a.episodes_watched)
        .slice(0, SHOW * 2),
    [anime],
  )
  if (!close.length) return null
  return (
    <section>
      <div className="section-head">
        <h2>Almost finished</h2>
        <span className="muted">shows you stopped or paused near the end</span>
      </div>
      <div className="roster-grid people">
        {close.map(({ a, left }) => (
          <AnimeCard key={a.id} a={a} note={`${left} of ${a.episodes} ${a.episodes === 1 ? 'episode' : 'episodes'} left`} />
        ))}
      </div>
    </section>
  )
}
