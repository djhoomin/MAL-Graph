// Typed wrappers around the FastAPI backend. All graph-returning endpoints share GraphPayload.
export type Label = 'Anime' | 'Character' | 'Person' | 'Studio' | 'Genre' | 'User'
export type RelType = 'LISTED' | 'HAS_CHARACTER' | 'VOICES' | 'WORKED_ON' | 'RELATED_TO' | 'PRODUCED_BY' | 'HAS_GENRE'

export type ListStatus = 'completed' | 'watching' | 'on_hold' | 'plan_to_watch' | 'dropped' | 'none'
export const LIST_STATUSES: ListStatus[] = ['completed', 'watching', 'on_hold', 'plan_to_watch', 'dropped', 'none']
export const LIST_STATUS_LABELS: Record<ListStatus, string> = {
  completed: 'completed',
  watching: 'watching',
  on_hold: 'on hold',
  plan_to_watch: 'plan to watch',
  dropped: 'dropped',
  none: 'not on my list',
}

export const LABELS: Label[] = ['Anime', 'Character', 'Person', 'Studio', 'Genre', 'User']
export const REL_TYPES: RelType[] = ['LISTED', 'HAS_CHARACTER', 'VOICES', 'WORKED_ON', 'RELATED_TO', 'PRODUCED_BY', 'HAS_GENRE']

export interface GNode {
  id: string
  label: Label
  key: number | null // the node's id in the data source, since id is the graph's "Label:key"
  name: string
  image_url: string | null
  watched: boolean | null
  list_status: string | null
  fetched: boolean
  props: Record<string, unknown>
}
export interface GEdge {
  id: string
  source: string
  target: string
  type: RelType
  props: Record<string, unknown>
}
export interface GraphPayload {
  nodes: GNode[]
  edges: GEdge[]
}
export interface PathResult extends GraphPayload {
  found: boolean
  hops: number | null
  paths: string[][]
}
export interface VaRole {
  character: GNode
  anime: GNode
  role: string | null
  language: string | null
}
export interface VaResult extends GraphPayload {
  roles: VaRole[]
}
export interface RosterEntry {
  person: GNode
  characters: number
  anime: number
}
export interface NodeDetail {
  node: GNode
  degrees: { type: RelType; label: Label; n: number }[]
}
export interface ListAnime {
  id: number
  title: string
  title_english: string | null
  image_url: string | null
  type: string | null
  year: number | null
  season: string | null
  aired_from: string | null
  episodes: number | null
  score: number | null
  members: number | null
  status: ListStatus
  my_score: number
  episodes_watched: number
  updated_at: string | null
  studios: { id: number; name: string }[]
  genres: { id: number; name: string; kind: string }[]
  follow_up?: boolean // a sequel or side story, which always has fewer members than what it follows
}
export interface RankedPerson {
  person: GNode
  anime_ids: number[]
  characters: number
  avg_my_score: number | null
}
export interface Gap {
  id: number
  title: string
  url: string | null
  image_url: string | null
  score: number | null
  type: string | null
  year: number | null
  season: string | null
  aired_from: string | null
  /** MyAnimeList's airing status, such as "Not yet aired". Null until the anime is fetched. */
  airing: string | null
  fetched: boolean
  via: { relation: string; id: number; title: string; my_score: number; status: ListStatus }[]
}
export interface Recommendation {
  anime: GNode
  score: number
  via: string[]
  n_people: number
}
export interface SyncStatus {
  running: boolean
  total: number
  done: number
  failed: { id: number; error: string }[]
  current: number | null
  others_in_queue: number
}
export interface UserSummary {
  username: string | null
  by_status: Record<string, number>
  total: number
  unfetched: number
}

// Dev talks to uvicorn on :8000; in production Caddy serves the UI and proxies /api on the same origin.
// Dev and production both serve /api on the same origin as the UI (Vite proxies it in dev), so the session
// cookie is sent with every request.
const BASE = import.meta.env.VITE_API_BASE ?? ''

/** Full-page navigation target that starts "Sign in with MyAnimeList". */
export const SIGN_IN_URL = BASE + '/api/auth/login'
export const ANILIST_SIGN_IN_URL = BASE + '/api/auth/anilist/login'
export interface Me {
  username: string | null // AniList accounts end in "@anilist"
  source?: 'mal' | 'anilist' | null // where the signed-in user's list comes from
  sign_in: boolean // false when the server has no sign-in configured (local development)
  mal?: boolean // whether "Sign in with MyAnimeList" is configured
  anilist?: boolean // whether "Sign in with AniList" is configured
  data_source?: 'mal' | 'anilist' // where anime, characters and people come from
  contact?: string | null // who runs the site, for the privacy page
}

