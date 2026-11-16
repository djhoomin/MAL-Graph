import { useEffect, useState } from 'react'
import { errorText, matchApi, SIGN_IN_URL, type MakerKind, type Match, type MatchAnime, type MatchInvite, type MatchLink, type MatchMaker, type MatchPick } from '../api'
import { navigate } from '../useHashRoute'

/** Where a visitor's invite waits while they sign in, since signing in comes back to the start page. */
export const PENDING_INVITE_KEY = 'malgraph.match.invite'

const signedOut = (e: unknown) => String((e as Error)?.message ?? '').startsWith('401')
const score = (n: number | null) => (n === null ? 'Not scored' : Number.isInteger(n) ? String(n) : n.toFixed(1))
const lean = (n: number) => (n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1))
const KIND: Record<MakerKind, string> = { studio: 'Studio', director: 'Director', writer: 'Series composition', voice: 'Lead voice', genre: 'Genre' }
const inviteUrl = (token: string) => `${window.location.origin}${window.location.pathname}#/match/join/${token}`

/** Taste match: compare your list with someone else's, once you've both agreed to it through an invite link. */
export function MatchPage({ route }: { route: string[] }) {
  const [view, arg] = [route[1], route[2] ? decodeURIComponent(route[2]) : '']
  return (
    <div className="doc-page">
      <header className="doc-head">
        {view ? (
          <button className="link" onClick={() => navigate('match')}>
            ← Taste match
          </button>
        ) : (
          <button className="link" onClick={() => navigate('')}>
            ← Back to the graph
          </button>
        )}
      </header>
      <div className="kmk-page match">
        {view === 'join' && arg ? <Join token={arg} /> : view === 'with' && arg ? <Compare key={arg} them={arg} /> : <Overview />}
      </div>
    </div>
  )
}

function SignIn({ text }: { text: string }) {
  return (
    <div className="match-signin">
      <p>{text}</p>
      <a className="button primary" href={SIGN_IN_URL}>
        Sign in with MyAnimeList
      </a>
    </div>
  )
}

function Overview() {
  const [links, setLinks] = useState<MatchLink[] | null>(null)
  const [invite, setInvite] = useState<MatchInvite | null>(null)
  const [days, setDays] = useState(7)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    matchApi.overview().then(
      (o) => {
        setLinks(o.links)
        setInvite(o.invite)
        setDays(o.invite_days)
      },
      (e) => (signedOut(e) ? setOut(true) : setError(errorText(e))),
    )
  }, [])

  const make = async () => {
    setBusy(true)
    setError(null)
    try {
      setInvite(await matchApi.invite())
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }
  const cancel = async () => {
    try {
      await matchApi.cancelInvite()
      setInvite(null)
    } catch (e) {
      setError(errorText(e))
    }
  }

  return (
    <>
      <h1>Taste match</h1>
      <p className="muted">Compare your anime list with a friend's.</p>
      {out ? (
        <SignIn text="Sign in to compare lists." />
      ) : (
        <>
          <section className="match-invite">
            <h2>Invite someone</h2>
            <p className="muted small-text">
              Send them a link. Nothing is compared until they open it and accept, and either of you can unlink at any time. A link works once and lasts {days} days.
            </p>
            {invite ? <InviteLink invite={invite} onCancel={() => void cancel()} onNew={() => void make()} /> : (
              <button className="primary" onClick={() => void make()} disabled={busy || !links}>
                Make an invite link
              </button>
            )}
          </section>
          {error && <p className="error">{error}</p>}
          <section>
            <h2>People you're linked with</h2>
            {!links ? (
              !error && <p className="muted">Loading…</p>
            ) : links.length ? (
              <ul className="match-links">
                {links.map((l) => (
                  <li key={l.username}>
                    <a href={`#/match/with/${encodeURIComponent(l.username)}`}>
                      <strong>{l.username}</strong>
                      <span className="muted small-text">{l.shared === 1 ? '1 series in common' : `${l.shared} series in common`}</span>
                    </a>
                    <b className="match-pct">{l.match}%</b>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">You haven't linked with anyone yet.</p>
            )}
          </section>
        </>
      )}
    </>
  )
}

function InviteLink({ invite, onCancel, onNew }: { invite: MatchInvite; onCancel: () => void; onNew: () => void }) {
  const [copied, setCopied] = useState(false)
  const url = inviteUrl(invite.token)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      /* clipboard blocked: the link is selectable in the box */
    }
  }
  const until = new Date(invite.expires * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'long' })
  return (
    <div className="match-link-box">
      <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} aria-label="Invite link" />
      <div className="match-link-actions">
        <button className="primary" onClick={() => void copy()}>
          {copied ? 'Copied' : 'Copy link'}
        </button>
        <button onClick={onNew}>New link</button>
        <button onClick={onCancel}>Cancel link</button>
      </div>
      <p className="muted small-text">Works once, until {until}.</p>
    </div>
  )
}

