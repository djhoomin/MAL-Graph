import { useState } from 'react'
import { useStore } from '../store'

/** First-run card: pick the MyAnimeList user whose list becomes the graph. Also opened by "Switch user". */
export function Welcome() {
  const user = useStore((s) => s.user)
  const busy = useStore((s) => s.busy)
  const { switchUser, setWelcomeOpen } = useStore.getState()
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const hasList = !!user?.total
  const valid = /^[A-Za-z0-9_-]{2,16}$/.test(name.trim())

  const submit = async () => {
    setError(null)
    const err = await switchUser(name)
    if (err) setError(err)
  }

  return (
    <div className="welcome float-panel" role="dialog" aria-labelledby="welcome-title">
      <h2 id="welcome-title">{hasList ? 'Switch user' : 'Your anime, as a graph'}</h2>
      <p className="muted">
        {hasList
          ? 'Enter another MyAnimeList username to see their list as a graph.'
          : 'Enter your MyAnimeList username to map your list and the characters, voice actors and staff behind it.'}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) void submit()
        }}
      >
        <input
          autoFocus
          name="mal-user"
          placeholder="MyAnimeList username"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="off"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          // not a sign-in form: keep password managers from offering to fill it
          data-1p-ignore
          data-lpignore="true"
          data-bwignore
        />
        <button className="primary" type="submit" disabled={!valid || !!busy}>
          {busy ? 'Reading list…' : 'Build my graph'}
        </button>
      </form>
      {error ? <div className="error">{error}</div> : <div className="muted small-text">Your anime list must be public on MyAnimeList.</div>}
      {hasList && (
        <button className="link" onClick={() => setWelcomeOpen(false)}>
          Cancel
        </button>
      )}
    </div>
  )
}

/** Shown while the anime on the list are being fetched in the background. */
export function SyncPill() {
  const sync = useStore((s) => s.sync)
  if (!sync?.running) return null
  const pct = sync.total ? Math.round((100 * sync.done) / sync.total) : 0
  return (
    <div className="sync-pill float-panel" title="New anime are fetched from MyAnimeList in the background. You can keep exploring.">
      <span>
        Fetching anime from MyAnimeList · {sync.done} of {sync.total}
        {sync.others_in_queue > 0 && <span className="muted"> · {sync.others_in_queue} other {sync.others_in_queue === 1 ? 'list' : 'lists'} in the queue</span>}
      </span>
      <span className="progress">
        <i style={{ width: `${pct}%` }} />
      </span>
    </div>
  )
}
