# TODO

Open work for MAL-Graph, in rough priority order. Production runs `main` behind the site password.

## Before a public launch

- [x] **Ask MyAnimeList for written permission.** Their API agreement conflicts with three things the app does. It
      stores users' lists on the server (§3(c)). It gets characters, voice actors and staff from Jikan, which scrapes
      the MyAnimeList website (§4(i)). And it uses "MAL" in the app name and domain (§17). The request went through
      the support form on 14 November 2026. MyAnimeList replied on 18 November that they don't give permission on an
      individual basis and that the API must be used within the guidelines, so none of the three is allowed. Without
      stored lists and the Jikan data most of the app goes, so AniList becomes the main data source (below).
- [ ] **Ask AniList to confirm** that a shared, on-demand cache fits their terms. This is now the permission the public
      launch depends on. The question was emailed to contact@anilist.co (the only contact their API terms give) on
      18 November 2026, and this stays open until they reply. Their terms allow free use under $150 a month of
      revenue, with a commercial licence above that, and a name with "AniList" in it must say "unofficial" or "for AniList".
- [ ] **Switch production to AniList.** Run `app` with `DATA_SOURCE=anilist`, as staging does, once AniList agrees.
      MyAnimeList users bring their lists across with the export upload. Decide whether the current MyAnimeList graph
      and its users' data are deleted or kept until people have moved.
- [x] **Rename the app.** It's Aniweb since 22 November 2026, at https://aniweb.eu with staging at
      https://staging.aniweb.eu. The old `mal-graph.eu` addresses redirect there. Let `mal-graph.eu` expire in
      September 2027 once nobody uses the old links. The GitHub repo and the Python package still carry the old name.
- [x] **Add a way to contact you on the privacy page.** Since 23 November 2026 `PRIVACY_CONTACT` is
      "DJ Human (contact@aniweb.eu)". Cloudflare hosts the aniweb.eu DNS and its Email Routing forwards that address to
      your inbox. Replies go out from your own address.
- [x] **Set a monthly spending cap on the OpenRouter key** in OpenRouter's dashboard. DJ confirmed it on 25 November 2026.
- [ ] **Moderate questions to Ask with Mistral Moderation**, so people can't use it for prompt injection or other abuse.
      `mistral-moderation-2603` has a jailbreaking category and takes a threshold per category. It's free and
      runs in the EU (from DJ, 25 November 2026). Check each question before the agent runs, and decline flagged ones without running it. Set the thresholds so ordinary questions
      about violent anime and Kiss Marry Kill get through, and add both kinds to the evals. Decide what happens when
      the service is down, and whether a declined question counts towards the daily limit. It adds to the privacy
      guard on Cypher and doesn't replace it, and text the tools return (synopses, names) isn't covered by checking
      the question alone. Name Mistral on the privacy page, since questions will go there too.
- [ ] **Take the site password off** once the items above are settled. It's the `basic_auth` block in `web/Caddyfile`.

## AniList as a data source (the main source, since MyAnimeList said no on 18 November 2026)

AniList's API officially provides everything the graph uses: anime, characters, voice actors by language, staff
roles, studios, related anime, genres and genders. Its terms allow non-commercial use but forbid "hoarding or mass
collection", so the app must fetch on demand for what users have rather than crawl. AniList characters and staff only
have AniList ids, so an AniList graph needs its own database rather than sharing the MyAnimeList one.

- [x] **Step 1: make ids source-neutral.** Nodes keep their source id as `id`, and `db.migrate_ids` moved the old
      `mal_id` property at startup (it also migrates an old backup after a restore). API payloads use `id`, except graph
      nodes, where `id` is already the "Label:key" ref, so the source id is `key`. Links to MyAnimeList come from each
      node's `url`. Jikan's own `mal_id` fields, the Jikan and MyAnimeList clients and the AniList gender lookup by
      MyAnimeList id keep the name, since those really are MyAnimeList ids. UI copy still says MAL.
