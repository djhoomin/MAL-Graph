import { useCallback, useEffect, useState } from 'react'
import { errorText, kmkApi, type KmkTheme } from '../api'
import { navigate } from '../useHashRoute'
import { KmkRound } from './KmkRound'

/** Kiss Marry Kill with a theme drawn at random from your own graph. */
export function KmkPage() {
  const [theme, setTheme] = useState<KmkTheme | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const spin = useCallback(async (current?: KmkTheme | null) => {
    setBusy(true)
    setError(null)
    try {
      setTheme(await kmkApi.theme(current ? { avoid: `${current.kind}:${current.key}` } : {}))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void spin()
  }, [spin])

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
        {error && <p className="error">{error}</p>}
        {!theme && !error && <p className="muted">Spinning a theme…</p>}
        {theme && <KmkRound key={`${theme.kind}:${theme.key}`} title={theme.title} pool={theme.pool} onNewTheme={() => void spin(theme)} newThemeBusy={busy} />}
      </div>
    </div>
  )
}
