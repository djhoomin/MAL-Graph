import { create } from 'zustand'
import { api, LABELS, LIST_STATUSES, REL_TYPES, type GEdge, type GNode, type GraphPayload, type Label, type ListStatus, type Me, type PathResult, type RelType, type SyncStatus, type UserSummary } from './api'

export interface Filters {
  labels: Record<Label, boolean>
  rels: Record<RelType, boolean>
  statuses: Record<ListStatus, boolean> // visibility of Anime nodes by my list status
  lang: string | null // null = all languages
  onlyWatched: boolean
  highlightNeighbors: boolean // dim everything except the selected node's neighbourhood
  expandOnClick: boolean // single click also expands (fetching from MAL first if the node is a stub)
}

export interface PathOpts {
  maxHops: number
  onlyWatched: boolean // only hop through anime I've seen
  via: { va: boolean; staff: boolean; related: boolean; studio: boolean; genre: boolean }
  allPaths: boolean
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
  view: 'node' | 'va' // what the node card shows
  askOpen: boolean
  cardDetailsOpen: boolean
  layoutTick: number
  fitTick: number
  /** Path mode: the next node picked (canvas tap or search) becomes the destination. */
  pathPicking: boolean
  pathOpts: PathOpts
  pathResult: PathResult | null
  sync: SyncStatus | null // background MAL expansion after a list sync
  syncMsg: string | null
  me: Me | null // who is signed in; null until the first /auth/me answers
  authError: string | null // from a failed sign-in redirect (?auth_error=...)

  mergePayload: (p: GraphPayload, opts?: { select?: string }) => void
  removeNode: (id: string) => void
  collapseNode: (id: string) => number
  clear: () => void
  select: (id: string | null) => void
  startPath: (fromId: string) => void
  completePath: (toId: string) => Promise<void>
  findPath: () => Promise<void>
  setPathOpts: (patch: Partial<PathOpts>) => void
  clearPath: () => void
  setFilter: (patch: Partial<Filters>) => void
  toggleLabel: (l: Label) => void
  toggleRel: (r: RelType) => void
  toggleStatus: (st: ListStatus) => void
  setView: (v: 'node' | 'va') => void
  setAskOpen: (open: boolean) => void
  relayout: () => void
  fit: () => void
  startSync: () => Promise<void>
  uploadList: (file: File) => Promise<void>
  /** Who is signed in, plus what a sign-in redirect left in the URL. */
  loadMe: () => Promise<void>
  signOut: () => Promise<void>
  pollSync: () => Promise<void>
  loadNeighbors: (id: string) => Promise<void>
  fetchFromMal: (id: string) => Promise<void>
  /** Fetch from MAL if the node is still a stub, then load its neighbours. */
  expandNode: (id: string) => Promise<void>
  refreshUser: () => Promise<void>
  run: <T>(label: string, fn: () => Promise<T>) => Promise<T | undefined>
}

const allTrue = <K extends string>(keys: readonly K[]) => Object.fromEntries(keys.map((k) => [k, true])) as Record<K, boolean>

export const DEFAULT_LABELS: Record<Label, boolean> = { ...allTrue(LABELS), Genre: false, User: false }
export const DEFAULT_RELS: Record<RelType, boolean> = { ...allTrue(REL_TYPES), WORKED_ON: false, HAS_GENRE: false }
export const DEFAULT_STATUSES: Record<ListStatus, boolean> = allTrue(LIST_STATUSES)
const sameFlags = <K extends string>(a: Record<K, boolean>, b: Record<K, boolean>) => (Object.keys(b) as K[]).every((k) => a[k] === b[k])
/** True when any type, list-status or relation chip differs from the default. */
export const chipFiltersChanged = (f: Filters) => !sameFlags(f.labels, DEFAULT_LABELS) || !sameFlags(f.rels, DEFAULT_RELS) || !sameFlags(f.statuses, DEFAULT_STATUSES)

