import { useEffect, useRef, useState, type ReactNode } from 'react'
import { kmkHistoryApi, type KmkCard } from '../api'
import { GenderFix } from './Gender'
import { characterRecency, rememberCharacters } from '../kmkRecent'

export type Choice = 'kiss' | 'marry' | 'kill'
const CHOICES: Choice[] = ['kiss', 'marry', 'kill']
/** What a card ends up as: a choice, or the terrarium for a killed character who was rescued. */
type Fate = Choice | 'terrarium'
const LABELS: Record<Fate, string> = { kiss: 'Kiss', marry: 'Marry', kill: 'Kill', terrarium: 'Terrarium' }
const COLORS: Record<Fate, string> = { kiss: '#ff7eb6', marry: '#ffd166', kill: '#ff4f6a', terrarium: '#4cc38a' }

/** How a round's three are picked: at random, three about as well known as each other, or one famous with two obscure. */
export type DrawMode = 'random' | 'balanced' | 'spicy'
const DRAW_MODES: { value: DrawMode; label: string; tip: string }[] = [
  { value: 'random', label: 'Random', tip: 'Any three from the theme.' },
  { value: 'balanced', label: 'Balanced', tip: 'Three characters about as popular as each other.' },
  { value: 'spicy', label: 'Spicy', tip: 'One famous character and two obscure ones.' },
]
const DRAW_KEY = 'malgraph.kmk.draw'
function loadDraw(): DrawMode {
  try {
    const m = localStorage.getItem(DRAW_KEY)
    return m === 'balanced' || m === 'spicy' ? m : 'random'
  } catch {
    return 'random'
  }
}

function shuffle<T>(xs: T[]): T[] {
  const out = [...xs]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}
/** Popularity on a log scale, so 100 and 1,000 favourites are as far apart as 1,000 and 10,000. */
const fame = (c: KmkCard) => Math.log10(Number(c.character.props.favorites ?? 0) + 1)
/** Cards in the order they should be dealt: ones not seen lately in random order, then the longest unseen. */
function freshFirst(cards: KmkCard[]): KmkCard[] {
  const recency = characterRecency()
  return shuffle(cards).sort((a, b) => (recency.get(a.character.id) ?? -1) - (recency.get(b.character.id) ?? -1))
}
/** The cards not seen lately, or when there are fewer than `min` of those, the `min` longest unseen. */
function fresh(cards: KmkCard[], min: number): KmkCard[] {
  const recency = characterRecency()
  const unseen = cards.filter((c) => !recency.has(c.character.id))
  return unseen.length >= min ? unseen : freshFirst(cards).slice(0, min)
}
/** The `n` cards closest in popularity to `target`, picked at random from the few closest so rounds vary. */
function nearest(cards: KmkCard[], target: number, n: number): KmkCard[] {
  const close = [...cards].sort((a, b) => Math.abs(fame(a) - target) - Math.abs(fame(b) - target)).slice(0, n + 2)
  return shuffle(close).slice(0, n)
}
/** The most popular quarter of a pool and its least popular half. */
function splitByFame(pool: KmkCard[]) {
  const sorted = [...pool].sort((a, b) => fame(b) - fame(a))
  return { famous: sorted.slice(0, Math.ceil(sorted.length / 4)), obscure: sorted.slice(Math.ceil(sorted.length / 2)) }
}

/** Three cards for a round, dealt like a shuffled deck: characters seen lately come back only once the rest are used. */
function draw(pool: KmkCard[], mode: DrawMode = 'random'): KmkCard[] {
  if (pool.length <= 3) return shuffle(pool)
  if (mode === 'balanced') {
    const anchor = freshFirst(pool)[0]
    const others = pool.filter((c) => c !== anchor)
    return shuffle([anchor, ...nearest(fresh(others, 4), fame(anchor), 2)])
  }
  if (mode === 'spicy') {
    const { famous, obscure } = splitByFame(pool)
    if (famous.length && obscure.length >= 2) return shuffle([freshFirst(famous)[0], ...freshFirst(obscure).slice(0, 2)])
  }
  return freshFirst(pool).slice(0, 3)
}

