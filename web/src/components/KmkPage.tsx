import { useCallback, useEffect, useState } from 'react'
import { errorText, kmkApi, kmkDailyApi, type KmkDaily, type KmkTheme } from '../api'
import { navigate } from '../useHashRoute'
import { loadWho, saveWho, WhoFilter, type Who } from './Gender'
import { KmkRound, type Choice, type Tally } from './KmkRound'

type Mode = 'today' | 'mine'
const MODE_KEY = 'malgraph.kmk.mode'

function loadMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'mine' ? 'mine' : 'today'
  } catch {
    return 'today'
  }
}

/** Kiss Marry Kill: today's three for everyone, or a theme drawn at random from your own graph. */
export function KmkPage() {
  const [mode, setMode] = useState<Mode>(loadMode)
  const change = (m: Mode) => {
    setMode(m)
    try {
      localStorage.setItem(MODE_KEY, m)
    } catch {
      /* storage blocked: the choice lasts until reload */
    }
  }

  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <div className="kmk-page">
        <h1>Kiss Marry Kill</h1>
        <div className="segmented game-mode" role="group" aria-label="Which round">
          <button className={mode === 'today' ? 'on' : ''} onClick={() => change('today')}>
            Today's three
          </button>
          <button className={mode === 'mine' ? 'on' : ''} onClick={() => change('mine')}>
            From your list
          </button>
        </div>
        {mode === 'today' ? <DailyKmk /> : <ThemeKmk />}
      </div>
    </div>
  )
}

/** The same three characters for everyone today, with how everyone chose once you've locked in. */
function DailyKmk() {
  const [daily, setDaily] = useState<KmkDaily | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    kmkDailyApi.get().then(setDaily, (e) => setError(errorText(e)))
  }, [])

  if (error) return <p className="error">{error}</p>
  if (!daily) return <p className="muted">Loading today's three…</p>

  // The server keys choices by MyAnimeList id, the round by node id.
  const byNode = (ids: Record<string, Choice>) => Object.fromEntries(daily.cards.map((c) => [c.character.id, ids[String(c.character.mal_id)]]))
  const locked = daily.choices ? byNode(daily.choices) : undefined
  const tally: Record<string, Tally> | undefined = daily.tally
    ? Object.fromEntries(daily.cards.map((c) => [c.character.id, daily.tally!.counts[String(c.character.mal_id)]]))
    : undefined
  const lockIn = async (choices: Record<string, Choice>) => {
    const ids = Object.fromEntries(daily.cards.map((c) => [String(c.character.mal_id), choices[c.character.id]]))
    setDaily(await kmkDailyApi.play(ids))
  }

  return (
    <>
      <p className="muted">
        The same three for everyone today. Lock in your choices to see how everyone else chose.
        {daily.tally && ` ${daily.tally.players} ${daily.tally.players === 1 ? 'player has' : 'players have'} played.`}
      </p>
      <KmkRound key={daily.date} title={daily.title} pool={daily.cards} fixed lockIn={lockIn} locked={locked} tally={tally} />
    </>
  )
}

/** Three characters from a theme in your list. */
function ThemeKmk() {
  const [theme, setTheme] = useState<KmkTheme | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [who, setWho] = useState<Who>(loadWho)

  const spin = useCallback(async (current: KmkTheme | null, gender: Who) => {
    setBusy(true)
    setError(null)
    try {
      setTheme(await kmkApi.theme({ ...(current ? { avoid: `${current.kind}:${current.key}` } : {}), gender: gender || null }))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void spin(null, loadWho())
  }, [spin])
  const changeWho = (w: Who) => {
    setWho(w)
    saveWho(w)
    void spin(null, w)
  }
  const filter = <WhoFilter value={who} onChange={changeWho} disabled={busy} />

  return (
    <>
      <p className="muted">Three characters from a theme in your list. Give each one a different choice.</p>
      {error && (
        <>
          {!theme && filter}
          <p className="error">{error}</p>
        </>
      )}
      {!theme && !error && <p className="muted">Spinning a theme…</p>}
      {theme && <KmkRound key={`${theme.kind}:${theme.key}:${who}`} title={theme.title} pool={theme.pool} onNewTheme={() => void spin(theme, who)} newThemeBusy={busy} filter={filter} />}
    </>
  )
}