function Join({ token }: { token: string }) {
  const [invite, setInvite] = useState<{ from: string; own: boolean; linked: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [out, setOut] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    matchApi.seeInvite(token).then(setInvite, (e) => {
      if (!signedOut(e)) return setError(errorText(e))
      setOut(true)
      try {
        localStorage.setItem(PENDING_INVITE_KEY, token)
      } catch {
        /* storage blocked: they can open the link again after signing in */
      }
    })
  }, [token])

  const accept = async () => {
    setBusy(true)
    try {
      const { username } = await matchApi.accept(token)
      navigate(`match/with/${encodeURIComponent(username)}`)
    } catch (e) {
      setError(errorText(e))
      setBusy(false)
    }
  }

  if (out) return <SignIn text="Someone has invited you to compare anime lists. Sign in to see who." />
  if (error) return <p className="error">{error}</p>
  if (!invite) return <p className="muted">Loading…</p>
  if (invite.own) return <p>This is your own invite link. Send it to the person you want to compare with.</p>
  if (invite.linked)
    return (
      <p>
        You're already linked with {invite.from}. <a href={`#/match/with/${encodeURIComponent(invite.from)}`}>See your match</a>.
      </p>
    )
  return (
    <div className="match-join">
      <h1>{invite.from} wants to compare anime lists with you</h1>
      <p>If you accept, you'll both see how well your tastes match and the scores you each gave the anime you've both watched. You'll also see the studios and people you both rate highly, the anime each of you rated highest that the other hasn't watched, and the anime you both plan to watch.</p>
      <p>Either of you can unlink at any time from Taste match, and that stops the comparison straight away. Deleting your data also removes every link.</p>
      <div className="match-link-actions">
        <button className="primary" onClick={() => void accept()} disabled={busy}>
          Compare lists
        </button>
        <button onClick={() => navigate('match')}>No thanks</button>
      </div>
    </div>
  )
}