- [x] **Step 2: AniList data adapter.** `anilist_source.AniListSource` answers the same calls as the Jikan client
      and returns Jikan's shapes with AniList ids, so ingest builds the same graph. It fetches on demand at 25 requests
      a minute and caches answers on disk. An anime takes 1 or 2 requests, with up to 50 characters and 50 staff (main
      cast and key staff first). Genres keep fixed ids, and up to 5 strong theme and setting tags become themes.
      Characters come with genders, so the gender worker is off. The Ask agent's catalogue tools (search, top,
      season, recommendations) use AniList too.
- [x] **Step 3a: sign in with AniList.** AniList OAuth (`/api/auth/anilist/login` and `/callback`, client in
      `ANILIST_CLIENT_ID` and `ANILIST_API_KEY`). AniList users are stored as `<name>@anilist`, and their list joins
      today's graph through each anime's `idMal`, so anime without one are skipped and counted. Sync list rereads a
      public AniList list, and a private one needs signing in again, as with MyAnimeList. An AniList deployment will
      use the same sign-in with AniList ids instead.
- [x] **Step 3b: list export upload.** Upload MyAnimeList export in the menu sends the file from Export lists
      (`.xml` or `.xml.gz`) to `/api/sync/upload`, which replaces the signed-in user's list. Only ids, statuses, scores
      and episode counts are read. Size is capped before and after unzipping, and files with a DOCTYPE are refused.
      Checked with a real export (355 entries), which matched the synced list on every id, status, score and episode count.
- [x] **Step 4: source switch.** `DATA_SOURCE=anilist` chooses the source per deployment, signs people in with
      AniList only, maps a MyAnimeList export to AniList ids, and makes the UI name AniList. Tested locally on a
      second Memgraph with the full AniList list. The AniList copy runs at `staging.mal-graph.eu` from
      `docker-compose.anilist.yml` (see `deploy/README.md`), with its own AniList API client and graph, and fetched
      a 355-anime list on 16 November 2026.
- [ ] **Ask AniList to confirm** the cache, listed under "Before a public launch".

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
- [x] **Yay or Nay.** Swipe right or left on character cards, as a daily stack of 20 with each card's yay share and as
      an endless stack from your list. Your patterns shows the voice actors, studios, genres and series your yays and
      nays lean towards. It asks no question on purpose: a "Smash or Pass" framing would need age data the graph lacks.
- [x] **Yay or Nay on a real phone.** The swipe is built on pointer events. Checked on a phone and works well.
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
- [x] **Ask on LangGraph, with LangSmith evals.** The hand-written tool loop became a LangGraph StateGraph (agent,
      ToolNode, a nudge node for empty replies) with conversations as threads in a SQLite checkpointer. Runs of the
      users in LANGSMITH_TRACE_USERS are traced to LangSmith. `malgraph eval-ask` scores ten questions on correctness
      (checked against the graph), private lists, a tool budget and tool errors, locally or as a LangSmith experiment.
- [x] **Voice lens for the tour.** The same graph ideas on a graph joined only by the Japanese voice actors of main
      characters, as a Voices switch on the tour with bridges, twins, duos and distance. Clusters and paths were left
      out, since leads work on too many shows a year to say much about taste. On Manned00d's list this has no islands, a diameter of 5 series and a radius of 3, against 7 and 4
      for the makers' graph, and the busiest leads (Rie Takahashi, Sora Amamiya, Asami Seto, Ayane Sakura) each voice
      a main role in 9 series. Generations of voice actors may still form islands on lists that go back decades.
- [ ] **Theme draft.** Two to four friends take turns drafting characters for a Kiss Marry Kill roulette theme, then
      vote on the best team. Reuses the existing theme pools.