/** The site anime, characters and people come from, as the UI names it. */
export interface Source {
  name: string // "MyAnimeList" or "AniList"
  short: string // "MAL" or "AniList", for tight spots like "MAL 8.21"
  anilist: boolean
}
const MAL_SOURCE: Source = { name: 'MyAnimeList', short: 'MAL', anilist: false }
const ANILIST_SOURCE: Source = { name: 'AniList', short: 'AniList', anilist: true }
export const sourceOf = (dataSource: string | null | undefined): Source => (dataSource === 'anilist' ? ANILIST_SOURCE : MAL_SOURCE)

/** Error message without the HTTP status prefix, for showing inline. */
export const errorText = (e: unknown) => String((e as Error)?.message ?? e).replace(/^\d+: /, '')

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

const qs = (params: Record<string, string | number | boolean | null | undefined>) =>
  '?' +
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')

export interface NeighborOpts {
  only_watched?: boolean
  lang?: string | null
  rels?: RelType[]
  limit?: number
}

export interface AskStatus {
  configured: boolean
  model: string | null
  remaining_today: number | null // questions left today; null means no daily cap
}

export interface ConversationSummary {
  id: string
  title: string
  model: string | null
  updated_at: number
  turns: number
}
/** One tool call of an Ask answer. `found` and `refs` say what a graph step found, for drawing it again. */
export interface AskStep {
  id?: string
  name: string
  args: Record<string, unknown>
  error?: string
  found?: string
  refs?: string[]
}
export interface ConversationTurn {
  role: 'user' | 'assistant'
  text: string
  steps: AskStep[]
  cards: { title: string; cards: { node: GNode; caption: string }[] }[]
  usage?: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number } | null
  error?: string | null
  run_id?: string
  feedback?: number | null
}
export interface Conversation {
  id: string
  title: string
  model: string | null
  created_at: number
  updated_at: number
  turns: ConversationTurn[]
}

export type AskEvent =
  | { type: 'session'; id: string; model: string; resumed: boolean }
  | { type: 'tool_call'; id?: string; name: string; args: Record<string, unknown> }
  | { type: 'trail'; id: string; summary: string; payload: GraphPayload }
  | { type: 'tool_error'; name: string; message: string }
  | { type: 'canvas'; payload: GraphPayload & { select?: string } }
  | { type: 'cards'; title: string; cards: { node: GNode; caption: string }[] }
  | { type: 'delta'; text: string }
  | { type: 'answer'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done'; usage: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number }; run_id?: string }

/** POST /api/ask and yield server-sent events as they arrive. */
export async function* ask(message: string, sessionId: string | null, signal?: AbortSignal): AsyncGenerator<AskEvent> {
  const res = await fetch(BASE + '/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  })
  if (!res.ok || !res.body) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* not JSON */
    }
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data: '))
      if (line) yield JSON.parse(line.slice(6)) as AskEvent
    }
  }
}