// The simple toggles survive a reload; the chip filters reset so new labels/relations never go missing.
type Prefs = Pick<Filters, 'lang' | 'onlyWatched' | 'highlightNeighbors' | 'expandOnClick'>
const PREFS_KEY = 'malgraph.prefs'
const DEFAULT_PREFS: Prefs = { lang: 'Japanese', onlyWatched: false, highlightNeighbors: true, expandOnClick: true }
function loadPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') }
  } catch {
    return DEFAULT_PREFS
  }
}
function savePrefs(f: Filters) {
  try {
    const { lang, onlyWatched, highlightNeighbors, expandOnClick } = f
    localStorage.setItem(PREFS_KEY, JSON.stringify({ lang, onlyWatched, highlightNeighbors, expandOnClick }))
  } catch {
    /* private mode: prefs just won't stick */
  }
}

// A sign-in redirect lands on /?signed_in=1 or /?auth_error=...; read it once at startup and tidy the address bar.
// The pre-sign-in "remember this username" key isn't used any more.
try {
  localStorage.removeItem('malgraph.user')
} catch {
  /* storage blocked */
}

const signInRedirect = (() => {
  const params = new URLSearchParams(window.location.search)
  const out = { signedIn: params.has('signed_in'), authError: params.get('auth_error') }
  if (out.signedIn || out.authError) window.history.replaceState(null, '', window.location.pathname + window.location.hash)
  return out
})()

