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
  sync: () => req<{ synced: number; unfetched: number; expanding: boolean }>('/api/sync', { method: 'POST' }),
  syncStatus: () => req<SyncStatus>('/api/sync/status'),
  stats: () => req<Record<string, number>>('/api/stats'),
}
