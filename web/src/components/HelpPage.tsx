import { useGolf } from '../golf'
import { navigate } from '../useHashRoute'

/** What everything in the app does, for someone opening it for the first time. */
export function HelpPage() {
  const golf = () => {
    navigate('')
    void useGolf.getState().start('daily')
  }
  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <article className="doc">
        <h1>Help</h1>
        <p>MAL-Graph draws your MyAnimeList anime list as a graph. Anime, characters, voice actors, staff and studios are the dots, and the lines between them show how they're connected, such as who voices a character or which studio made an anime.</p>

        <h2>Exploring the graph</h2>
        <p>Search for an anime, a character or a person in the bar at the top, and pick a result to put it on the graph. Tap any dot to open its card. On the card, Expand adds everything connected to it, and the ⋯ button has more, such as a voice actor's roles, opening it on MyAnimeList or removing it from the graph.</p>
        <p>Path finds the shortest chain between two things. Tap Path on one card, then tap the other one on the graph or search for it, and the chain is drawn.</p>
        <p>Filters, at the bottom left, hide kinds of dots or connections, or everything that isn't on your list. The button at the bottom right fits the graph to the screen, and holding it down rearranges the graph. Drag with one finger to move around and pinch to zoom.</p>
        <p>The menu at the top right has Add my list to the graph, which puts your whole list on at once, and Sync list, which picks up changes you've made on MyAnimeList since.</p>

        <h2>Ask</h2>
        <p>The speech bubble at the bottom right opens Ask. You can ask questions about your list and the anime, characters and people in it, such as "Which voice actors appear most in what I've watched?" or "What sequels haven't I seen?". The answer is written out, and you can open what it found on the graph. There's a limit on questions per day.</p>

        <h2>Graph tour</h2>
        <p>The <a href="#/tour">graph tour</a>, in the menu, answers questions about your taste from the shape of your graph. It finds clusters of anime that belong together, the people who connect them, and the one person a cluster would fall apart without. It also finds shows made by the same team, new shows to watch with the reasons that lead to them, and the people who keep working together. Last, it measures how far apart your anime are, from the two furthest apart to the ones at the centre and the islands that connect to nothing else. The Voices switch asks some of the same questions of a graph linked only by the voice actors of main characters, such as which shows share a main cast and which voice actors keep leading together. It explains the graph idea behind each answer.</p>

        <h2>Insights and the voice actor roster</h2>
        <p>Insights, in the menu, sums up your list with a timeline, the people who show up most in it, recommendations and gaps. The voice actor roster lists the voice actors in your anime and the characters they voice in it.</p>

        <h2>Games</h2>
        <p>Each game explains its rules when you open it, and you can open them again from How to play.</p>
        <ul>
          <li>
            <button className="link" onClick={golf}>
              Graph Golf
            </button>{' '}
            asks you to get from one thing to another along the graph in as few moves as you can. There's an easy mode with fewer moves to choose from.
          </li>
          <li>
            <a href="#/kmk">Kiss Marry Kill</a> gives you three characters to kiss, marry and kill, and keeps your harem, hookups, graveyard and terrarium in your collection.
          </li>
          <li>
            <a href="#/yay">Yay or Nay</a> deals character cards to swipe right or left on, and shows what the ones you said yay to have in common.
          </li>
          <li>
            <a href="#/odd">Odd one out</a> shows four characters, and you pick the one that doesn't share the link the other three have.
          </li>
          <li>
            <a href="#/mystery">Mystery character</a> asks you to guess a character from clues that get more specific the more you need.
          </li>
        </ul>
        <p>Golf, Odd one out, Mystery character, Today's three in Kiss Marry Kill and Today's stack in Yay or Nay are daily games. They're the same for everyone, they change at midnight UTC, and afterwards you can see how everyone else did. Other players only ever see counts, never names.</p>
      </article>
    </div>
  )
}
