import { useState, type ReactNode } from 'react'
import type { Histogram, KmkCard } from '../api'

/** A character card for the daily games: picture, name and best-known anime. */
export function GameCard({ card, onClick, className = '', disabled, children }: { card: KmkCard; onClick?: () => void; className?: string; disabled?: boolean; children?: ReactNode }) {
  const body = (
    <>
      {card.character.image_url ? <img src={card.character.image_url} alt="" /> : <div className="noimg" />}
      <strong title={card.character.name}>{card.character.name}</strong>
      <span className="muted small-text kmk-anime" title={card.anime[0]}>
        {card.anime[0]}
      </span>
      {children}
    </>
  )
  return onClick ? (
    <button className={`kmk-card game-card ${className}`} onClick={onClick} disabled={disabled}>
      {body}
    </button>
  ) : (
    <div className={`kmk-card game-card ${className}`}>{body}</div>
  )
}

/** How the day's players did, as bars. `label` names each value, such as "3 of 5". */
export function FieldBars({ rows, label, mine }: { rows: Histogram[]; label: (value: number) => string; mine?: number | null }) {
  if (!rows.length) return null
  const most = Math.max(...rows.map((r) => r.players))
  return (
    <div className="golf-field">
      {rows.map((r) => (
        <div key={r.value} className={`golf-bar ${r.value === mine ? 'mine' : ''}`}>
          <span>{label(r.value)}</span>
          <i style={{ width: `${(100 * r.players) / most}%` }} />
          <b>{r.players}</b>
        </div>
      ))}
    </div>
  )
}

const HOWTO_KEY = 'malgraph.howto.'

/** Whether someone has seen a game's rules. The rules start open until they're closed once. */
function seen(id: string): boolean {
  try {
    return localStorage.getItem(HOWTO_KEY + id) === 'seen'
  } catch {
    return false
  }
}

export function useHowTo(id: string): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(() => !seen(id))
  const change = (next: boolean) => {
    setOpen(next)
    if (!next) {
      try {
        localStorage.setItem(HOWTO_KEY + id, 'seen')
      } catch {
        /* storage blocked: the rules open again next visit */
      }
    }
  }
  return [open, change]
}

/** The rules of a game, open on the first visit and folded away once read. */
export function HowTo({ id, children }: { id: string; children: ReactNode }) {
  const [open, setOpen] = useHowTo(id)
  return (
    <details className="howto" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>How to play</summary>
      <div className="howto-body">
        {children}
        <button className="primary" onClick={() => setOpen(false)}>
          Got it
        </button>
      </div>
    </details>
  )
}
