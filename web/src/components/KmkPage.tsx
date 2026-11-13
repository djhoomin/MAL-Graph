import { useCallback, useEffect, useState } from 'react'
import { errorText, kmkApi, type KmkTheme } from '../api'
import { navigate } from '../useHashRoute'
import { loadWho, saveWho, WhoFilter, type Who } from './Gender'
import { KmkRound } from './KmkRound'

/** Kiss Marry Kill with a theme drawn at random from your own graph. */
export function KmkPage() {
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
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <div className="kmk-page">
        <h1>Kiss Marry Kill</h1>
        <p className="muted">Three characters from a theme in your list. Give each one a different choice.</p>
        {error && (
          <>
            {!theme && filter}
            <p className="error">{error}</p>
          </>
        )}
        {!theme && !error && <p className="muted">Spinning a theme…</p>}
        {theme && <KmkRound key={`${theme.kind}:${theme.key}:${who}`} title={theme.title} pool={theme.pool} onNewTheme={() => void spin(theme, who)} newThemeBusy={busy} filter={filter} />}
      </div>
    </div>
  )
}