export const useStore = create<State>((set, get) => ({
  nodes: {},
  edges: {},
  selected: null,
  pathFrom: null,
  pathTo: null,
  highlight: new Set(),
  filters: { labels: DEFAULT_LABELS, rels: DEFAULT_RELS, statuses: DEFAULT_STATUSES, ...loadPrefs() },
  user: null,
  busy: null,
  error: null,
  view: 'node',
  askOpen: false,
  cardDetailsOpen: false,
  layoutTick: 0,
  fitTick: 0,
  pathPicking: false,
  pathOpts: { maxHops: 8, onlyWatched: false, via: { va: true, staff: true, related: true, studio: true, genre: false }, allPaths: false },
  pathResult: null,
  sync: null,
  syncMsg: null,
  me: null,
  authError: null,

  mergePayload: (p, opts) =>
    set((s) => {
      const nodes = { ...s.nodes }
      const edges = { ...s.edges }
      for (const n of p.nodes) nodes[n.id] = { ...nodes[n.id], ...n }
      for (const e of p.edges) edges[e.id] = e
      // While a path is highlighted everything else is faded, so what was just added joins the highlight and shows.
      const highlight = s.highlight.size ? new Set([...s.highlight, ...p.nodes.map((n) => n.id), ...p.edges.map((e) => e.id)]) : s.highlight
      return { nodes, edges, highlight, selected: opts?.select ?? s.selected }
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
  clear: () => set({ nodes: {}, edges: {}, selected: null, highlight: new Set(), pathFrom: null, pathTo: null, pathPicking: false, pathResult: null }),
  select: (id) => set({ selected: id, view: 'node' }),
  startPath: (fromId) => set({ pathFrom: fromId, pathTo: null, pathPicking: true, pathResult: null, highlight: new Set() }),
  completePath: async (toId) => {
    if (toId === get().pathFrom) return
    set({ pathTo: toId, pathPicking: false })
    await get().findPath()
  },
  findPath: async () => {
    const { pathFrom, pathTo, pathOpts: o, filters, run, mergePayload } = get()
    if (!pathFrom || !pathTo) return
    const exclude = ['User', ...(o.via.genre ? [] : ['Genre']), ...(o.via.studio ? [] : ['Studio'])].join(',')
    const rels = [
      ...(o.via.va ? ['VOICES', 'HAS_CHARACTER'] : []),
      ...(o.via.staff ? ['WORKED_ON'] : []),
      ...(o.via.related ? ['RELATED_TO'] : []),
      ...(o.via.studio ? ['PRODUCED_BY'] : []),
      ...(o.via.genre ? ['HAS_GENRE'] : []),
    ].join(',')
    if (!rels) return
    const r = await run('Finding path…', () =>
      api.path(pathFrom, pathTo, { max_hops: o.maxHops, only_watched: o.onlyWatched, exclude, rels, lang: filters.lang, all_paths: o.allPaths, limit: 10 }),
    )
    if (!r) return
    if (r.found) mergePayload(r)
    set({ pathResult: r, highlight: new Set(r.found ? [...r.nodes.map((n) => n.id), ...r.edges.map((e) => e.id)] : []) })
  },
  setPathOpts: (patch) => {
    set((s) => ({ pathOpts: { ...s.pathOpts, ...patch } }))
    void get().findPath()
  },
  clearPath: () => set({ pathFrom: null, pathTo: null, pathPicking: false, pathResult: null, highlight: new Set() }),
  setFilter: (patch) =>
    set((s) => {
      const filters = { ...s.filters, ...patch }
      savePrefs(filters)
      return { filters }
    }),
  toggleLabel: (l) => set((s) => ({ filters: { ...s.filters, labels: { ...s.filters.labels, [l]: !s.filters.labels[l] } } })),
  toggleRel: (r) => set((s) => ({ filters: { ...s.filters, rels: { ...s.filters.rels, [r]: !s.filters.rels[r] } } })),
  toggleStatus: (st) => set((s) => ({ filters: { ...s.filters, statuses: { ...s.filters.statuses, [st]: !s.filters.statuses[st] } } })),
  setView: (view) => set({ view }),
  setAskOpen: (askOpen) => set({ askOpen }),
  relayout: () => set((s) => ({ layoutTick: s.layoutTick + 1 })),
  fit: () => set((s) => ({ fitTick: s.fitTick + 1 })),

  startSync: async () => {
    const { run, refreshUser } = get()
    set({ syncMsg: null })
    const r = await run('Syncing your list…', api.sync)
    if (!r) return
    await refreshUser()
    // AniList anime that aren't on MyAnimeList can't join the graph yet.
    const skipped = r.skipped ? ` ${r.skipped} ${r.skipped === 1 ? "anime isn't" : "anime aren't"} on MyAnimeList, so ${r.skipped === 1 ? "it's" : "they're"} left out.` : ''
    if (r.expanding) {
      if (skipped) set({ syncMsg: skipped.trim() })
      set({ sync: { running: true, total: r.unfetched, done: 0, failed: [], current: null, others_in_queue: 0 } })
      void get().pollSync()
    } else set({ syncMsg: `List synced (${r.synced} entries). Nothing new to fetch.${skipped}` })
  },
  uploadList: async (file) => {
    const { run, refreshUser } = get()
    set({ syncMsg: null })
    const r = await run('Reading your export…', () => api.uploadList(file))
    if (!r) return
    await refreshUser()
    const msg = `List replaced with ${r.synced} entries from the export${r.exported_by ? ` of ${r.exported_by}` : ''}.`
    if (r.expanding) {
      set({ syncMsg: msg, sync: { running: true, total: r.unfetched, done: 0, failed: [], current: null, others_in_queue: 0 } })
      void get().pollSync()
    } else set({ syncMsg: msg })
  },
  loadMe: async () => {
    const { signedIn, authError } = signInRedirect
    try {
      const me = await api.me()
      set({ me, authError })
      // Signed in, but reading the list failed: the welcome card isn't shown, so say it in the toast.
      if (me.username && authError === 'list') set({ error: 'Your list could not be read. Try Sync list in the menu.' })
      // First thing after signing in: the user's own list on the canvas.
      if (signedIn && me.username && Object.keys(get().nodes).length === 0) void get().loadNeighbors(`User:${me.username}`)
    } catch {
      set({ me: { username: null, sign_in: false }, authError })
    }
  },
  signOut: async () => {
    await api.signOut()
    window.location.replace(window.location.pathname) // start over with a clean slate
  },
  pollSync: async () => {
    try {
      const st = await api.syncStatus()
      const wasRunning = get().sync?.running
      set({ sync: st.running ? st : null })
      if (wasRunning && !st.running) {
        await get().refreshUser()
        set({ syncMsg: st.failed.length ? `${st.failed.length} anime failed to fetch. Sync again to retry.` : `Fetched ${st.done} new anime.` })
      }
    } catch {
      /* keep the last known state */
    }
  },

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
