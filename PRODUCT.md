# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Aniweb is mainly for curious list keepers. They have a sizeable anime list on AniList or MyAnimeList and want to explore
the connections in what they've watched, such as the voice actors, staff and studios their anime share. They use it on
phones and on desktops.

## Product Purpose

Aniweb turns a person's anime list into a graph they can explore. Anime, characters, voice actors, staff, studios and
genres are the nodes, and the edges show how they're connected. A visitor signs in with AniList or MyAnimeList, or
uploads a MyAnimeList export, and then explores, asks questions and plays games with their own list.

How success will be measured hasn't been decided.

## Positioning

Everything starts from the visitor's own list. Four things are central:

- **Connections on a canvas.** The list becomes a graph to walk, with shortest paths between any two anime or people.
- **Ask your own graph.** An agent answers questions from the list and draws the steps it took on the canvas.
- **Games from your list.** The games are played with anime, characters and people, and several use what the player has
  watched.
- **Recognising voices.** The voice actor roster shows everywhere the visitor has already heard someone.

## Operating Context

- The graph canvas is the home screen. Other pages are reached through the menu: Insights, the VA roster, Graph tour,
  Taste match, Kiss Marry Kill, Yay or Nay, Odd one out, Mystery character, Help, and Privacy and your data.
- Graph Golf, Odd one out, Mystery character, Today's three in Kiss Marry Kill and Today's stack in Yay or Nay are daily.
  They're the same for everyone and change at midnight UTC. Other players only see counts, never names.
- Anime on a new list are fetched in the background, so a first visit can happen while the graph is still filling in.
- The canvas fills the screen at every size, and at 700 px and below the node card becomes a bottom sheet. A long press
  on a node opens its menu, and the page can be installed to the home screen.
- Ask has a daily limit on questions.

## Capabilities and Constraints

- **Companion, not a tracker.** Aniweb reads lists and never changes anything on AniList or MyAnimeList. Future work
  must not turn it into a place to keep or edit a list.
- **Phone and desktop equally.** Every feature has to work on a phone as well as on a desktop, including the canvas.
- A site has one data source. The main site uses MyAnimeList data and staging uses AniList data. The plan is to move the
  main site to AniList, pending AniList's reply to an email of 18 November 2026. Copy must name the right source.
- The user can choose English or Japanese titles.
- The graph has no descriptions of characters, so features can't rely on what a character is or is like.
- The whole site is behind a shared password until the items under "Before a public launch" in `TODO.md` are settled.
- Terms used in the interface: graph, canvas, card, Expand, Path, Filters, Ask, Sync list, roster, Insights, Graph tour,
  Taste match.

Open decisions:

- Whether Aniweb stays free and non-commercial for good. It has no ads, trackers or analytics today.

## Brand Commitments

- The name is Aniweb, at aniweb.eu. It replaced MAL-Graph on 22 November 2026, and "MAL" must not return to the name.
- The site says it isn't affiliated with or endorsed by AniList or MyAnimeList.
- The privacy page names DJ Human (contact@aniweb.eu) as the person who runs the site.

## Evidence on Hand

- Working features with real data, described for visitors in `web/src/components/HelpPage.tsx`.
- App icons in `web/public/` (`favicon.svg`, `icon-192.png`, `icon-512.png`).
- There are no testimonials, press, public user numbers or case studies. Future work must not invent any.

## Product Principles

1. Start from the visitor's own list, and make every feature say something about what they've watched.
2. Show the connection behind an answer, so a result can be followed back through the graph.
3. Read lists and leave them alone.
4. Design for the phone and the desktop together.
5. Keep other people's lists and plays private.

## Accessibility & Inclusion

No accessibility standard has been committed to.