export const api = {
  search: (q: string, limit = 8, kinds?: Label[]) =>
    req<{ query: string; results: Partial<Record<Label, GNode[]>> }>(`/api/search${qs({ q, limit, kinds: kinds?.join(',') })}`),
  node: (id: string) => req<NodeDetail>(`/api/node/${id}`),
  neighbors: (id: string, o: NeighborOpts = {}) =>
    req<GraphPayload>(`/api/neighbors/${id}${qs({ only_watched: o.only_watched, lang: o.lang, rels: o.rels?.join(','), limit: o.limit })}`),
  expand: (id: string, o: NeighborOpts = {}) =>
    req<GraphPayload & { fetched: Record<string, number>; seconds: number }>(
      `/api/expand/${id}${qs({ only_watched: o.only_watched, lang: o.lang })}`,
      { method: 'POST' },
    ),
  path: (from: string, to: string, o: { max_hops?: number; only_watched?: boolean; exclude?: string; rels?: string; lang?: string | null; all_paths?: boolean; limit?: number }) =>
    req<PathResult>(`/api/path${qs({ from, to, ...o })}`),
  vaRoles: (personId: number, only_watched: boolean, lang: string | null) =>
    req<VaResult>(`/api/person/${personId}/characters${qs({ only_watched, lang })}`),
  roster: (o: { only_watched?: boolean; main_only?: boolean; lang?: string | null; min_characters?: number; q?: string; limit?: number }) =>
    req<{ people: RosterEntry[] }>(`/api/roster${qs(o)}`),
  user: () => req<UserSummary>('/api/user'),
  askStatus: () => req<AskStatus>('/api/ask/status'),
  conversations: () => req<{ conversations: ConversationSummary[] }>('/api/conversations'),
  conversation: (id: string) => req<Conversation>(`/api/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    req<{ id: string; title: string }>(`/api/conversations/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => req<{ deleted: boolean }>(`/api/conversations/${id}`, { method: 'DELETE' }),
  subgraph: (refs: string[]) =>
    req<GraphPayload>('/api/subgraph', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refs }) }),
  answerFeedback: (id: string, runId: string, score: number | null) =>
    req<{ run_id: string; feedback: number | null }>(`/api/conversations/${id}/feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_id: runId, score }) }),
  insightsList: () => req<{ anime: ListAnime[] }>('/api/insights/list'),
  insightsPeople: (kind: string, statuses: string[], lang: string | null, min_anime = 2, limit = 40) =>
    req<{ kind: string; people: RankedPerson[] }>(`/api/insights/people${qs({ kind, statuses: statuses.join(','), lang, min_anime, limit })}`),
  insightsRecommendations: (via: 'va' | 'staff' | 'studio', min_score: number | null, types: string, limit = 40) =>
    req<{ via: string; recommendations: Recommendation[] }>(`/api/insights/recommendations${qs({ via, min_score, types, limit })}`),
  insightsGaps: (statuses: string[]) => req<{ gaps: Gap[] }>(`/api/insights/gaps${qs({ statuses: statuses.join(',') })}`),
  me: () => req<Me>('/api/auth/me'),
  signOut: () => fetch(BASE + '/api/auth/logout', { method: 'POST' }),
  deleteAccount: () => fetch(BASE + '/api/auth/account', { method: 'DELETE' }).then((r) => {
    if (!r.ok) throw new Error('Your data could not be deleted. Please try again.')
  }),
  sync: () => req<{ username: string; synced: number; skipped?: number; unfetched: number; expanding: boolean }>('/api/sync', { method: 'POST' }),
  /** Replace the list with the file from MyAnimeList's Export lists, sent as is. */
  uploadList: (file: File) =>
    req<{ username: string; synced: number; skipped?: number; unfetched: number; expanding: boolean; exported_by: string | null }>('/api/sync/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
    }),
  syncStatus: () => req<SyncStatus>('/api/sync/status'),
  stats: () => req<Record<string, number>>('/api/stats'),
}

// --------------------------------------------------------------------------- Graph Golf
export interface GolfHole {
  date: string | null // set for the daily hole
  par: number
  start: GNode
  end: GNode
}
export interface GolfRound {
  strokes: number
  mulligans: number
  gave_up: boolean
  moves: string[]
}
export interface GolfSummary {
  players: number
  finished: number
  by_score: { to_par: number; players: number }[]
  rank: number | null
}
export interface GolfResult {
  round?: GolfRound
  first_round?: boolean
  shortest: number | null
  summary?: GolfSummary
  solution: GraphPayload & { paths: string[][] }
}
export type DailyResponse = GolfHole & Partial<GolfResult> & { round?: GolfRound }

export const golfApi = {
  daily: (easy = false) => req<DailyResponse>(`/api/golf/daily${qs({ easy: easy || undefined })}`),
  practice: () => req<GolfHole>('/api/golf/practice'),
  /** Every move from `ref`, or in easy mode a short list toward the hole `to` plus the distance to it. */
  moves: (ref: string, easyTo?: string) => req<GraphPayload & { to_hole?: number | null }>(`/api/golf/moves/${ref}${qs({ to: easyTo, easy: easyTo ? true : undefined })}`),
  finishDaily: (moves: string[], mulligans: number, gave_up: boolean, easy = false) =>
    req<GolfResult & { par: number }>('/api/golf/daily', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ moves, mulligans, gave_up, easy }) }),
  finishPractice: (start: string, end: string, moves: string[], mulligans: number, gave_up: boolean) =>
    req<GolfResult>('/api/golf/practice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ start, end, moves, mulligans, gave_up }) }),
}

// --------------------------------------------------------------------------- Kiss Marry Kill
export interface KmkCard {
  character: GNode
  anime: string[] // titles, up to three
  main: boolean
}
export interface KmkTheme {
  kind: string
  key: string | number
  title: string
  pool: KmkCard[]
}
export const kmkApi = {
  theme: (o: { avoid?: string; kind?: string; key?: string | number; gender?: string | null } = {}) => req<KmkTheme>(`/api/kmk/theme${qs(o)}`),
  fixGender: (characterId: number, gender: string | null) =>
    req<{ id: number; gender: string | null }>(`/api/kmk/character/${characterId}/gender`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ gender }) }),
}

// --------------------------------------------------------------------------- Daily games
const post = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

/** Players per value (a score, or clues used), without names. */
export interface Histogram {
  value: number
  players: number
}

export type KmkChoice = 'kiss' | 'marry' | 'kill'
export interface KmkDaily {
  date: string
  title: string
  cards: KmkCard[]
  choices?: Record<string, KmkChoice> // by character id, once played
  round_id?: string // this play in your history, for a rescue
  rescued?: boolean // its killed character went to the terrarium
  tally?: { players: number; counts: Record<string, Record<KmkChoice, number>> }
}

/** A sentence about what the three share, with the shared thing's name and where it links to. */
export interface OddLink {
  text: string
  name?: string
  href?: string // '#/roster/…' inside the app, otherwise a MyAnimeList page
}
export interface OddResult {
  pick: number
  correct: boolean
  answer: number // id of the odd one
  links: OddLink[] // what the other three share, main link first
  players?: number // daily only: how many answered this round
  right?: number
}
export interface OddDaily {
  date: string
  rounds: { cards: KmkCard[]; result?: OddResult }[]
  summary?: { players: number; by_score: Histogram[] }
}
export const oddApi = {
  daily: () => req<OddDaily>('/api/odd/daily'),
  answer: (index: number, pick: number) => req<{ result: OddResult; summary?: OddDaily['summary'] }>(`/api/odd/daily/${index}`, post({ pick })),
  practice: () => req<{ token: string; cards: KmkCard[] }>('/api/odd/practice'),
  answerPractice: (token: string, pick: number) => req<{ result: OddResult }>('/api/odd/practice', post({ token, pick })),
}

export interface Mystery {
  date: string
  total: number // clues there are
  clues: string[] // shown so far (all of them once done)
  used: number // clues the player has seen, which is the score once solved
  guesses: GNode[]
  right_anime: number[] // ids of wrong guesses from the answer's anime or its franchise
  branch: number | null // how many anime clues came before the character clues took over, once a guess got the anime
  solved: boolean
  done: boolean
  correct?: boolean // after a guess
  answer?: KmkCard // once done
  summary?: { players: number; solved: number; by_clues: Histogram[] }
  token?: string // a game from your own list
}
/** A person or studio in the tour, with how many of your series they're behind. */
export interface TourMaker {
  id: string
  label: 'Person' | 'Studio'
  key: number
  name: string
  series: number
}
export interface TourCluster {
  anime: number
  series: { id: number; title: string; image_url: string | null; my_score: number }[]
  makers: TourMaker[]
  genres: string[]
  timeline: {
    items: { id: number; title: string; image_url: string | null; year: number; season: number; makers: string[] }[] // season 0 is winter
    makers: { id: string; name: string; anime: number }[] // the people and studios behind two or more of the cluster's anime
  }
}
/** Anime from different series that share most of their makers. */
export interface TourTwins {
  shows: { id: number; title: string; image_url: string | null }[]
  shared: { id: string; label: 'Person' | 'Studio'; name: string }[]
  either: number // people and studios behind either of the first pair
  jaccard: number
}
export interface TourBridge extends TourMaker {
  rank: number
  count_rank: number // their place when ranked by how many of your series they're behind
  clusters: { cluster: number; id: number; title: string; image_url: string | null }[]
}
/** A cut point: the person, studio or anime a cluster falls apart without, and the pieces it holds together. */
export interface TourCut {
  id: string
  label: 'Person' | 'Studio' | 'Anime'
  key: number
  name: string
  image_url: string | null
  cluster: number
  sides: { series: number; anime: number; items: { id: number; title: string; image_url: string | null }[] }[]
}
/** A single series that only connects to its cluster through one person, studio or anime. */
export interface TourThread {
  cluster: number
  show: { id: number; title: string; image_url: string | null }
  via: { id: string; label: 'Person' | 'Studio' | 'Anime'; name: string }
  also: { id: number; title: string; image_url: string | null }[] // what the person or studio made in the rest of the cluster
}
/** An anime you haven't listed, reached in two steps from anime you scored highly. */
export interface TourRec {
  anime: { id: number; title: string; image_url: string | null; mal_score: number | null; members: number | null; type: string | null; year: number | null }
  score: number
  paths: {
    maker: { id: string; label: 'Person' | 'Studio'; name: string }
    made: number // anime this person or studio is credited on in the whole graph
    because: { id: number; title: string; image_url: string | null; my_score: number }[]
  }[]
}
/** People who keep working together across your series. */
export interface TourTeam {
  people: { id: string; name: string }[]
  series: number
  shows: { id: number; title: string; image_url: string | null }[]
  /** What they made together that you haven't seen, with the members of a bigger team who didn't work on it. */
  more: { id: number; title: string; image_url: string | null; mal_score: number | null; type: string | null; year: number | null; without: string[] }[]
}
/** How far apart your anime are: the islands, the two series furthest apart and the series at the centre. */
export interface TourDistance {
  islands: { shows: { id: number; title: string; image_url: string | null }[]; makers: { id: string; label: string; name: string }[] }[]
  main: { anime: number; series: number }
  unlinked: number
  /** The chain between the far ends, alternating anime and the people or studios that link them. */
  far: { steps: number; chain: ({ anime: { id: number; title: string; image_url: string | null } } | { maker: { id: string; label: string; name: string } })[] } | null
  radius: number
  center: { id: number; title: string; image_url: string | null }[]
  spread: { steps: number; series: number }[]
}
type TourCover = { id: number; title: string; image_url: string | null; note?: string }
/** The voice tour: the graph joined only by the Japanese voice actors of main characters. Notes are character names. */
export interface VoiceTour {
  anime: number
  voiced: number
  voices: number
  bridges: { id: string; label: string; name: string; series: number; count_rank: number; shows: TourCover[] }[]
  /** roles[i] is who the voice actor plays in shows[i]. */
  twins: { shows: TourCover[]; shared: { id: string; name: string; roles: string[] }[]; either: number; jaccard: number }[]
  duos: { people: { id: string; name: string }[]; series: number; shows: TourCover[] }[]
  distance: TourDistance
  queries: { bridges: string; twins: string; duos: string; islands: string }
}
export type VoiceStep = 'bridges' | 'twins' | 'duos' | 'distance'
export interface Tour {
  anime: number
  clustered: number
  makers: number
  clusters: TourCluster[]
  bridges: TourBridge[]
  cuts: TourCut[]
  threads: TourThread[]
  twins: TourTwins[]
  recs: TourRec[]
  teams: TourTeam[]
  distance: TourDistance
  queries: { clusters: string; bridges: string; cuts: string; twins: string; recs: string; teams: string; team_more: string; islands: string }
}
export const tourApi = {
  get: () => req<Tour>('/api/tour'),
  cluster: (index: number) => req<GraphPayload>(`/api/tour/cluster/${index}`),
  bridge: (ref: string) => req<GraphPayload>(`/api/tour/bridge/${encodeURIComponent(ref)}`),
  twins: (index: number) => req<GraphPayload>(`/api/tour/twins/${index}`),
  rec: (index: number) => req<GraphPayload>(`/api/tour/recs/${index}`),
  team: (index: number) => req<GraphPayload>(`/api/tour/teams/${index}`),
  /** 0 is the chain between the far ends, and 1 onwards are the islands. */
  distance: (index: number) => req<GraphPayload>(`/api/tour/distance/${index}`),
  voices: () => req<VoiceTour>('/api/tour/voices'),
  voice: (step: VoiceStep, index: number) => req<GraphPayload>(`/api/tour/voices/${step}/${index}`),
}

/** Yay or Nay: what a player's yays or nays have in common, against their overall yay rate. */
export interface YayPattern {
  kind: 'voice' | 'studio' | 'genre' | 'series'
  label: string
  yay: number
  total: number
}
export interface YayPatterns {
  votes: number
  yay: number
  need: number // votes still needed before patterns show
  likes: YayPattern[]
  dislikes: YayPattern[]
}
export interface YayDaily {
  date: string
  cards: KmkCard[]
  votes: Record<string, number> // character id -> 1 for yay, 0 for nay
  done: boolean
  results?: Record<string, { players: number; yay: number }> // once done
  patterns?: YayPatterns // once done
}
export const yayApi = {
  daily: () => req<YayDaily>('/api/yay/daily'),
  voteDaily: (character: number, yay: boolean) => req<YayDaily>('/api/yay/daily', post({ character, yay })),
  mine: () => req<{ cards: KmkCard[]; patterns: YayPatterns }>('/api/yay/mine'),
  voteMine: (character: number, yay: boolean) => req<{ patterns: YayPatterns }>('/api/yay/mine', post({ character, yay })),
}

export const mysteryApi = {
  daily: () => req<Mystery>('/api/mystery/daily'),
  move: (action: 'clue' | 'guess' | 'give_up', guess?: number) => req<Mystery>('/api/mystery/daily', post({ action, guess })),
  mine: () => req<Mystery>('/api/mystery/mine'),
  moveMine: (token: string, action: 'clue' | 'guess' | 'give_up', guess?: number) => req<Mystery>('/api/mystery/mine', post({ token, action, guess })),
}

export const kmkDailyApi = {
  get: () => req<KmkDaily>('/api/kmk/daily'),
  play: (choices: Record<string, KmkChoice>) => req<KmkDaily>('/api/kmk/daily', post({ choices })),
}

/** A character in one of your collections, with how many rounds put them there. */
export type ShelfCard = KmkCard & { count: number }
export interface KmkHistory {
  rounds: number
  harem: ShelfCard[]
  hookups: ShelfCard[]
  graveyard: ShelfCard[]
  terrarium: ShelfCard[]
}
export const kmkHistoryApi = {
  record: (title: string, choices: Record<string, KmkChoice>) => req<{ round_id: string }>('/api/kmk/rounds', post({ title, choices })),
  rescue: (roundId: string) => req<{ rescued: number }>(`/api/kmk/rounds/${roundId}/rescue`, post({})),
  history: () => req<KmkHistory>('/api/kmk/history'),
}

/** An anime named in a taste match, with each person's score (the average over a series' seasons). */
export interface MatchAnime {
  id: number
  title: string
  url: string | null
  image: string | null
  members: number | null
  you: number | null
  them: number | null
}
export type MakerKind = 'studio' | 'director' | 'writer' | 'voice' | 'genre'
export interface MatchMaker {
  kind: MakerKind
  name: string
  you: number // points above your own average, on average, for their series
  them: number
}
/** Something to watch, with what makes it likely to suit the person it's for. */
export interface MatchPick {
  id: number
  title: string
  url: string | null
  image: string | null
  members: number | null
  score?: number // what the person recommending it gave it
  planned?: boolean // already on the plan to watch of the person it's for
  because: { kind: MakerKind; name: string } | null
}
export interface Match {
  them: string
  match: number // 0 to 100
  parts: { agreement: number | null; makers: number | null; overlap: number } // null when there's too little to compare
  weights: { agreement: number; makers: number; overlap: number } // percent of the match
  counts: { shared: number; scored: number; only_you: number; only_them: number; rare: number; planned: number }
  means: { you: number; them: number }
  loved: MatchAnime[]
  split: MatchAnime[]
  rare: MatchAnime[]
  makers: MatchMaker[]
  for_you: MatchPick[]
  for_them: MatchPick[]
  together: MatchPick[]
}
export interface MatchLink {
  username: string
  since: number
  match: number
  shared: number
}
export interface MatchInvite {
  token: string
  expires: number
}

/** A request that answers 204 No Content. */
async function send(path: string, init: RequestInit): Promise<void> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`)
}