function Compare({ them }: { them: string }) {
  const [m, setM] = useState<Match | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)

  useEffect(() => {
    matchApi.compare(them).then(setM, (e) => setError(errorText(e)))
  }, [them])

  const unlink = async () => {
    try {
      await matchApi.unlink(them)
      navigate('match')
    } catch (e) {
      setError(errorText(e))
    }
  }

  if (error) return <p className="error">{error}</p>
  if (!m) return <p className="muted">Comparing your lists…</p>
  const { counts, parts } = m
  return (
    <>
      <h1>You and {m.them}</h1>
      <div className="match-score">
        <b>{m.match}%</b>
        <span className="muted">match</span>
      </div>

      <div className="match-parts">
        <div>
          <h3>Score agreement</h3>
          {parts.agreement === null ? (
            <p className="muted small-text">You need at least 3 series you've both scored for this, so it isn't part of the match yet.</p>
          ) : (
            <>
              <b className="match-pct">{parts.agreement}%</b>
              <p className="muted small-text">
                From the {counts.scored} series you've both scored, each measured against your own average. You average {m.means.you.toFixed(1)} and {m.them} averages {m.means.them.toFixed(1)}. This is {m.weights.agreement}% of the match.
              </p>
            </>
          )}
        </div>
        <div>
          <h3>Shared makers</h3>
          {parts.makers === null ? (
            <p className="muted small-text">One of you hasn't scored enough anime for this yet.</p>
          ) : (
            <>
              <b className="match-pct">{parts.makers}%</b>
              <p className="muted small-text">
                How alike the studios, directors, writers, lead voice actors and genres you each score above or below your average are. It works even for anime only one of you has seen. This is {m.weights.makers}% of the match.
              </p>
            </>
          )}
        </div>
        <div>
          <h3>Watched overlap</h3>
          <b className="match-pct">{parts.overlap}%</b>
          <p className="muted small-text">
            You've both watched {counts.shared} series. You've watched {counts.only_you} that {m.them} hasn't, and {m.them} has watched {counts.only_them} that you haven't. Shared shows with fewer members count for more. This is {m.weights.overlap}% of the match.
          </p>
        </div>
      </div>

      <AnimeList title="You both loved" note="Both scored above your own averages." rows={m.loved} them={m.them} />
      <AnimeList title="Where you disagree" note="One of you scored it above your average and the other below." rows={m.split} them={m.them} />
      <AnimeList title="Rare ones you've both seen" note="Fewer than 100,000 members on MyAnimeList." rows={m.rare} them={m.them} />
      <MakerList rows={m.makers} them={m.them} />

      <PickList title={`For you, from ${m.them}'s favourites`} note={`Anime ${m.them} scored well above their average that you haven't watched, best fit for you first.`} rows={m.for_you} who={m.them} planned="On your plan to watch" />
      <PickList title={`For ${m.them}, from your favourites`} note={`Anime you scored well above your average that ${m.them} hasn't watched, best fit for them first.`} rows={m.for_them} who="You" planned={`On ${m.them}'s plan to watch`} />
      <PickList title="To watch together" note={counts.planned > m.together.length ? `${counts.planned} series are on both your plans to watch. These look like the best fit for you both.` : 'On both your plans to watch, best fit for you both first.'} rows={m.together} />

      <div className="match-unlink">
        {confirm ? (
          <>
            <span>Stop comparing lists with {m.them}?</span>
            <button className="danger" onClick={() => void unlink()}>
              Unlink
            </button>
            <button onClick={() => setConfirm(false)}>Keep</button>
          </>
        ) : (
          <button onClick={() => setConfirm(true)}>Unlink from {m.them}</button>
        )}
      </div>
    </>
  )
}

function AnimeList({ title, note, rows, them }: { title: string; note: string; rows: MatchAnime[]; them: string }) {
  if (!rows.length) return null
  return (
    <section className="match-list">
      <h2>{title}</h2>
      <p className="muted small-text">{note}</p>
      <ul>
        {rows.map((a) => (
          <li key={a.id}>
            {a.image ? <img src={a.image} alt="" /> : <span className="noimg" />}
            <a href={a.url ?? undefined} target="_blank" rel="noreferrer">
              {a.title}
            </a>
            <span className="match-scores">
              <span>
                <i>You</i> {score(a.you)}
              </span>
              <span>
                <i>{them}</i> {score(a.them)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function MakerList({ rows, them }: { rows: MatchMaker[]; them: string }) {
  if (!rows.length) return null
  return (
    <section className="match-list">
      <h2>Makers you both rate</h2>
      <p className="muted small-text">How many points above your own average you each score their anime.</p>
      <ul>
        {rows.map((m) => (
          <li key={`${m.kind}:${m.name}`} className="match-maker">
            <span className="match-maker-name">
              <i>{KIND[m.kind]}</i>
              {m.name}
            </span>
            <span className="match-scores">
              <span>
                <i>You</i> {lean(m.you)}
              </span>
              <span>
                <i>{them}</i> {lean(m.them)}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function PickList({ title, note, rows, who, planned }: { title: string; note: string; rows: MatchPick[]; who?: string; planned?: string }) {
  if (!rows.length) return null
  return (
    <section className="match-list">
      <h2>{title}</h2>
      <p className="muted small-text">{note}</p>
      <ul>
        {rows.map((a) => (
          <li key={a.id}>
            {a.image ? <img src={a.image} alt="" /> : <span className="noimg" />}
            <span className="match-pick">
              <a href={a.url ?? undefined} target="_blank" rel="noreferrer">
                {a.title}
              </a>
              {a.because && (
                <span className="muted small-text">
                  {KIND[a.because.kind]}: {a.because.name}
                </span>
              )}
              {a.planned && planned && <span className="match-tag">{planned}</span>}
            </span>
            {who && a.score !== undefined && (
              <span className="match-scores">
                <span>
                  <i>{who}</i> {score(a.score)}
                </span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
