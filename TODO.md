# TODO

Open work for MAL-Graph, in rough priority order. Production runs `main` behind the site password.

## Before a public launch

- [ ] **Ask MyAnimeList for written permission.** Their API agreement conflicts with three things the app does. It
      stores users' lists on the server (§3(c)). It gets characters, voice actors and staff from Jikan, which scrapes
      the MyAnimeList website (§4(i)). And it uses "MAL" in the app name and domain (§17). The request goes through
      MyAnimeList's API support form. The site is non-commercial and read-only, which helps.
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

- [ ] **Daily Kiss Marry Kill.** The same three for everyone each day, with an anonymous tally of choices. It can reuse
      the daily-hole and anonymous-results setup from Graph Golf.
- [ ] **Balanced Kiss Marry Kill draws.** Pick three characters of similar popularity using MyAnimeList favourites, or
      a spicy mode with one famous character and two obscure ones.
- [ ] **Guess the voice actor.** Show three characters and ask who voices all of them.
- [ ] **Pass-the-phone Kiss Marry Kill** for groups, revealing where players agreed.

## Checks not done yet

- [ ] **Graph Golf on a phone.** The layout was built for phones but only tested on a desktop.
- [ ] **Insights timeline on a phone.** The y-axis labels scroll out of view along with the chart.
