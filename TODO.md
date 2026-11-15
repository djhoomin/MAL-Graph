# TODO

Open work for MAL-Graph, in rough priority order. Production runs `main` behind the site password.

## Before a public launch

- [ ] **Ask MyAnimeList for written permission.** Their API agreement conflicts with three things the app does. It
      stores users' lists on the server (§3(c)). It gets characters, voice actors and staff from Jikan, which scrapes
      the MyAnimeList website (§4(i)). And it uses "MAL" in the app name and domain (§17). The request goes through
      MyAnimeList's API support form. The site is non-commercial and read-only, which helps. The request was sent
      through the support form on 14 November 2026, and this stays open until they reply.
- [ ] **Rename the app.** Drop "MAL" from the name, the domain (`mal-graph.eu`) and the Kiss Marry Kill share image
      footer, whichever data source the app ends up on.
- [ ] **Add a way to contact you on the privacy page.** `PRIVACY_CONTACT` is "DJ Human" with no address. GDPR expects
      people to be able to reach the operator, so add an email address to the server's `.env` and restart the API.
- [ ] **Set a monthly spending cap on the OpenRouter key** in OpenRouter's dashboard, if that isn't done yet.
- [ ] **Take the site password off** once the items above are settled. It's the `basic_auth` block in `web/Caddyfile`.

## AniList as a data source (fallback if MyAnimeList says no)

AniList's API officially provides everything the graph uses: anime, characters, voice actors by language, staff
roles, studios, related anime, genres and genders. Its terms allow non-commercial use but forbid "hoarding or mass
collection", so the app must fetch on demand for what users have rather than crawl. AniList characters and staff only
have AniList ids, so an AniList graph needs its own database rather than sharing the MyAnimeList one.

- [ ] **Step 1: make ids source-neutral.** Rename `mal_id` to `id` across the backend, queries, agent prompt and
      frontend (about 250 places), with a one-off migration for the existing graph. Take "Open on MAL" links from
      each node's `url`. No change for users.
- [ ] **Step 2: AniList data adapter.** Build the same graph shape from AniList, on demand: the user's list anime
      plus whatever they expand. Reuse the rate-limited client in `backend/malgraph/genders.py`.
- [ ] **Step 3: lists without the MyAnimeList API.** Sign in with AniList (OAuth), and accept an upload of the list
      export file that MyAnimeList lets every user download.
- [ ] **Step 4: source switch.** A setting such as `DATA_SOURCE=anilist` chooses the source per deployment, with its
      own Memgraph data. Try it on a staging copy before switching the live site.
- [ ] **Ask AniList to confirm** that a shared, on-demand cache fits their terms (their Discord is the quickest route).

## Operations

- [ ] **Do a restore drill** from a backup into a local copy, following `deploy/README.md`, to prove the backups work.
- [ ] **Watch Memgraph memory** as users join. It used about 825 MB of its 2 GiB limit in November 2026. A bigger
      Scaleway instance is the simple fix when it gets close.

## Product ideas

- [x] **Daily Kiss Marry Kill.** The same three for everyone each day, with an anonymous tally of choices. Built as
      "Today's three" on the Kiss Marry Kill page.
- [x] **Balanced Kiss Marry Kill draws.** Random, Balanced (three of similar popularity by MyAnimeList favourites) and
      Spicy (one famous, two obscure). Pools are now 30 of a theme's best-known characters and 10 from the rest.
- [ ] **Guess the voice actor.** Show three characters and ask who voices all of them.
- [ ] **Pass-the-phone Kiss Marry Kill** for groups, revealing where players agreed.
- [x] **Odd one out.** Four characters, three of which share a hidden link (voice actor, studio, creator or season).
      Pick the one that doesn't belong. The graph guarantees exactly one answer. Cheap to build and works as a daily.
- [x] **Mystery character.** Guess a character from clues revealed one at a time from the graph, for example "voiced
      by someone who also played X", "from a Fall 2019 anime" or "made by the studio behind Y". Fewer clues score more.
      Fits a daily format with an anonymous tally.
- [ ] **Who's the link.** Two anime, and the player names a person who worked on both using search. Rarer answers
      score more, so a much-cast voice actor is worth less than the shared sound director.
- [ ] **Voice chain.** Build the longest chain alternating character, voice actor, character through anime you've
      seen, with no repeats. An endurance version of Graph Golf.
- [x] **Insights from your own list.** Hot takes (your score against MyAnimeList's average), your genres against
      your mean score, hidden gems (scored 8 or more, under 100k members, not sequels) and shows paused near the end.
- [x] **Graph tour, steps 1 and 2.** Taste clusters (Louvain community detection) and the bridges between them
      (betweenness centrality), run in Memgraph on the user's anime and their makers, with the query shown.
- [x] **Graph tour, step 3.** Cut points (biconnected components per cluster): the person, studio or anime a cluster
      falls apart without, with the pieces it holds together.
- [x] **Cluster timeline.** Each cluster's anime by season, with the people and studios behind two or more of them
      as highlights, so patterns like one creator's shows alternating cours stand out.
- [x] **Graph tour, step 4.** Twins, the anime from different series with the highest Jaccard similarity of makers.
- [x] **Graph tour, steps 5 and 6.** Paths to new shows (two-step paths from anime scored 8 or more, weighted the
      Adamic-Adar way) and creative teams (the people-to-anime graph projected onto people). PageRank was tried on the
      tour graph and dropped, because the links point people into anime and anime into studios, so it rewarded
      studios and people with a single credit.
- [x] **What each team made together.** Teams list other anime they worked on that you haven't seen. Anime only
      known by title are fetched in the background on a tour queue and appear on a later visit.
- [x] **Graph tour, step 7.** How far apart your anime are: islands (connected components), the two series furthest
      apart (the diameter, by breadth-first search between series) and the series at the centre. People born before
      1900, such as composers credited when an anime plays their pieces, are left out of the tour.
- [ ] **Theme draft.** Two to four friends take turns drafting characters for a Kiss Marry Kill roulette theme, then
      vote on the best team. Reuses the existing theme pools.
- [ ] **Taste match (next up).** Compare two people's lists for a compatibility score with reasons: how closely they
      scored the anime both have seen, shared favourite voice actors and studios both rate highly. It should also list
      what one loved that the other hasn't seen, both ways, and the anime both have on plan to watch, as picks to watch
      together. Lists are private, so both people must agree through an invite link before anything is compared, and
      either one can unlink at any time. Unlinking and account deletion must remove the link. Asked for in November
      2026, now that two people use the app.

## Checks not done yet

- [x] **Graph Golf on a phone.** The layout was built for phones but only tested on a desktop.
- [x] **Odd one out and Mystery character on a real phone.** Checked at phone width in a desktop browser only.
- [x] **Graph tour's "Show on the graph" in a real browser.** The layout and fit run on an animation, which the
      automated test browser never plays because its tab is hidden. The positions it computes look right.
- [ ] **Insights timeline on a phone.** The y-axis labels scroll out of view along with the chart.
