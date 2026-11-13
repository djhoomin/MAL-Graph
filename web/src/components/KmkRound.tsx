import { useState, type ReactNode } from 'react'
import type { KmkCard } from '../api'
import { GenderFix } from './Gender'

export type Choice = 'kiss' | 'marry' | 'kill'
const CHOICES: Choice[] = ['kiss', 'marry', 'kill']
const LABELS: Record<Choice, string> = { kiss: 'Kiss', marry: 'Marry', kill: 'Kill' }
const COLORS: Record<Choice, string> = { kiss: '#ff7eb6', marry: '#ffd166', kill: '#ff4f6a' }

function draw(pool: KmkCard[], n = 3): KmkCard[] {
  const copy = [...pool]
  const out: KmkCard[] = []
  while (out.length < Math.min(n, pool.length)) out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0])
  return out
}

interface Props {
  title: string
  pool: KmkCard[]
  onNewTheme?: () => void
  newThemeBusy?: boolean
  onClose?: () => void
  filter?: ReactNode // e.g. the Everyone / Women / Men switch
}

/** One round of Kiss Marry Kill: three characters, each choice used once, one reroll, then a result to share. */
export function KmkRound({ title, pool, onNewTheme, newThemeBusy, onClose, filter }: Props) {
  const [cards, setCards] = useState(() => draw(pool))
  const [choices, setChoices] = useState<Record<string, Choice>>({})
  const [rerolled, setRerolled] = useState(false)
  const [saving, setSaving] = useState(false)
  const done = cards.length === 3 && cards.every((c) => choices[c.character.id])

  const again = () => {
    setCards(draw(pool))
    setChoices({})
    setRerolled(false)
  }
  // A correction updates the card in place; the round carries on.
  const fixGender = (id: string, gender: string | null) =>
    setCards((cs) => cs.map((c) => (c.character.id === id ? { ...c, character: { ...c.character, props: { ...c.character.props, gender } } } : c)))
  const reroll = (i: number) => {
    const taken = new Set(cards.map((c) => c.character.id))
    const rest = pool.filter((c) => !taken.has(c.character.id))
    if (!rest.length) return
    const next = [...cards]
    const old = next[i].character.id
    next[i] = rest[Math.floor(Math.random() * rest.length)]
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
      const blob = await renderResult(title, ordered, choices)
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
        {onClose && (
          <button className="link" onClick={onClose}>
            Back to all characters
          </button>
        )}
      </div>
      <div className="kmk-cards">
        {ordered.map((c, i) => {
          const chosen = choices[c.character.id]
          return (
            <div key={c.character.id} className={`kmk-card ${chosen ? 'chosen' : ''}`} style={chosen ? { borderColor: COLORS[chosen] } : undefined}>
              {done && (
                <div className="kmk-verdict" style={{ color: COLORS[chosen] }}>
                  {LABELS[chosen]}
                </div>
              )}
              {c.character.image_url ? <img src={c.character.image_url} alt="" /> : <div className="noimg" />}
              <strong>{c.character.name}</strong>
              <span className="muted small-text">{c.anime[0]}</span>
              {!done && <GenderFix node={c.character} onFixed={(g) => fixGender(c.character.id, g)} />}
              {!done && (
                <>
                  <div className="kmk-choices">
                    {CHOICES.map((ch) => (
                      <button key={ch} className={chosen === ch ? 'on' : ''} style={chosen === ch ? { background: COLORS[ch], borderColor: COLORS[ch] } : undefined} onClick={() => assign(c.character.id, ch)}>
                        {LABELS[ch]}
                      </button>
                    ))}
                  </div>
                  <button className="link kmk-reroll" disabled={rerolled || pool.length <= 3} onClick={() => reroll(i)} title="Swap this character for another. Once per round.">
                    {rerolled ? 'Reroll used' : 'Reroll'}
                  </button>
                </>
              )}
            </div>
          )
        })}
      </div>
      <div className="kmk-actions">
        {done && (
          <button className="primary" onClick={() => void save()} disabled={saving}>
            {saving ? 'Making the image…' : 'Save or share'}
          </button>
        )}
        <button onClick={again} disabled={pool.length < 3}>
          {done ? 'Play again' : 'Draw three others'}
        </button>
        {onNewTheme && (
          <button onClick={onNewTheme} disabled={newThemeBusy}>
            {newThemeBusy ? 'Spinning…' : 'New theme'}
          </button>
        )}
      </div>
    </div>
  )
}

function loadImage(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null)
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous' // MyAnimeList's image server allows it, so the canvas stays exportable
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
export async function renderResult(title: string, cards: KmkCard[], choices: Record<string, Choice>): Promise<Blob> {
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
  ctx.fillStyle = '#6b7080'
  ctx.font = '16px system-ui, sans-serif'
  ctx.fillText('Kiss Marry Kill · MAL-Graph', W / 2, H - 20)
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not make the image'))), 'image/png'))
}
