import { useEffect, useRef, useState } from 'react'
import { api, errorText, mysteryApi, type GNode, type Mystery } from '../api'
import { navigate } from '../useHashRoute'
import { FieldBars, GameCard } from './GameBits'

/** Mystery character: guess today's character from clues revealed one at a time. */
export function MysteryPage() {
  const [game, setGame] = useState<Mystery | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [miss, setMiss] = useState<string | null>(null) // the name of the last wrong guess

  useEffect(() => {
    mysteryApi.daily().then(setGame, (e) => setError(errorText(e)))
  }, [])

  const move = async (action: 'clue' | 'guess' | 'give_up', guess?: GNode) => {
    setBusy(true)
    setError(null)
    setMiss(null)
    try {
      const next = await mysteryApi.move(action, guess?.mal_id ?? undefined)
      setGame(next)
      if (action === 'guess' && next.correct === false && guess) setMiss(guess.name)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <div className="kmk-page mystery">
        <h1>Mystery character</h1>
        <p className="muted">Guess today's character. Each wrong guess shows another clue, and fewer clues is better.</p>
        {!game && !error && <p className="muted">Loading today's clues…</p>}
        {game && (
          <>
            <ol className="mystery-clues">
              {game.clues.map((c, i) => (
                <li key={i} className={`${i === game.clues.length - 1 && !game.done ? 'new' : ''} ${game.done && i >= game.used ? 'unseen' : ''}`}>
                  {c}
                </li>
              ))}
            </ol>
            {!game.done && (
              <>
                <div className="muted small-text">
                  Clue {game.clues.length} of {game.total}
                </div>
                <GuessBox disabled={busy} exclude={new Set(game.guesses.map((g) => g.id))} onGuess={(n) => void move('guess', n)} />
                {miss && <p className="bad">It isn't {miss}.</p>}
                <div className="kmk-actions">
                  <button onClick={() => void move('clue')} disabled={busy || game.clues.length >= game.total}>
                    Show another clue
                  </button>
                  <button className="link" onClick={() => void move('give_up')} disabled={busy}>
                    Give up
                  </button>
                </div>
              </>
            )}
            {game.guesses.length > 0 && !game.solved && (
              <div className="mystery-guesses muted small-text">Guessed so far: {game.guesses.map((g) => g.name).join(', ')}</div>
            )}
            {game.done && game.answer && <Result game={game} />}
          </>
        )}
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  )
}

function Result({ game }: { game: Mystery }) {
  const used = game.solved ? game.used : null
  return (
    <div className="game-done mystery-done">
      <GameCard card={game.answer!} className={game.solved ? 'odd-answer' : ''} />
      <div>
        <h2>{game.solved ? `You got it with ${used} ${used === 1 ? 'clue' : 'clues'}` : `It was ${game.answer!.character.name}`}</h2>
        {game.summary && game.summary.players > 1 && (
          <>
            <p className="muted small-text">
              {game.summary.solved} of {game.summary.players} players got it today. Clues they needed:
            </p>
            <FieldBars rows={game.summary.by_clues} label={(v) => `${v} ${v === 1 ? 'clue' : 'clues'}`} mine={used} />
          </>
        )}
        <p className="muted small-text">A new character comes at midnight UTC.</p>
      </div>
    </div>
  )
}

/** Search box for characters already in the graph. Picking a suggestion makes the guess. */
function GuessBox({ onGuess, disabled, exclude }: { onGuess: (n: GNode) => void; disabled: boolean; exclude: Set<string> }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<GNode[]>([])
  const [active, setActive] = useState(0)
  const seq = useRef(0)
  const input = useRef<HTMLInputElement>(null)
  const wasDisabled = useRef(disabled)
  // A guess disables the box while it's checked. Put the cursor back afterwards, so the next guess can be typed.
  useEffect(() => {
    if (wasDisabled.current && !disabled) input.current?.focus()
    wasDisabled.current = disabled
  }, [disabled])

  useEffect(() => {
    const term = q.trim()
    if (term.length < 2) {
      setResults([])
      return
    }
    const mine = ++seq.current
    const t = setTimeout(() => {
      api.search(term, 8, ['Character']).then(
        (r) => mine === seq.current && (setResults(r.results.Character ?? []), setActive(0)),
        () => mine === seq.current && setResults([]),
      )
    }, 200)
    return () => clearTimeout(t)
  }, [q])
  const shown = results.filter((n) => !exclude.has(n.id))

  const choose = (n: GNode) => {
    setQ('')
    setResults([])
    onGuess(n)
  }

  return (
    <div className="guess-box">
      <input
        ref={input}
        type="search"
        placeholder="Name a character"
        value={q}
        disabled={disabled}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') setActive((a) => Math.min(a + 1, shown.length - 1))
          else if (e.key === 'ArrowUp') setActive((a) => Math.max(a - 1, 0))
          else if (e.key === 'Enter' && shown[active]) choose(shown[active])
          else return
          e.preventDefault()
        }}
        aria-label="Guess a character"
      />
      {shown.length > 0 && (
        <ul className="guess-results">
          {shown.map((n, i) => (
            <li key={n.id}>
              <button className={i === active ? 'on' : ''} onClick={() => choose(n)}>
                {n.image_url ? <img src={n.image_url} alt="" /> : <span className="noimg" />}
                {n.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
