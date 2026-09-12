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
}
export interface UserSummary {
  username: string | null
  by_status: Record<string, number>
  total: number
  unfetched: number
}

// Dev talks to uvicorn on :8000; in production Caddy serves the UI and proxies /api on the same origin.
const BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

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
  if (!res.ok || !res.body) throw new Error(`${res.status}: ${res.statusText}`)
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
  search: (q: string, limit = 8) =>
    req<{ query: string; results: Partial<Record<Label, GNode[]>> }>(`/api/search${qs({ q, limit })}`),
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
  askStatus: () => req<{ configured: boolean; model: string | null }>('/api/ask/status'),
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
  sync: () => req<{ synced: number; unfetched: number; expanding: boolean }>('/api/sync', { method: 'POST' }),
  syncStatus: () => req<SyncStatus>('/api/sync/status'),
  stats: () => req<Record<string, number>>('/api/stats'),
}
