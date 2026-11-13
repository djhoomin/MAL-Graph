import { useEffect, useState } from 'react'
import { api, errorText } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

export function PrivacyPage() {
  const me = useStore((s) => s.me)
  const loadMe = useStore((s) => s.loadMe)
  const [confirming, setConfirming] = useState(false)
  const [state, setState] = useState<'idle' | 'deleting' | 'deleted'>('idle')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!me) void loadMe()
  }, [me, loadMe])

  const remove = async () => {
    setState('deleting')
    setError(null)
    try {
      await api.deleteAccount()
      setState('deleted')
    } catch (e) {
      setError(errorText(e))
      setState('idle')
    }
  }

  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => (state === 'deleted' ? window.location.replace('/') : navigate(''))}>
          ← Back to the graph
        </button>
      </header>
      <article className="doc">
        <h1>Privacy</h1>
        <p>MAL-Graph shows your MyAnimeList anime list as a graph. This page explains what it keeps about you, who can see it, and how to delete it.</p>
        {me?.contact && <p>MAL-Graph is run by {me.contact}. Write there with any question about your data.</p>}

        <h2>What MAL-Graph keeps when you sign in</h2>
        <ul>
          <li>Your MyAnimeList username.</li>
          <li>Your anime list. For each anime that means its status, your score, the episodes you've watched, whether you're rewatching it and when you last updated it. Private lists are included, because you sign in with your own account.</li>
          <li>The questions you ask in Ask the graph, the answers, and how many questions you asked each day.</li>
          <li>Your Graph Golf rounds, meaning the moves you made and your score.</li>
        </ul>
        <p>MAL-Graph never sees your MyAnimeList password, because MyAnimeList handles the sign-in. The access MyAnimeList grants is used once to read your list and is then discarded. MAL-Graph never changes anything on MyAnimeList.</p>

        <h2>Who can see it</h2>
        <p>Only you. Other people can't see your list, your questions or your golf rounds. Daily hole results show how many players got each score, without names.</p>
        <p>The anime, characters, voice actors and staff in the graph are public MyAnimeList data that everyone shares.</p>

        <h2>Other services involved</h2>
        <ul>
          <li>MyAnimeList, for signing in and reading your list. Pictures of anime and characters load from MyAnimeList's servers, which see your IP address.</li>
          <li>OpenRouter, only when you use Ask the graph. Your question and the graph data the assistant looks up, which can include your list, go to OpenRouter and the AI model provider it sends them to. They handle it under their own privacy policies.</li>
          <li>Scaleway, which hosts the site and its backups in the Netherlands.</li>
        </ul>

        <h2>Cookies and browser storage</h2>
        <p>MAL-Graph sets one cookie that keeps you signed in for 30 days, and a second one that only lasts the 10 minutes of a sign-in. Your display settings stay in your browser's local storage. There are no analytics, trackers or ads.</p>

        <h2>How long it's kept</h2>
        <p>Your data stays until you delete it. The server's logs record IP addresses and the pages requested, for troubleshooting. They're capped at a small size, so new requests overwrite old ones. A backup is made every night and deleted automatically after 30 days.</p>

        <h2>Deleting your data</h2>
        {state === 'deleted' ? (
          <p className="doc-done">Your data has been deleted and you are signed out. Copies in backups disappear within 30 days.</p>
        ) : me?.username && me.sign_in ? (
          <>
            <p>This removes your list, your Ask conversations and your golf rounds from MAL-Graph straight away, and signs you out. Copies in backups disappear within 30 days. Your MyAnimeList account isn't affected, and signing in again would read your list again.</p>
            {confirming ? (
              <div className="doc-confirm">
                <p>
                  Delete everything MAL-Graph keeps about <b>{me.username}</b>? This can't be undone.
                </p>
                <div className="doc-actions">
                  <button className="danger" onClick={() => void remove()} disabled={state === 'deleting'}>
                    {state === 'deleting' ? 'Deleting…' : 'Delete my data'}
                  </button>
                  <button onClick={() => setConfirming(false)} disabled={state === 'deleting'}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button className="danger" onClick={() => setConfirming(true)}>
                Delete my data
              </button>
            )}
            {error && <p className="error">{error}</p>}
          </>
        ) : (
          <p>Sign in to delete your data. If you can't sign in, contact the person running the site.</p>
        )}

        <h2>Where the anime data comes from</h2>
        <p>
          Anime, character and staff data comes from <a href="https://myanimelist.net" target="_blank" rel="noopener noreferrer">MyAnimeList</a>, through the official MyAnimeList API and <a href="https://jikan.moe" target="_blank" rel="noopener noreferrer">Jikan</a>. MAL-Graph isn't affiliated with or endorsed by MyAnimeList.
        </p>
      </article>
    </div>
  )
}
