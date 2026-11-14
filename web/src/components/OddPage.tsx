import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { errorText, oddApi, type KmkCard, type OddDaily, type OddLink, type OddResult } from '../api'
import { navigate } from '../useHashRoute'
import { FieldBars, GameCard, HowTo } from './GameBits'

/** On a phone the reveal sits below the cards, so a new round starts back at the top of the page. */
const toTop = () => document.querySelector('.doc-page')?.scrollTo({ top: 0, behavior: 'smooth' })

/** Odd one out: four characters, three share a hidden link. Five daily rounds, then endless practice. */
export function OddPage() {
  const [practice, setPractice] = useState(false)
  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <div className="kmk-page">
        <h1>Odd one out</h1>
        <p className="muted">Three of these characters share a voice actor, a studio, a creator or an anime season. Pick the one that doesn't belong.</p>
        <HowTo id="odd">
          <p>Each round shows four characters. Three of them have something in common, and the fourth doesn't. Tap the one you think is the odd one out.</p>
          <p>The link can be one of four things. The three can share a Japanese voice actor, they can be main characters in anime by the same studio, they can come from the same original creator, or they can be main characters in anime from the same season. The three never come from the same anime or its sequels, so the link takes a bit more thought than that.</p>
          <p>Under each name is the character's best-known anime, which is a good hint. After you answer, the link is shown, and you can tap the name in it to look it up.</p>
          <p>There are five rounds a day, and they're the same for everyone. Only your first pick in each round counts. Once you've played them, you can see how everyone else did and keep going with practice rounds, which are endless and don't count.</p>
        </HowTo>
        {practice ? <Practice onDaily={() => setPractice(false)} /> : <Daily onPractice={() => setPractice(true)} />}
      </div>
    </div>
  )
}

function Daily({ onPractice }: { onPractice: () => void }) {
  const [daily, setDaily] = useState<OddDaily | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [viewing, setViewing] = useState<number | null>(null) // a round whose answer is showing

  useEffect(() => {
    oddApi.daily().then(setDaily, (e) => setError(errorText(e)))
  }, [])

  if (error && !daily) return <p className="error">{error}</p>
  if (!daily) return <p className="muted">Loading today's rounds…</p>

  const total = daily.rounds.length
  const next = daily.rounds.findIndex((r) => !r.result)
  const index = viewing ?? next
  const score = daily.rounds.filter((r) => r.result?.correct).length

  const pick = async (i: number, malId: number) => {
    setBusy(true)
    setError(null)
    try {
      const { result, summary } = await oddApi.answer(i, malId)
      setDaily((d) => d && { ...d, rounds: d.rounds.map((r, j) => (j === i ? { ...r, result } : r)), ...(summary ? { summary } : {}) })
      setViewing(i)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  if (index === -1) {
    return (
      <div className="game-done">
        <h2>
          You got {score} of {total} today
        </h2>
        {daily.summary && daily.summary.players > 1 && (
          <>
            <p className="muted small-text">How {daily.summary.players} players did today</p>
            <FieldBars rows={daily.summary.by_score} label={(v) => `${v} of ${total}`} mine={score} />
          </>
        )}
        <div className="kmk-actions">
          <button className="primary" onClick={onPractice}>
            Keep playing
          </button>
          <button onClick={() => setViewing(0)}>Look back at today's rounds</button>
        </div>
      </div>
    )
  }

  const round = daily.rounds[index]
  const last = index === total - 1
  return (
    <>
      <div className="game-progress muted small-text">
        Round {index + 1} of {total}
        {score > 0 && ` · ${score} right so far`}
      </div>
      <OddRound cards={round.cards} result={round.result} busy={busy} onPick={(id) => void pick(index, id)}>
        {round.result?.players != null && round.result.players > 1 && (
          <p className="muted small-text">
            {round.result.right} of {round.result.players} players got this one.
          </p>
        )}
        <div className="kmk-actions">
          <button
            className="primary"
            onClick={() => {
              toTop()
              setViewing(!last && daily.rounds[index + 1].result ? index + 1 : null)
            }}
          >
            {last && next === -1 ? 'See how you did' : 'Next round'}
          </button>
        </div>
      </OddRound>
      {error && <p className="error">{error}</p>}
    </>
  )
}

function Practice({ onDaily }: { onDaily: () => void }) {
  const [round, setRound] = useState<{ token: string; cards: KmkCard[] } | null>(null)
  const [result, setResult] = useState<OddResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tally, setTally] = useState({ right: 0, played: 0 })

  const deal = useCallback(async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setRound(await oddApi.practice())
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }, [])
  useEffect(() => {
    void deal()
  }, [deal])

  const pick = async (id: number) => {
    if (!round) return
    setBusy(true)
    try {
      const { result } = await oddApi.answerPractice(round.token, id)
      setResult(result)
      setTally((t) => ({ right: t.right + (result.correct ? 1 : 0), played: t.played + 1 }))
    } catch (e) {
      setError(errorText(e))
      void deal() // an expired round gets a new one
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="game-progress muted small-text">
        Practice{tally.played > 0 && ` · ${tally.right} of ${tally.played} right`}
        {' · '}
        <button className="link" onClick={onDaily}>
          Back to today's rounds
        </button>
      </div>
      {round && (
        <OddRound cards={round.cards} result={result ?? undefined} busy={busy} onPick={(id) => void pick(id)}>
          <div className="kmk-actions">
            <button
              className="primary"
              onClick={() => {
                toTop()
                void deal()
              }}
              disabled={busy}
            >
              Next round
            </button>
          </div>
        </OddRound>
      )}
      {!round && !error && <p className="muted">Dealing…</p>}
      {error && <p className="error">{error}</p>}
    </>
  )
}

/** The sentence with the shared name as a link. Links open in a new tab, so the game keeps its place. */
function LinkText({ link }: { link: OddLink }) {
  const at = link.name && link.href ? link.text.indexOf(link.name) : -1
  if (at < 0) return <>{link.text}</>
  return (
    <>
      {link.text.slice(0, at)}
      <a href={link.href} target="_blank" rel="noopener noreferrer">
        {link.name}
      </a>
      {link.text.slice(at + link.name!.length)}
    </>
  )
}

/** Four cards to pick from. Once answered, the odd one is marked, your wrong pick too, and the link is told. */
function OddRound({ cards, result, busy, onPick, children }: { cards: KmkCard[]; result?: OddResult; busy: boolean; onPick: (malId: number) => void; children?: ReactNode }) {
  const mark = (c: KmkCard) => {
    if (!result) return ''
    if (c.character.mal_id === result.answer) return 'odd-answer'
    if (c.character.mal_id === result.pick) return 'odd-wrong'
    return 'odd-rest'
  }
  const reveal = useRef<HTMLDivElement>(null)
  const answered = !!result
  useEffect(() => {
    if (answered) reveal.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [answered])
  return (
    <>
      <div className="odd-cards">
        {cards.map((c) => (
          <GameCard key={c.character.id} card={c} className={mark(c)} disabled={busy || !!result} onClick={result ? undefined : () => onPick(c.character.mal_id!)}>
            {result && c.character.mal_id === result.answer && <span className="odd-tag">Odd one out</span>}
          </GameCard>
        ))}
      </div>
      {result && (
        <div className="odd-reveal" ref={reveal}>
          <strong className={result.correct ? 'good' : 'bad'}>{result.correct ? 'Right!' : 'Not quite.'}</strong>
          {result.links.map((l) => (
            <p key={l.text}>
              <LinkText link={l} />
            </p>
          ))}
          {children}
        </div>
      )}
    </>
  )
}