/** A replacement for one card that keeps the round's mode: as popular as the other two, or from the same end. */
function replacement(pool: KmkCard[], cards: KmkCard[], i: number, mode: DrawMode): KmkCard | undefined {
  const taken = new Set(cards.map((c) => c.character.id))
  const rest = pool.filter((c) => !taken.has(c.character.id))
  if (!rest.length) return undefined
  const others = cards.filter((_, j) => j !== i)
  if (mode === 'balanced' && others.length) return nearest(fresh(rest, 3), others.reduce((n, c) => n + fame(c), 0) / others.length, 1)[0]
  if (mode === 'spicy') {
    const { famous, obscure } = splitByFame(pool)
    const side = (famous.includes(cards[i]) ? famous : obscure).filter((c) => !taken.has(c.character.id))
    if (side.length) return freshFirst(side)[0]
  }
  return freshFirst(rest)[0]
}

/** Everyone's choices for one card, as counts. */
export type Tally = Record<Choice, number>

interface Props {
  title: string
  pool: KmkCard[]
  /** The daily round: the pool is the three cards, in order, with no reroll or redraw. */
  fixed?: boolean
  /** Asks the player to lock their choices in, then calls this. Choices are keyed by character id. */
  lockIn?: (choices: Record<string, Choice>) => Promise<void>
  /** Choices already locked in, keyed by character id. */
  locked?: Record<string, Choice>
  /** Everyone's choices per character id, shown once the round is done. */
  tally?: Record<string, Tally>
  /** The daily round's id in your history (rounds from a theme record themselves), and whether it was rescued. */
  roundId?: string
  rescued?: boolean
  onNewTheme?: () => void
  newThemeBusy?: boolean
  onClose?: () => void
  filter?: ReactNode // e.g. the Everyone / Women / Men switch
}

