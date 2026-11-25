import { useCallback, useEffect, useRef, useState } from 'react'
import { errorText, yayApi, type KmkCard, type YayDaily, type YayPattern, type YayPatterns } from '../api'
import { navigate } from '../useHashRoute'
import { GameCard, HowTo } from './GameBits'
import { lessMotion } from '../motion'

type Mode = 'today' | 'mine'
const MODE_KEY = 'malgraph.yay.mode'
const SWIPE = 90 // pixels a card has to travel to count as a vote
const OUT_MS = 180

function loadMode(): Mode {
  try {
    return localStorage.getItem(MODE_KEY) === 'mine' ? 'mine' : 'today'
  } catch {
    return 'today'
  }
}

const idOf = (card: KmkCard) => card.character.key ?? 0

/** Yay or Nay: swipe right or left on characters. Today's stack is the same for everyone, and From your list is
 *  endless. Your votes from both build up a picture of what you say yay to. */
export function YayPage() {
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
      <div className="kmk-page yay">
        <h1>Yay or Nay</h1>
        <p className="muted">Swipe right for yay and left for nay.</p>
        <HowTo id="yay">
          <p>Swipe a card right for yay or left for nay. You can also use the buttons, or the arrow keys on a keyboard.</p>
          <p>Today's stack has 20 characters and is the same for everyone. Once you're through it, you can see what share of players said yay to each one. A new stack comes at midnight UTC.</p>
          <p>From your list deals characters from anime you've watched, as many as you like, and never one you've already voted on.</p>
          <p>After 10 votes, Your patterns shows what the characters you said yay or nay to have in common, such as a voice actor, a studio, a genre or a series.</p>
        </HowTo>
        <div className="segmented game-mode" role="group" aria-label="Which stack">
          <button className={mode === 'today' ? 'on' : ''} aria-pressed={mode === 'today'} onClick={() => change('today')}>
            Today's stack
          </button>
          <button className={mode === 'mine' ? 'on' : ''} aria-pressed={mode === 'mine'} onClick={() => change('mine')}>
            From your list
          </button>
        </div>
        {mode === 'today' ? <Daily key="today" /> : <Mine key="mine" />}
      </div>
    </div>
  )
}

function Daily() {
  const [game, setGame] = useState<YayDaily | null>(null)
  const [error, setError] = useState<string | null>(null)
  const votes = useRef<Record<string, number>>({}) // every vote either side has, since replies can arrive out of order
  const show = (g: YayDaily) => {
    votes.current = { ...g.votes, ...votes.current }
    setGame({ ...g, votes: votes.current })
  }
  useEffect(() => {
    yayApi.daily().then(show, (e) => setError(errorText(e)))
  }, [])

  const vote = async (card: KmkCard, yes: boolean) => {
    const id = idOf(card)
    votes.current = { ...votes.current, [id]: yes ? 1 : 0 }
    setGame((g) => g && { ...g, votes: votes.current }) // show the next card straight away
    try {
      const reply = await yayApi.voteDaily(id, yes)
      show(reply)
      // The last reply to arrive may predate the last vote. Fetch the finished game once every vote is in.
      if (!reply.done && reply.cards.every((c) => String(idOf(c)) in votes.current)) show(await yayApi.daily())
    } catch (e) {
      setError(errorText(e))
    }
  }

  if (error) return <p className="error" role="alert">{error}</p>
  if (!game) return <p className="muted" role="status">Loading today's stack…</p>
  const left = game.cards.filter((c) => !(String(idOf(c)) in game.votes))
  if (left.length || !game.done) {
    return left.length ? (
      <>
        <Swiper key={idOf(left[0])} card={left[0]} next={left[1]} onVote={(yes) => void vote(left[0], yes)} />
        <div className="muted small-text yay-count">
          {game.cards.length - left.length + 1} of {game.cards.length}
        </div>
      </>
    ) : (
      <p className="muted">Counting the votes…</p>
    )
  }
  return <DailyResults game={game} />
}

