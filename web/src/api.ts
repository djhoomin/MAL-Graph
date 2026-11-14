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
  mal_id: number | null
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
  mal_id: number
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
  studios: { mal_id: number; name: string }[]
  genres: { mal_id: number; name: string; kind: string }[]
  follow_up?: boolean // a sequel or side story, which always has fewer members than what it follows
}
export interface RankedPerson {
  person: GNode
  anime_ids: number[]
  characters: number
  avg_my_score: number | null
}
export interface Gap {
  mal_id: number
  title: string
  image_url: string | null
  score: number | null
  type: string | null
  year: number | null
  fetched: boolean
  via: { relation: string; mal_id: number; title: string; my_score: number; status: ListStatus }[]
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
  failed: { mal_id: number; error: string }[]
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
export interface Me {
  username: string | null
  sign_in: boolean // false when the server has no MAL sign-in configured (local development)
  contact?: string | null // who runs the site, for the privacy page
}

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
export interface ConversationTurn {
  role: 'user' | 'assistant'
  text: string
  steps: { name: string; args: Record<string, unknown>; error?: string }[]
  cards: { title: string; cards: { node: GNode; caption: string }[] }[]
  usage?: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number } | null
  error?: string | null
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
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_error'; name: string; message: string }
  | { type: 'canvas'; payload: GraphPayload & { select?: string } }
  | { type: 'cards'; title: string; cards: { node: GNode; caption: string }[] }
  | { type: 'answer'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done'; usage: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number } }

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
  vaRoles: (malId: number, only_watched: boolean, lang: string | null) =>
    req<VaResult>(`/api/person/${malId}/characters${qs({ only_watched, lang })}`),
  roster: (o: { only_watched?: boolean; main_only?: boolean; lang?: string | null; min_characters?: number; q?: string; limit?: number }) =>
    req<{ people: RosterEntry[] }>(`/api/roster${qs(o)}`),
  user: () => req<UserSummary>('/api/user'),
  askStatus: () => req<AskStatus>('/api/ask/status'),
  conversations: () => req<{ conversations: ConversationSummary[] }>('/api/conversations'),
  conversation: (id: string) => req<Conversation>(`/api/conversations/${id}`),
  renameConversation: (id: string, title: string) =>
    req<{ id: string; title: string }>(`/api/conversations/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) }),
  deleteConversation: (id: string) => req<{ deleted: boolean }>(`/api/conversations/${id}`, { method: 'DELETE' }),
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
  sync: () => req<{ username: string; synced: number; unfetched: number; expanding: boolean }>('/api/sync', { method: 'POST' }),
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
  fixGender: (malId: number, gender: string | null) =>
    req<{ mal_id: number; gender: string | null }>(`/api/kmk/character/${malId}/gender`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ gender }) }),
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
  choices?: Record<string, KmkChoice> // by character mal_id, once played
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
  answer: number // mal_id of the odd one
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
  mal_id: number
  name: string
  series: number
}
export interface TourCluster {
  anime: number
  series: { mal_id: number; title: string; image_url: string | null; my_score: number }[]
  makers: TourMaker[]
  genres: string[]
}
export interface TourBridge extends TourMaker {
  rank: number
  count_rank: number // their place when ranked by how many of your series they're behind
  clusters: { cluster: number; mal_id: number; title: string; image_url: string | null }[]
}
/** A cut point: the person, studio or anime a cluster falls apart without, and the pieces it holds together. */
export interface TourCut {
  id: string
  label: 'Person' | 'Studio' | 'Anime'
  mal_id: number
  name: string
  image_url: string | null
  cluster: number
  sides: { series: number; anime: number; items: { mal_id: number; title: string; image_url: string | null }[] }[]
}
/** A single series that only connects to its cluster through one person, studio or anime. */
export interface TourThread {
  cluster: number
  show: { mal_id: number; title: string; image_url: string | null }
  via: { id: string; label: 'Person' | 'Studio' | 'Anime'; name: string }
  also: { mal_id: number; title: string; image_url: string | null }[] // what the person or studio made in the rest of the cluster
}
export interface Tour {
  anime: number
  clustered: number
  makers: number
  clusters: TourCluster[]
  bridges: TourBridge[]
  cuts: TourCut[]
  threads: TourThread[]
  queries: { clusters: string; bridges: string; cuts: string }
}
export const tourApi = {
  get: () => req<Tour>('/api/tour'),
  cluster: (index: number) => req<GraphPayload>(`/api/tour/cluster/${index}`),
  bridge: (ref: string) => req<GraphPayload>(`/api/tour/bridge/${encodeURIComponent(ref)}`),
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