export const matchApi = {
  overview: () => req<{ links: MatchLink[]; invite: MatchInvite | null; invite_days: number }>('/api/match'),
  invite: () => req<MatchInvite>('/api/match/invite', { method: 'POST' }),
  cancelInvite: () => send('/api/match/invite', { method: 'DELETE' }),
  seeInvite: (token: string) => req<{ from: string; own: boolean; linked: boolean }>(`/api/match/invite/${encodeURIComponent(token)}`),
  accept: (token: string) => req<{ username: string }>(`/api/match/invite/${encodeURIComponent(token)}`, { method: 'POST' }),
  compare: (username: string) => req<Match>(`/api/match/with/${encodeURIComponent(username)}`),
  unlink: (username: string) => send(`/api/match/with/${encodeURIComponent(username)}`, { method: 'DELETE' }),
}

// The viewer's choice of anime titles lives in a cookie, so the server can name anime in every response. The page
// reloads on a change, since titles are already in the graph and pages on screen.
export function englishTitles(): boolean {
  return /(?:^|;\s*)titles=english(?:;|$)/.test(document.cookie)
}

export function setEnglishTitles(english: boolean): void {
  document.cookie = `titles=${english ? 'english' : 'romaji'}; path=/; max-age=31536000; SameSite=Lax`
  location.reload()
}
