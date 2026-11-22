import { useEffect, useState } from 'react'
import { api, errorText } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

export function PrivacyPage() {
  const me = useStore((s) => s.me)
  const al = me?.data_source === 'anilist' // an AniList site: AniList data and sign-in only
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
        <p>Aniweb shows your {al ? 'AniList' : 'MyAnimeList'} anime list as a graph. This page explains what it keeps about you, who can see it, and how to delete it.</p>
        {me?.contact && <p>Aniweb is run by {me.contact}.</p>}

        <h2>What Aniweb keeps when you sign in</h2>
        <ul>
          <li>{al ? 'Your AniList username.' : 'Your MyAnimeList or AniList username, whichever you signed in with.'}</li>
          <li>Your anime list. For each anime that means its status, your score, the episodes you've watched, whether you're rewatching it and when you last updated it. Private lists are included, because you sign in with your own account.</li>
          <li>The questions you ask in Ask the graph, the answers, and how many questions you asked each day.</li>
          <li>Your plays of the daily games, meaning your Graph Golf moves and score, your Odd one out picks, your Mystery character guesses, and every Kiss Marry Kill round you finish, which make up your collection.</li>
          <li>Who you've linked with in Taste match, and your open invite link.</li>
        </ul>
        {al ? (
          <p>Aniweb never sees your password, because AniList handles the sign-in. The access it grants is used once to read your list and is then discarded. Aniweb never changes anything on AniList. If you upload a MyAnimeList export file instead, only its statuses, scores and episode counts are kept, anime that AniList doesn't have are left out, and the file itself isn't stored.</p>
        ) : (
        <p>Aniweb never sees your password, because MyAnimeList or AniList handles the sign-in. The access they grant is used once to read your list and is then discarded. Aniweb never changes anything on either site. An AniList list joins the graph through each anime's MyAnimeList id, so anime that aren't on MyAnimeList are left out. If you upload a MyAnimeList export file instead, only its statuses, scores and episode counts are kept, and the file itself isn't stored.</p>
        )}

        <h2>Who can see it</h2>
        <p>Only you, unless you link with someone in Taste match. Linking needs an invite link from one of you that the other accepts. Once linked, you each see how well your tastes match, the scores you each gave the anime you've both watched, the studios and people you both rate highly, the anime each of you rated highest that the other hasn't watched, and the anime you both plan to watch. Either of you can unlink at any time. Otherwise, other people can't see your list, your questions or your game plays. Daily results show only counts, such as how many players got each score or chose Kiss for a character, and never names.</p>
        <p>The anime, characters, voice actors and staff in the graph are public {al ? 'AniList' : 'MyAnimeList'} data that everyone shares.</p>

        <h2>Other services involved</h2>
        <ul>
          {al ? (
            <li>AniList, for signing in, reading your list and the anime data. Pictures of anime and characters load from AniList's servers, which see your IP address.</li>
          ) : (
            <>
              <li>MyAnimeList, for signing in and reading your list. Pictures of anime and characters load from MyAnimeList's servers, which see your IP address.</li>
              <li>AniList, if you sign in with it, for signing in and reading your list.</li>
            </>
          )}
          <li>OpenRouter, only when you use Ask the graph. Your question and the graph data the assistant looks up, which can include your list, go to OpenRouter and the AI model provider it sends them to. They handle it under their own privacy policies.</li>
          <li>Scaleway, which hosts the site and its backups in the Netherlands.</li>
        </ul>

        <h2>Cookies and browser storage</h2>
        <p>Aniweb sets one cookie that keeps you signed in for 30 days, and a second one that only lasts the 10 minutes of a sign-in. Your display settings stay in your browser's local storage. There are no analytics, trackers or ads.</p>

        <h2>How long it's kept</h2>
        <p>Your data stays until you delete it. The server's logs record IP addresses and the pages requested, for troubleshooting. They're capped at a small size, so new requests overwrite old ones. A backup is made every night and deleted automatically after 30 days.</p>

        <h2>Deleting your data</h2>
        {state === 'deleted' ? (
          <p className="doc-done">Your data has been deleted and you are signed out. Copies in backups disappear within 30 days.</p>
        ) : me?.username && me.sign_in ? (
          <>
            <p>This removes your list, your Ask conversations, your game plays and your Taste match links from Aniweb straight away, and signs you out. Copies in backups disappear within 30 days. Your {al ? 'AniList' : 'MyAnimeList or AniList'} account isn't affected, and signing in again would read your list again.</p>
            {confirming ? (
              <div className="doc-confirm">
                <p>
                  Delete everything Aniweb keeps about <b>{me.username}</b>? This can't be undone.
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
        {al ? (
          <p>
            Anime, character and staff data, including character genders, comes from <a href="https://anilist.co" target="_blank" rel="noopener noreferrer">AniList</a> through its official API. Aniweb only fetches the anime on players' lists and what they open. Anyone signed in can correct a character's gender. Corrections are shared and aren't linked to the person who made them. Aniweb isn't affiliated with or endorsed by AniList.
          </p>
        ) : (
        <p>
          Anime, character and staff data comes from <a href="https://myanimelist.net" target="_blank" rel="noopener noreferrer">MyAnimeList</a>, through the official MyAnimeList API and <a href="https://jikan.moe" target="_blank" rel="noopener noreferrer">Jikan</a>. Character genders come from <a href="https://anilist.co" target="_blank" rel="noopener noreferrer">AniList</a>, and anyone signed in can correct one. Corrections are shared and aren't linked to the person who made them. Aniweb isn't affiliated with or endorsed by MyAnimeList or AniList.
        </p>
        )}
      </article>
    </div>
  )
}
