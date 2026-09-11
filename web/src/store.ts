import { create } from 'zustand'
import { api, LABELS, LIST_STATUSES, REL_TYPES, type GEdge, type GNode, type GraphPayload, type Label, type ListStatus, type RelType, type UserSummary } from './api'

export interface Filters {
  labels: Record<Label, boolean>
  rels: Record<RelType, boolean>
  statuses: Record<ListStatus, boolean> // visibility of Anime nodes by my list status
  lang: string | null // null = all languages
  onlyWatched: boolean
  highlightNeighbors: boolean // dim everything except the selected node's neighbourhood
  expandOnClick: boolean // single click also expands (fetching from MAL first if the node is a stub)
}

interface State {
  nodes: Record<string, GNode>
  edges: Record<string, GEdge>
  selected: string | null
  pathFrom: string | null
  pathTo: string | null
  highlight: Set<string> // node + edge ids of the current path result
  filters: Filters
  user: UserSummary | null
  busy: string | null
  error: string | null
  view: 'node' | 'va'
  layoutTick: number

  mergePayload: (p: GraphPayload, opts?: { select?: string }) => void
  removeNode: (id: string) => void
  collapseNode: (id: string) => number
  clear: () => void
  select: (id: string | null) => void
  setPathEnd: (end: 'from' | 'to', id: string | null) => void
  setHighlight: (ids: Iterable<string>) => void
  setFilter: (patch: Partial<Filters>) => void
  toggleLabel: (l: Label) => void
  toggleRel: (r: RelType) => void
  toggleStatus: (st: ListStatus) => void
  setView: (v: 'node' | 'va') => void
  relayout: () => void
  loadNeighbors: (id: string) => Promise<void>
  fetchFromMal: (id: string) => Promise<void>
  /** Fetch from MAL if the node is still a stub, then load its neighbours. */
  expandNode: (id: string) => Promise<void>
  refreshUser: () => Promise<void>
  run: <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>
}

const allTrue = <K extends string>(keys: readonly K[]) => Object.fromEntries(keys.map((k) => [k, true])) as Record<K, boolean>

export const useStore = create<State>((set, get) => ({
  nodes: {},
  edges: {},
  selected: null,
  pathFrom: null,
  pathTo: null,
  highlight: new Set(),
  filters: { labels: { ...allTrue(LABELS), Genre: false, User: false }, rels: { ...allTrue(REL_TYPES), WORKED_ON: false, HAS_GENRE: false }, statuses: allTrue(LIST_STATUSES), lang: 'Japanese', onlyWatched: false, highlightNeighbors: true, expandOnClick: false },
  user: null,
  busy: null,
  error: null,
  view: 'node',
  layoutTick: 0,

  mergePayload: (p, opts) =>
    set((s) => {
      const nodes = { ...s.nodes }
      const edges = { ...s.edges }
      for (const n of p.nodes) nodes[n.id] = { ...nodes[n.id], ...n }
      for (const e of p.edges) edges[e.id] = e
      return { nodes, edges, selected: opts?.select ?? s.selected }
    }),
  removeNode: (id) =>
    set((s) => {
      const nodes = { ...s.nodes }
      delete nodes[id]
      const edges = Object.fromEntries(Object.entries(s.edges).filter(([, e]) => e.source !== id && e.target !== id))
      return { nodes, edges, selected: s.selected === id ? null : s.selected }
    }),
  // Remove neighbours of `id` that are connected to nothing else on the canvas (leaf nodes),
  // so anything reachable another way — e.g. a path you've built — survives.
  collapseNode: (id) => {
    const s = get()
    const degree: Record<string, number> = {}
    for (const e of Object.values(s.edges)) {
      degree[e.source] = (degree[e.source] ?? 0) + 1
      degree[e.target] = (degree[e.target] ?? 0) + 1
    }
    const leaves = new Set<string>()
    for (const e of Object.values(s.edges)) {
      const other = e.source === id ? e.target : e.target === id ? e.source : null
      if (other && other !== id && degree[other] === 1 && other !== s.pathFrom && other !== s.pathTo) leaves.add(other)
    }
    if (leaves.size === 0) return 0
    const nodes = Object.fromEntries(Object.entries(s.nodes).filter(([k]) => !leaves.has(k)))
    const edges = Object.fromEntries(Object.entries(s.edges).filter(([, e]) => !leaves.has(e.source) && !leaves.has(e.target)))
    set({ nodes, edges, selected: s.selected && leaves.has(s.selected) ? id : s.selected })
    return leaves.size
  },
  clear: () => set({ nodes: {}, edges: {}, selected: null, highlight: new Set(), pathFrom: null, pathTo: null }),
  select: (id) => set({ selected: id, view: 'node' }),
  setPathEnd: (end, id) => set(end === 'from' ? { pathFrom: id } : { pathTo: id }),
  setHighlight: (ids) => set({ highlight: new Set(ids) }),
  setFilter: (patch) => set((s) => ({ filters: { ...s.filters, ...patch } })),
  toggleLabel: (l) => set((s) => ({ filters: { ...s.filters, labels: { ...s.filters.labels, [l]: !s.filters.labels[l] } } })),
  toggleRel: (r) => set((s) => ({ filters: { ...s.filters, rels: { ...s.filters.rels, [r]: !s.filters.rels[r] } } })),
  toggleStatus: (st) => set((s) => ({ filters: { ...s.filters, statuses: { ...s.filters.statuses, [st]: !s.filters.statuses[st] } } })),
  setView: (view) => set({ view }),
  relayout: () => set((s) => ({ layoutTick: s.layoutTick + 1 })),

  run: async (label, fn) => {
    set({ busy: label, error: null })
    try {
      return await fn()
    } catch (e) {
      set({ error: (e as Error).message })
      return undefined
    } finally {
      set({ busy: null })
    }
  },

  loadNeighbors: async (id) => {
    const { filters, run, mergePayload } = get()
    const rels = REL_TYPES.filter((r) => filters.rels[r])
    await run(`Loading neighbours of ${id}`, async () => {
      const p = await api.neighbors(id, { only_watched: filters.onlyWatched, lang: filters.lang, rels, limit: 400 })
      mergePayload(p)
    })
  },

  fetchFromMal: async (id) => {
    const { filters, run, mergePayload, refreshUser } = get()
    await run(`Fetching ${id} from MAL via Jikan…`, async () => {
      const p = await api.expand(id, { only_watched: filters.onlyWatched, lang: filters.lang })
      mergePayload(p)
      await refreshUser()
    })
  },

  expandNode: async (id) => {
    const { nodes, fetchFromMal, loadNeighbors } = get()
    const n = nodes[id]
    const expandable = n && (n.label === 'Anime' || n.label === 'Person' || n.label === 'Character')
    if (expandable && !n.fetched) await fetchFromMal(id)
    else await loadNeighbors(id)
  },

  refreshUser: async () => {
    try {
      set({ user: await api.user() })
    } catch {
      /* API down: leave stale */
    }
  },
}))
