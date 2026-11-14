import type { ReactNode } from 'react'
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