- [x] **Taste match.** Invite links (one use, 7 days), unlinking, and removal on account deletion. The match blends
      score agreement (cosine of each person's scores measured from their own average, over shared series), shared
      makers (cosine of profiles of studios, directors, series composers, lead voices and genres) and watched overlap
      (Jaccard weighted by 1 / log(members)). Agreement weighs up to 50%, less with few shared scores, and makers take
      the rest after overlap's 20%. It names the series both loved, where they disagree, rare shared ones and the makers
      both rate, and picks from each other's favourites and from both plans to watch, each with the maker behind it.
      Links live in `data/golf/match/links.json`.
- [ ] **Taste match summary (later).** An LLM-written summary of a match, written from the same data the page shows.
- [ ] **Calibrate taste match** once a few real pairs are linked. The weights and the square root on overlap were set
      on one real list and a synthetic one. A pick shows its series' most-watched entry, which picks a later season when
      the first one has no member count yet (Bungou Stray Dogs).

## Ask agent

- [x] **Answer from what it has when the tool budget runs out.** The graph counts tool calls per turn. Past
      `MAX_STEPS` (20), an `out_of_steps` node answers the pending calls with a note and the model answers with
      `tool_choice="none"`, from what it found. `recursion_limit` stays only as a guard against a loop.
- [x] **Stronger evals.** Experiments ask every question three times (`--repetitions`). A trajectory check looks for
      a tool suited to the question, no repeated calls and no cards before data. A judge model (`ASK_JUDGE_MODEL`,
      Claude Sonnet 5.5 by default) grades how well each answer serves its question, with rubrics for the
      recommendations, privacy and connection questions.
- [x] **Keep old tool results out of the context.** The model sees the current turn in full and only the questions
      and answers of earlier turns, the last 10 within 30,000 characters. The checkpointer still keeps everything.
- [x] **Stream the answer.** The graph streams in `messages` and `updates` modes, and the UI shows the reply as it
      arrives. Text a model writes before a tool call is dropped when the call arrives.
- [x] **Compile the graph once.** The system prompt, the conversation id and the turn's UI side effects travel as the
      run's context (`AskContext`), and a small tool node of our own replaced the prebuilt ToolNode and the
      ContextVar. `create_agent` needs the `langchain` package, which isn't installed, and the nudge and out-of-steps
      steps are custom, so the hand-built graph stays.
- [x] **Thumbs up and down on answers.** Each turn keeps its run id. A thumb is saved with the conversation and, for
      traced users, sent to LangSmith as `user_score` feedback on the run. The same thumb again takes it back.
- [x] **Show the agent's trail on the canvas.** Each graph step sends what it found (up to 40 nodes and the edges
      between them) as a `trail` event, drawn in blue, with dashed borders on the nodes it added. When the answer is
      done those added nodes go again, unless the answer showed them. The steps list shows each step's result and the
      full Cypher of queries, and a "show" link draws a step again, from conversation history too (`/api/subgraph`).
- [x] **Keep an answer written before its last tool call.** A model often writes the whole answer, then calls
      `show_on_canvas` or `present_cards`, then replies with one line. Text alongside a display tool is now part of
      the answer, so the line is added to it instead of replacing it. GLM 5.3 failed the Chainsaw Man eval this way.
- [x] **Schema notes for GLM's mistakes.** The system prompt now says that unscored anime have score 0, that
      `positions` is a list to test with `IN` (a `{positions: ['Director']}` pattern matched 302 of 1,054 director
      credits), what a sequel is, that Memgraph's `round` takes one argument, and that the graph can't say what a
      character is (a cat, a dog), so such answers come from the model and must say so.

## Checks not done yet

- [x] **Graph Golf on a phone.** The layout was built for phones but only tested on a desktop.
- [x] **Odd one out and Mystery character on a real phone.** Checked at phone width in a desktop browser only.
- [x] **Graph tour's "Show on the graph" in a real browser.** The layout and fit run on an animation, which the
      automated test browser never plays because its tab is hidden. The positions it computes look right.
- [x] **Insights timeline on a phone.** The y-axis labels scroll out of view along with the chart. Checked on a phone
      and fine.
