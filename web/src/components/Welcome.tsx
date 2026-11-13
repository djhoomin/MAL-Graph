import { SIGN_IN_URL } from '../api'
import { useStore } from '../store'

/** Shown to visitors who haven't signed in. */
export function Welcome() {
  const authError = useStore((s) => s.authError)
  return (
    <div className="welcome float-panel" role="dialog" aria-labelledby="welcome-title">
      <h2 id="welcome-title">Your anime, as a graph</h2>
      <p className="muted">Sign in with MyAnimeList to map your list and the characters, voice actors and staff behind it.</p>
      <a className="button primary" href={SIGN_IN_URL}>
        Sign in with MyAnimeList
      </a>
      {authError ? <div className="error">{authError}</div> : <div className="muted small-text">We only read your anime list. Nothing is posted to MyAnimeList.</div>}
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
