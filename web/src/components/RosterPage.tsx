import { useEffect, useMemo, useState } from 'react'
import { api, type RosterEntry, type VaRole, type VaResult } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

const LANGS = ['Japanese', 'English', 'Korean', 'Mandarin', 'Spanish', 'French', 'German', 'Italian', 'Portuguese (BR)']

/** URL-addressable view: a voice actor and the characters they play, as a card grid. */
export function RosterPage({ personId }: { personId?: string }) {
  const [onlyWatched, setOnlyWatched] = useState(true)
  const [mainOnly, setMainOnly] = useState(false)
  const [lang, setLang] = useState<string | null>('Japanese')
  const opts = { onlyWatched, mainOnly, lang }
  return (
    <div className="roster">
      <header className="roster-head">
        <a href="#/" className="back">← graph</a>
        <h1>Voice actor roster</h1>
        <a href="#/insights" className="nav">Insights</a>
        <label className="row">
          <input type="checkbox" checked={onlyWatched} onChange={(e) => setOnlyWatched(e.target.checked)} /> only anime I've seen
        </label>
        <label className="row">
          <input type="checkbox" checked={mainOnly} onChange={(e) => setMainOnly(e.target.checked)} /> main roles only
        </label>
        <label className="row">
          language
          <select value={lang ?? ''} onChange={(e) => setLang(e.target.value || null)}>
            <option value="">all</option>
            {LANGS.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </label>
      </header>
      {personId ? <PersonRoster personId={Number(personId)} {...opts} /> : <RosterList {...opts} />}
    </div>
  )
}

interface Opts {
  onlyWatched: boolean
  mainOnly: boolean
  lang: string | null
}

function RosterList({ onlyWatched, mainOnly, lang }: Opts) {
  const [q, setQ] = useState('')
  const [min, setMin] = useState(3)
  const [people, setPeople] = useState<RosterEntry[] | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .roster({ only_watched: onlyWatched, main_only: mainOnly, lang, min_characters: min, q: q || undefined, limit: 300 })
        .then((r) => setPeople(r.people))
        .catch((e) => setErr((e as Error).message))
    }, 200)
    return () => clearTimeout(t)
  }, [onlyWatched, mainOnly, lang, min, q])

  return (
    <div className="roster-body">
      <div className="row">
        <input placeholder="filter by name…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="row">
          at least <input type="number" min={1} max={50} value={min} onChange={(e) => setMin(Math.max(1, +e.target.value || 1))} style={{ width: 56 }} /> characters
        </label>
        {people && <span className="muted">{people.length} voice actors</span>}
      </div>
      {err && <div className="error">{err}</div>}
      <div className="roster-grid people">
        {people?.map(({ person, characters, anime }) => (
          <button key={person.id} className="card" onClick={() => navigate(`/roster/${person.mal_id}`)}>
            {person.image_url ? <img src={person.image_url} alt="" /> : <div className="noimg" />}
            <div className="card-body">
              <strong>{person.name}</strong>
              <span className="muted">
                {characters} characters · {anime} anime
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function PersonRoster({ personId, onlyWatched, mainOnly, lang }: Opts & { personId: number }) {
  const [data, setData] = useState<VaResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const mergePayload = useStore((s) => s.mergePayload)
  const select = useStore((s) => s.select)

  useEffect(() => {
    setData(null)
    setErr(null)
    setPicked(null)
    api
      .vaRoles(personId, onlyWatched, lang)
      .then(setData)
      .catch((e) => setErr((e as Error).message))
  }, [personId, onlyWatched, lang])

  // One card per character (a character can appear in several anime); collect the anime list per character.
  const cards = useMemo(() => {
    const byChar = new Map<string, { role: VaRole; anime: VaRole['anime'][]; main: boolean }>()
    for (const r of data?.roles ?? []) {
      const entry = byChar.get(r.character.id) ?? { role: r, anime: [], main: false }
      entry.anime.push(r.anime)
      entry.main ||= r.role === 'Main'
      byChar.set(r.character.id, entry)
    }
    return [...byChar.values()].filter((c) => !mainOnly || c.main)
  }, [data, mainOnly])

  const person = data?.nodes.find((n) => n.id === `Person:${personId}`)
  const shuffle = () => {
    const pool = [...cards]
    const chosen = new Set<string>()
    while (chosen.size < Math.min(3, pool.length)) {
      const i = Math.floor(Math.random() * pool.length)
      chosen.add(pool.splice(i, 1)[0].role.character.id)
    }
    setPicked(chosen)
  }
  const openInGraph = () => {
    if (!data) return
    mergePayload(data)
    select(`Person:${personId}`)
    navigate('/')
  }

  return (
    <div className="roster-body">
      <div className="row">
        <a href="#/roster" className="back">← all voice actors</a>
        {person?.image_url && <img className="avatar" src={person.image_url} alt="" />}
        <h2>{person?.name ?? `Person ${personId}`}</h2>
        {person?.props.url != null && (
          <a href={String(person.props.url)} target="_blank" rel="noreferrer">
            MAL ↗
          </a>
        )}
        <span className="muted">{cards.length} characters</span>
        <button disabled={cards.length < 2} onClick={shuffle}>Pick 3 at random</button>
        {picked && <button onClick={() => setPicked(null)}>Show all</button>}
        <button disabled={!data} onClick={openInGraph}>Open in graph</button>
      </div>
      {err && <div className="error">{err}</div>}
      {data && cards.length === 0 && <div className="muted">No characters match these filters.</div>}
      <div className="roster-grid">
        {cards
          .filter((c) => !picked || picked.has(c.role.character.id))
          .map(({ role, anime, main }) => (
            <div key={role.character.id} className={`card ${picked ? 'picked' : ''}`}>
              {role.character.image_url ? <img src={role.character.image_url} alt="" /> : <div className="noimg" />}
              <div className="card-body">
                <strong>{role.character.name}</strong>
                <span className="muted">{main ? 'Main' : 'Supporting'}</span>
                {anime.slice(0, 3).map((a) => (
                  <span key={a.id} className="anime-line" title={a.list_status ?? ''}>
                    {a.watched ? '✓ ' : ''}
                    {a.name}
                  </span>
                ))}
                {anime.length > 3 && <span className="muted">+{anime.length - 3} more</span>}
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}
