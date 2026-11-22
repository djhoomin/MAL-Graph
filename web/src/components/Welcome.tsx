import { ANILIST_SIGN_IN_URL, SIGN_IN_URL } from '../api'
import { useSource, useStore } from '../store'

// Sign-in error codes from /api/auth/callback. Unknown codes get the generic message, so a crafted link can't show
// text of its own.
const AUTH_ERRORS: Record<string, string> = {
  cancelled: 'Sign-in was cancelled.',
  incomplete: 'Sign-in did not complete. Please try again.',
  expired: 'The sign-in took too long or was started in another tab. Please try again.',
  rejected: 'The sign-in was not accepted. Please try again.',
  profile: 'Your profile could not be read. Please try again.',
  list: 'You are signed in, but your list could not be read. Try Sync list in the menu.',
}

/** Shown to visitors who haven't signed in. */
export function Welcome() {
  const code = useStore((s) => s.authError)
  const authError = code ? (AUTH_ERRORS[code] ?? AUTH_ERRORS.incomplete) : null
  const anilist = useStore((s) => !!s.me?.anilist)
  const mal = useStore((s) => s.me?.mal ?? !!s.me?.sign_in)
  const src = useSource()
  const sites = [mal && 'MyAnimeList', anilist && 'AniList'].filter(Boolean).join(' or ')
  return (
    <div className="welcome float-panel" role="dialog" aria-labelledby="welcome-title">
      <h2 id="welcome-title">Your anime, as a graph</h2>
      <p className="muted">Sign in with {sites || src.name} to map your list and the characters, voice actors and staff behind it.</p>
      {mal && (
        <a className="button primary" href={SIGN_IN_URL}>
          Sign in with MyAnimeList
        </a>
      )}
      {anilist && (
        <a className={`button ${mal ? 'secondary' : 'primary'}`} href={ANILIST_SIGN_IN_URL}>
          Sign in with AniList
        </a>
      )}
      {authError && <div className="error">{authError}</div>}
      <div className="muted small-text">
        Aniweb only reads your anime list and never posts anything. By signing in you agree to the <a href="#/privacy">privacy notice</a>.
      </div>
      <div className="muted small-text">
        {src.anilist ? 'Data from AniList. Not affiliated with AniList.' : `Data from MyAnimeList${anilist ? ' and AniList' : ''}. Not affiliated with MyAnimeList${anilist ? ' or AniList' : ''}.`}
      </div>
    </div>
  )
}

/** Shown while the anime on the list are being fetched in the background. */
export function SyncPill() {
  const sync = useStore((s) => s.sync)
  const src = useSource()
  if (!sync?.running) return null
  const pct = sync.total ? Math.round((100 * sync.done) / sync.total) : 0
  return (
    <div className="sync-pill float-panel" title={`New anime are fetched from ${src.name} in the background. You can keep exploring.`}>
      <span>
        Fetching anime from {src.name} · {sync.done} of {sync.total}
        {sync.others_in_queue > 0 && <span className="muted"> · {sync.others_in_queue} other {sync.others_in_queue === 1 ? 'list' : 'lists'} in the queue</span>}
      </span>
      <span className="progress">
        <i style={{ width: `${pct}%` }} />
      </span>
    </div>
  )
}