function DailyResults({ game }: { game: YayDaily }) {
  const rows = game.cards.map((card) => {
    const id = String(idOf(card))
    const r = game.results?.[id] ?? { players: 0, yay: 0 }
    const share = r.players ? Math.round((100 * r.yay) / r.players) : 0
    return { card, mine: game.votes[id] === 1, players: r.players, share }
  })
  const yays = rows.filter((r) => r.mine).length
  const players = Math.max(...rows.map((r) => r.players))
  // The majority on a card, with you counted in it. A tie counts as agreeing.
  const agreed = rows.filter((r) => (r.mine ? r.share >= 50 : r.share <= 50)).length
  return (
    <div className="game-done">
      <h2>
        You said yay to {yays} of {rows.length}
      </h2>
      {players > 1 ? (
        <p className="muted small-text">
          {players} players so far. You went with the majority on {agreed} of {rows.length}.
        </p>
      ) : (
        <p className="muted small-text">You're the first today. Check back later to see how everyone else voted.</p>
      )}
      <div className="yay-results">
        {rows.map((r) => (
          <GameCard key={idOf(r.card)} card={r.card} className={r.mine ? 'yay-mine' : 'nay-mine'}>
            <span className={`yay-badge ${r.mine ? 'yay' : 'nay'}`}>{r.mine ? 'Yay' : 'Nay'}</span>
            {players > 1 && (
              <span className="yay-share" title={`${r.share}% of ${r.players} players said yay`}>
                <i style={{ width: `${r.share}%` }} />
                <b>{r.share}% yay</b>
              </span>
            )}
          </GameCard>
        ))}
      </div>
      {game.patterns && <Patterns patterns={game.patterns} />}
      <p className="muted small-text">A new stack comes at midnight UTC.</p>
    </div>
  )
}

function Mine() {
  const [queue, setQueue] = useState<KmkCard[]>([])
  const [patterns, setPatterns] = useState<YayPatterns | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [empty, setEmpty] = useState(false)
  const loading = useRef(false)

  const more = useCallback(async () => {
    if (loading.current) return
    loading.current = true
    try {
      const batch = await yayApi.mine()
      setPatterns(batch.patterns)
      setQueue((q) => {
        const have = new Set(q.map(idOf))
        return [...q, ...batch.cards.filter((c) => !have.has(idOf(c)))]
      })
    } catch (e) {
      const text = errorText(e)
      if (/no characters left/i.test(text)) setEmpty(true)
      else setError(text)
    } finally {
      loading.current = false
    }
  }, [])
  useEffect(() => void more(), [more])
  // Keep a few cards ahead, so a quick swiper never waits.
  useEffect(() => {
    if (queue.length < 3 && !empty && !error) void more()
  }, [queue.length, empty, error, more])

  const vote = async (card: KmkCard, yes: boolean) => {
    setQueue((q) => q.slice(1))
    try {
      const next = (await yayApi.voteMine(idOf(card), yes)).patterns
      setPatterns((p) => (p && p.votes > next.votes ? p : next)) // an older reply can arrive last
    } catch (e) {
      setError(errorText(e))
    }
  }

  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {queue.length ? (
        <Swiper key={idOf(queue[0])} card={queue[0]} next={queue[1]} onVote={(yes) => void vote(queue[0], yes)} />
      ) : empty ? (
        <p className="muted">You've voted on every character from your list. Sync your list for more, or play today's stack.</p>
      ) : (
        !error && <p className="muted">Dealing characters from your list…</p>
      )}
      {patterns && <Patterns patterns={patterns} />}
    </>
  )
}