/** One round of Kiss Marry Kill: three characters, each choice used once, one reroll, then a result to share. */
export function KmkRound({ title, pool, fixed, lockIn, locked, tally, roundId: givenId, rescued: givenRescued, onNewTheme, newThemeBusy, onClose, filter }: Props) {
  const [mode, setMode] = useState<DrawMode>(loadDraw)
  const [cards, setCards] = useState(() => (fixed ? pool.slice(0, 3) : draw(pool, mode)))
  const [choices, setChoices] = useState<Record<string, Choice>>(locked ?? {})
  // Every card dealt counts as seen, so the next rounds deal others first.
  useEffect(() => {
    if (!fixed) rememberCharacters(cards.map((c) => c.character.id))
  }, [cards, fixed])
  const [rerolled, setRerolled] = useState(false)
  const [saving, setSaving] = useState(false)
  const [locking, setLocking] = useState(false)
  const [lockError, setLockError] = useState<string | null>(null)
  const complete = cards.length === 3 && cards.every((c) => choices[c.character.id])
  const done = complete && (!lockIn || !!locked)

  // Every finished round goes into your history. The daily round is recorded when it's locked in, so it arrives
  // with its id. The ref keeps a round from being recorded twice (React runs effects twice in development).
  const [recordedId, setRecordedId] = useState<string | null>(null)
  const [rescued, setRescued] = useState(false)
  const [rescuing, setRescuing] = useState(false)
  const recordedFor = useRef<string | null>(null)
  const roundId = givenId ?? recordedId
  const isRescued = rescued || !!givenRescued
  useEffect(() => {
    if (!done || lockIn) return
    const key = cards.map((c) => `${c.character.id}=${choices[c.character.id]}`).join(',')
    if (recordedFor.current === key) return
    recordedFor.current = key
    const byMal = Object.fromEntries(cards.map((c) => [String(c.character.key), choices[c.character.id]]))
    kmkHistoryApi.record(title, byMal).then(
      (r) => setRecordedId(r.round_id),
      () => {}, // not signed in, or offline: the round just isn't kept
    )
  }, [done, lockIn, cards, choices, title])
  const rescue = async () => {
    if (!roundId) return
    setRescuing(true)
    try {
      await kmkHistoryApi.rescue(roundId)
      setRescued(true)
    } finally {
      setRescuing(false)
    }
  }
  const fateOf = (id: string): Fate => (choices[id] === 'kill' && isRescued ? 'terrarium' : choices[id])
  const confirm = async () => {
    if (!lockIn) return
    setLocking(true)
    setLockError(null)
    try {
      await lockIn(choices)
    } catch (e) {
      setLockError(String((e as Error)?.message ?? e).replace(/^\d+: /, ''))
    } finally {
      setLocking(false)
    }
  }

  const again = (m: DrawMode = mode) => {
    setCards(draw(pool, m))
    setChoices({})
    setRerolled(false)
    setRecordedId(null)
    setRescued(false)
  }
  // A correction updates the card in place; the round carries on.
  const fixGender = (id: string, gender: string | null) =>
    setCards((cs) => cs.map((c) => (c.character.id === id ? { ...c, character: { ...c.character, props: { ...c.character.props, gender } } } : c)))
  const changeMode = (m: DrawMode) => {
    setMode(m)
    try {
      localStorage.setItem(DRAW_KEY, m)
    } catch {
      /* storage blocked: the mode lasts until the page closes */
    }
    again(m)
  }
  const reroll = (i: number) => {
    const swap = replacement(pool, cards, i, mode)
    if (!swap) return
    const next = [...cards]
    const old = next[i].character.id
    next[i] = swap
    setCards(next)
    setChoices(({ [old]: _drop, ...keep }) => keep)
    setRerolled(true)
  }
  // Each choice goes to one character: giving it to another card takes it away from the first.
  const assign = (id: string, choice: Choice) =>
    setChoices((prev) => {
      if (prev[id] === choice) {
        const { [id]: _drop, ...rest } = prev
        return rest
      }
      const next = Object.fromEntries(Object.entries(prev).filter(([, c]) => c !== choice))
      return { ...next, [id]: choice }
    })

  const ordered = done ? CHOICES.map((ch) => cards.find((c) => choices[c.character.id] === ch)!) : cards

  const save = async () => {
    setSaving(true)
    try {
      const fates = Object.fromEntries(ordered.map((c) => [c.character.id, fateOf(c.character.id)]))
      const blob = await renderResult(title, ordered, fates)
      const file = new File([blob], 'kiss-marry-kill.png', { type: 'image/png' })
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: 'Kiss Marry Kill' }).catch(() => {})
      } else {
        const a = document.createElement('a')
        a.href = URL.createObjectURL(blob)
        a.download = file.name
        a.click()
        setTimeout(() => URL.revokeObjectURL(a.href), 1000)
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="kmk">
      <div className="kmk-head">
        <h2>{title}</h2>
        {filter}
        {!fixed && pool.length > 3 && (
          <div className="segmented" role="group" aria-label="How the three are drawn">
            {DRAW_MODES.map((m) => (
              <button key={m.value} className={mode === m.value ? 'on' : ''} aria-pressed={mode === m.value} onClick={() => changeMode(m.value)} title={m.tip}>
                {m.label}
              </button>
            ))}
          </div>
        )}
        {onClose && (
          <button className="link" onClick={onClose}>
            Back to all characters
          </button>
        )}
      </div>
      <div className="kmk-cards">
        {ordered.map((c, i) => {
          const chosen = choices[c.character.id]
          const fate = done ? fateOf(c.character.id) : chosen
          return (
            <div key={c.character.id} className={`kmk-card ${chosen ? 'chosen' : ''}`} style={fate ? { borderColor: COLORS[fate] } : undefined}>
              {done && (
                <div className="kmk-verdict" style={{ color: COLORS[fate] }}>
                  {LABELS[fate]}
                </div>
              )}
              {c.character.image_url ? <img src={c.character.image_url} alt="" /> : <div className="noimg" />}
              <strong title={c.character.name}>{c.character.name}</strong>
              <span className="muted small-text kmk-anime" title={c.anime[0]}>
                {c.anime[0]}
              </span>
              {!done && <GenderFix node={c.character} onFixed={(g) => fixGender(c.character.id, g)} />}
              {done && tally?.[c.character.id] && <TallyBar tally={tally[c.character.id]} />}
              {done && chosen === 'kill' && !isRescued && roundId && (
                <button className="link kmk-rescue" onClick={() => void rescue()} disabled={rescuing} title="Save them from their fate. They go to your terrarium instead of your graveyard.">
                  🪴 Put in the terrarium
                </button>
              )}
              {!done && (
                <>
                  <div className="kmk-choices">
                    {CHOICES.map((ch) => (
                      <button key={ch} className={chosen === ch ? 'on' : ''} aria-pressed={chosen === ch} style={chosen === ch ? { background: COLORS[ch], borderColor: COLORS[ch] } : undefined} onClick={() => assign(c.character.id, ch)}>
                        {LABELS[ch]}
                      </button>
                    ))}
                  </div>
                  {!fixed && (
                    <button className="link kmk-reroll" disabled={rerolled || pool.length <= 3} onClick={() => reroll(i)} title="Swap this character for another. Once per round.">
                      {rerolled ? 'Reroll used' : 'Reroll'}
                    </button>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>
      {lockError && <p className="error" role="alert">{lockError}</p>}
      <div className="kmk-actions">
        {lockIn && !done && (
          <button className="primary" onClick={() => void confirm()} disabled={!complete || locking}>
            {locking ? 'Locking in…' : 'Lock in'}
          </button>
        )}
        {done && (
          <button className="primary" onClick={() => void save()} disabled={saving}>
            {saving ? 'Making the image…' : 'Save or share'}
          </button>
        )}
        {!fixed && (
          <button onClick={() => again()} disabled={pool.length < 3}>
            {done ? 'Play again' : 'Draw three others'}
          </button>
        )}
        {onNewTheme && (
          <button onClick={onNewTheme} disabled={newThemeBusy}>
            {newThemeBusy ? 'Spinning…' : 'New theme'}
          </button>
        )}
      </div>
    </div>
  )
}

/** How everyone chose for one character, as a bar split by choice. */
function TallyBar({ tally }: { tally: Tally }) {
  const total = CHOICES.reduce((n, ch) => n + tally[ch], 0)
  if (!total) return null
  return (
    <div className="kmk-tally" title={`${total} ${total === 1 ? 'player' : 'players'}`}>
      <div className="kmk-tally-bar">
        {CHOICES.map((ch) => (tally[ch] ? <i key={ch} style={{ flexGrow: tally[ch], background: COLORS[ch] }} /> : null))}
      </div>
      <div className="kmk-tally-text">
        {CHOICES.map((ch) => (
          <span key={ch} style={{ color: COLORS[ch] }}>
            {LABELS[ch]} {Math.round((100 * tally[ch]) / total)}%
          </span>
        ))}
      </div>
    </div>
  )
}

function loadImage(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null)
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous' // MyAnimeList's and AniList's image servers allow it, so the canvas stays exportable
    img.onload = () => resolve(img)
    img.onerror = () => resolve(null)
    img.src = url
  })
}

function fitText(ctx: CanvasRenderingContext2D, text: string, max: number): string {
  if (ctx.measureText(text).width <= max) return text
  let t = text
  while (t.length > 1 && ctx.measureText(`${t}…`).width > max) t = t.slice(0, -1)
  return `${t}…`
}

/** The finished round as a 1200 x 675 PNG, for a group chat. */
export async function renderResult(title: string, cards: KmkCard[], choices: Record<string, Fate>): Promise<Blob> {
  const W = 1200
  const H = 675
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#12141b'
  ctx.fillRect(0, 0, W, H)
  ctx.textAlign = 'center'
  ctx.fillStyle = '#e8e8ef'
  ctx.font = '600 30px system-ui, sans-serif'
  ctx.fillText(fitText(ctx, title, W - 80), W / 2, 58)

  const images = await Promise.all(cards.map((c) => loadImage(c.character.image_url)))
  const colW = 340
  const gap = (W - 3 * colW) / 4
  const imgW = 220
  const imgH = 320
  cards.forEach((c, i) => {
    const cx = gap + i * (colW + gap) + colW / 2
    const choice = choices[c.character.id]
    ctx.fillStyle = COLORS[choice]
    ctx.font = '800 40px system-ui, sans-serif'
    ctx.fillText(LABELS[choice].toUpperCase(), cx, 130)
    const x = cx - imgW / 2
    const y = 155
    ctx.fillStyle = '#20242f'
    ctx.fillRect(x, y, imgW, imgH)
    const img = images[i]
    if (img) {
      // cover-fit the picture into the frame
      const s = Math.max(imgW / img.width, imgH / img.height)
      const sw = imgW / s
      const sh = imgH / s
      ctx.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, x, y, imgW, imgH)
    }
    ctx.strokeStyle = COLORS[choice]
    ctx.lineWidth = 5
    ctx.strokeRect(x, y, imgW, imgH)
    ctx.fillStyle = '#e8e8ef'
    ctx.font = '600 26px system-ui, sans-serif'
    ctx.fillText(fitText(ctx, c.character.name, colW), cx, y + imgH + 44)
    ctx.fillStyle = '#9aa0ad'
    ctx.font = '20px system-ui, sans-serif'
    ctx.fillText(fitText(ctx, c.anime[0] ?? '', colW), cx, y + imgH + 74)
  })
  ctx.fillStyle = '#8d99ae'
  ctx.font = '16px system-ui, sans-serif'
  ctx.fillText('Kiss Marry Kill · aniweb.eu', W / 2, H - 20)
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not make the image'))), 'image/png'))
}
