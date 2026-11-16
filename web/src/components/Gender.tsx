import { useState } from 'react'
import { errorText, kmkApi, type GNode } from '../api'

export const GENDERS = ['Female', 'Male', 'Non-binary'] as const
export type Who = '' | 'Female' | 'Male'
const WHO: { value: Who; label: string }[] = [
  { value: '', label: 'Everyone' },
  { value: 'Female', label: 'Women' },
  { value: 'Male', label: 'Men' },
]
const WHO_KEY = 'malgraph.kmk.who'

export const genderOf = (n: GNode): string | null => (typeof n.props.gender === 'string' ? n.props.gender : null)

export function loadWho(): Who {
  try {
    const v = localStorage.getItem(WHO_KEY)
    return v === 'Female' || v === 'Male' ? v : ''
  } catch {
    return ''
  }
}
export function saveWho(who: Who) {
  try {
    localStorage.setItem(WHO_KEY, who)
  } catch {
    /* storage blocked: the choice lasts until reload */
  }
}

/** Everyone / Women / Men, for Kiss Marry Kill. */
export function WhoFilter({ value, onChange, disabled }: { value: Who; onChange: (w: Who) => void; disabled?: boolean }) {
  return (
    <div className="segmented" role="group" aria-label="Who to include">
      {WHO.map((w) => (
        <button key={w.value} className={value === w.value ? 'on' : ''} onClick={() => onChange(w.value)} disabled={disabled}>
          {w.label}
        </button>
      ))}
    </div>
  )
}

/** A character's gender with a way to correct it. Corrections are shared with everyone. */
export function GenderFix({ node, onFixed }: { node: GNode; onFixed: (gender: string | null) => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const current = genderOf(node)
  if (node.label !== 'Character' || node.key == null) return null

  const pick = async (g: string | null) => {
    setBusy(true)
    setError(null)
    try {
      await kmkApi.fixGender(node.key!, g)
      onFixed(g)
      setOpen(false)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="gender-fix">
      {open ? (
        <span className="gender-options">
          {[...GENDERS, null].map((g) => (
            <button key={g ?? 'unknown'} className={g === current ? 'on' : ''} disabled={busy} onClick={() => void pick(g)}>
              {g ?? 'Unknown'}
            </button>
          ))}
          <button className="link" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </button>
        </span>
      ) : (
        <button className="link gender-current" onClick={() => setOpen(true)} title="Correct this character's gender for everyone">
          {current ?? 'Gender unknown'} · fix
        </button>
      )}
      {error && <span className="error small-text">{error}</span>}
    </span>
  )
}