/** The top card, which follows a finger or the mouse and flies off when let go far enough to one side. */
function Swiper({ card, next, onVote }: { card: KmkCard; next?: KmkCard; onVote: (yes: boolean) => void }) {
  const [dx, setDx] = useState(0)
  const [out, setOut] = useState<0 | 1 | -1>(0)
  const start = useRef<number | null>(null)
  const pointer = useRef<number | null>(null) // the finger doing the swipe, so a second one can't take it over

  const decide = useCallback(
    (yes: boolean) => {
      if (out) return
      setOut(yes ? 1 : -1)
      setTimeout(() => onVote(yes), OUT_MS)
    },
    [out, onVote],
  )
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowRight') decide(true)
      else if (e.key === 'ArrowLeft') decide(false)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [decide])

  const fade = out !== 0 && lessMotion() // the card fades where it is instead of flying off
  const x = out && !fade ? out * 600 : dx
  const lean = Math.max(-1, Math.min(1, x / SWIPE))
  return (
    <div className="yay-stage">
      <div className="yay-stack">
        {next && <GameCard card={next} className="yay-next" />}
        <div
          className={`yay-top ${start.current === null ? 'settle' : ''}`}
          style={{ transform: `translateX(${x}px) rotate(${x / 18}deg)`, opacity: fade ? 0 : undefined }}
          onPointerDown={(e) => {
            if (out || start.current !== null) return
            pointer.current = e.pointerId
            start.current = e.clientX
            e.currentTarget.setPointerCapture(e.pointerId)
          }}
          onPointerMove={(e) => start.current !== null && e.pointerId === pointer.current && setDx(e.clientX - start.current)}
          onPointerUp={(e) => {
            if (start.current === null || e.pointerId !== pointer.current) return
            start.current = null
            if (Math.abs(dx) >= SWIPE) decide(dx > 0)
            else setDx(0)
          }}
          onPointerCancel={(e) => {
            if (e.pointerId !== pointer.current) return
            start.current = null
            setDx(0)
          }}
          onLostPointerCapture={() => {
            if (start.current === null) return // an ordinary release, already handled
            start.current = null
            setDx(0)
          }}
        >
          <GameCard card={card}>
            <span className="yay-stamp yay" style={{ opacity: Math.max(0, lean) }}>
              Yay
            </span>
            <span className="yay-stamp nay" style={{ opacity: Math.max(0, -lean) }}>
              Nay
            </span>
          </GameCard>
        </div>
      </div>
      <div className="yay-buttons">
        <button className="nay" onClick={() => decide(false)} disabled={!!out} aria-label={`Nay to ${card.character.name}`}>
          ← Nay
        </button>
        <button className="yay" onClick={() => decide(true)} disabled={!!out} aria-label={`Yay to ${card.character.name}`}>
          Yay →
        </button>
      </div>
    </div>
  )
}

const KIND: Record<YayPattern['kind'], (label: string) => string> = {
  voice: (l) => `Voiced by ${l}`,
  studio: (l) => `Animated by ${l}`,
  genre: (l) => `${l} anime`,
  series: (l) => l,
}

function Patterns({ patterns }: { patterns: YayPatterns }) {
  const rate = patterns.votes ? Math.round((100 * patterns.yay) / patterns.votes) : 0
  return (
    <section className="yay-patterns">
      <h2>Your patterns</h2>
      {patterns.need > 0 ? (
        <p className="muted small-text">
          {patterns.need} more {patterns.need === 1 ? 'vote' : 'votes'} until your patterns show.
        </p>
      ) : (
        <>
          <p className="muted small-text">
            You've said yay to {rate}% of {patterns.votes} characters, across both stacks.
          </p>
          {!patterns.likes.length && !patterns.dislikes.length && <p className="muted small-text">Nothing stands out yet. Keep swiping.</p>}
          <PatternList title="More yays" rows={patterns.likes} />
          <PatternList title="More nays" rows={patterns.dislikes} />
        </>
      )}
    </section>
  )
}

function PatternList({ title, rows }: { title: string; rows: YayPattern[] }) {
  if (!rows.length) return null
  return (
    <div className="yay-pattern-list">
      <h3>{title}</h3>
      <ul>
        {rows.map((p) => (
          <li key={`${p.kind}:${p.label}`}>
            <span>{KIND[p.kind](p.label)}</span>
            <b>
              {p.yay} of {p.total} yay
            </b>
          </li>
        ))}
      </ul>
    </div>
  )
}
