import { useCallback, useEffect, useState } from 'react'
import { errorText, kmkApi, kmkDailyApi, kmkHistoryApi, type KmkDaily, type KmkHistory, type KmkTheme, type ShelfCard } from '../api'
import { navigate } from '../useHashRoute'
import { loadWho, saveWho, WhoFilter, type Who } from './Gender'
import { HowTo } from './GameBits'
import { KmkRound, type Choice, type Tally } from './KmkRound'
import { recentThemes, rememberTheme } from '../kmkRecent'

type Mode = 'today' | 'mine' | 'collection'
const MODE_KEY = 'malgraph.kmk.mode'

function loadMode(): Mode {
  try {
    const m = localStorage.getItem(MODE_KEY)
    return m === 'mine' || m === 'collection' ? m : 'today'
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
        <HowTo id="kmk">
          <p>You get three characters, and you have to kiss one, marry one and kill one. Each choice can only be used once, so every character ends up with a different fate.</p>
          <p>Today's three is the same round for everyone, and once you lock your choices in you can see how everyone else chose. From your list draws three characters from a theme in your own anime list, such as a studio or a voice actor. You can swap one character per round, spin a new theme, and choose whether to see women, men or everyone. Random draws any three, Balanced draws three about as popular as each other, and Spicy draws one famous character and two obscure ones.</p>
          <p>Every round you finish goes into your collection. The ones you married go in your harem, the ones you kissed in your hookups and the ones you killed in your graveyard. If you feel bad about a kill, you can put that character in the terrarium after the round, where they're safe as a pet instead. Only you can see your collection.</p>
          <p>When a round is done you can save it as a picture to share.</p>
        </HowTo>
        <div className="segmented game-mode" role="group" aria-label="Which round">
          <button className={mode === 'today' ? 'on' : ''} aria-pressed={mode === 'today'} onClick={() => change('today')}>
            Today's three
          </button>
          <button className={mode === 'mine' ? 'on' : ''} aria-pressed={mode === 'mine'} onClick={() => change('mine')}>
            From your list
          </button>
          <button className={mode === 'collection' ? 'on' : ''} aria-pressed={mode === 'collection'} onClick={() => change('collection')}>
            Your collection
          </button>
        </div>
        {mode === 'today' && <DailyKmk />}
        {mode === 'mine' && <ThemeKmk />}
        {mode === 'collection' && <Collection />}
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

  if (error) return <p className="error" role="alert">{error}</p>
  if (!daily) return <p className="muted" role="status">Loading today's three…</p>

  // The server keys choices by MyAnimeList id, the round by node id.
  const byNode = (ids: Record<string, Choice>) => Object.fromEntries(daily.cards.map((c) => [c.character.id, ids[String(c.character.key)]]))
  const locked = daily.choices ? byNode(daily.choices) : undefined
  const tally: Record<string, Tally> | undefined = daily.tally
    ? Object.fromEntries(daily.cards.map((c) => [c.character.id, daily.tally!.counts[String(c.character.key)]]))
    : undefined
  const lockIn = async (choices: Record<string, Choice>) => {
    const ids = Object.fromEntries(daily.cards.map((c) => [String(c.character.key), choices[c.character.id]]))
    setDaily(await kmkDailyApi.play(ids))
  }

  return (
    <>
      <p className="muted">
        The same three for everyone today. Lock in your choices to see how everyone else chose.
        {daily.tally && ` ${daily.tally.players} ${daily.tally.players === 1 ? 'player has' : 'players have'} played.`}
      </p>
      <KmkRound key={daily.date} title={daily.title} pool={daily.cards} fixed lockIn={lockIn} locked={locked} tally={tally} roundId={daily.round_id} rescued={daily.rescued} />
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
      if (current) rememberTheme(`${current.kind}:${current.key}`)
      const recent = recentThemes()
      const next = await kmkApi.theme({ ...(recent.length ? { avoid: recent.join(',') } : {}), gender: gender || null })
      rememberTheme(`${next.kind}:${next.key}`)
      setTheme(next)
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
          <p className="error" role="alert">{error}</p>
        </>
      )}
      {!theme && !error && <p className="muted">Spinning a theme…</p>}
      {theme && <KmkRound key={`${theme.kind}:${theme.key}:${who}`} title={theme.title} pool={theme.pool} onNewTheme={() => void spin(theme, who)} newThemeBusy={busy} filter={filter} />}
    </>
  )
}

const SHELVES: { key: keyof Omit<KmkHistory, 'rounds'>; title: string; empty: string }[] = [
  { key: 'harem', title: '💍 Harem', empty: 'Nobody married yet.' },
  { key: 'hookups', title: '💋 Hookups', empty: 'Nobody kissed yet.' },
  { key: 'graveyard', title: '🪦 Graveyard', empty: 'Nobody killed yet.' },
  { key: 'terrarium', title: '🪴 Terrarium', empty: 'Nobody rescued yet. After a round, put the one you killed in the terrarium instead.' },
]

/** Everyone you've married, kissed, killed or rescued, from every round you've finished. */
function Collection() {
  const [history, setHistory] = useState<KmkHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    kmkHistoryApi.history().then(setHistory, (e) => setError(errorText(e)))
  }, [])
  if (error) return <p className="error" role="alert">{error}</p>
  if (!history) return <p className="muted" role="status">Loading your collection…</p>
  return (
    <>
      <p className="muted">
        From {history.rounds} {history.rounds === 1 ? 'round' : 'rounds'}. Only you can see this.
      </p>
      {SHELVES.map((shelf) => (
        <section key={shelf.key} className="kmk-shelf">
          <h2>
            {shelf.title} <span className="muted">{history[shelf.key].length || ''}</span>
          </h2>
          {history[shelf.key].length ? (
            <div className="kmk-shelf-grid">
              {history[shelf.key].map((c) => (
                <ShelfItem key={c.character.id} card={c} />
              ))}
            </div>
          ) : (
            <p className="muted small-text">{shelf.empty}</p>
          )}
        </section>
      ))}
    </>
  )
}

function ShelfItem({ card }: { card: ShelfCard }) {
  return (
    <div className="kmk-shelf-item" title={`${card.character.name}${card.anime[0] ? ` (${card.anime[0]})` : ''}`}>
      {card.character.image_url ? <img src={card.character.image_url} alt="" loading="lazy" /> : <div className="noimg" />}
      {card.count > 1 && <span className="kmk-shelf-count">×{card.count}</span>}
      <span className="kmk-shelf-name">{card.character.name}</span>
    </div>
  )
}
