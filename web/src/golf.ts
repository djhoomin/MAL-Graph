// Graph Golf: get from the tee to the hole in as few moves as you can. One move is one step along a voice role,
// character, staff credit, related anime or studio. The game drives the main canvas while it runs and puts back
// whatever was on it when the player leaves.
import { create } from 'zustand'
import { errorText, golfApi, type DailyResponse, type GEdge, type GNode, type GolfHole, type GolfResult } from './api'
import { useStore } from './store'

export interface GolfOption {
  node: GNode
  edge: GEdge
}

interface Golf {
  mode: 'daily' | 'practice'
  hole: GolfHole
  moves: string[] // positions from the tee, backtracks included
  trailNodes: Record<string, GNode>
  trailEdges: GEdge[] // the edge used for each move
  options: GolfOption[] // every move from the current position
  mulligans: number // used this hole (one allowed)
  loading: boolean
  note: string | null
  result: (GolfResult & { par: number }) | null
}

interface GolfStore {
  golf: Golf | null
  starting: boolean
  startError: string | null
  stash: { nodes: Record<string, GNode>; edges: Record<string, GEdge> } | null
  start: (mode: 'daily' | 'practice') => Promise<void>
  move: (id: string) => Promise<void>
  mulligan: () => Promise<void>
  giveUp: () => Promise<void>
  exit: () => void
}

export const MAX_STROKES = 60
const CANVAS_OPTIONS = 150 // more than this and the canvas gets unreadable; the panel lists every move
const KEY_STAFF = ['Director', 'Original Creator', 'Series Composition', 'Music', 'Character Design']

/** Lower sorts first: the moves people are most likely to want. */
function priority(o: GolfOption): number {
  const p = o.edge.props
  switch (o.edge.type) {
    case 'RELATED_TO':
      return 0
    case 'PRODUCED_BY':
      return 1
    case 'HAS_CHARACTER':
      return p.role === 'Main' ? 2 : 4
    case 'VOICES':
      return 3
    case 'WORKED_ON':
      return Array.isArray(p.positions) && p.positions.some((x) => KEY_STAFF.includes(String(x))) ? 5 : 6
    default:
      return 7
  }
}

export function sortOptions(options: GolfOption[]): GolfOption[] {
  return [...options].sort((a, b) => priority(a) - priority(b) || a.node.name.localeCompare(b.node.name))
}

const current = (g: Golf) => g.moves[g.moves.length - 1]
export const strokes = (g: Golf) => g.moves.length - 1

export function scoreName(strokes: number, par: number): string {
  if (strokes === 1) return 'Hole in one'
  const d = strokes - par
  return ({ [-3]: 'Albatross', [-2]: 'Eagle', [-1]: 'Birdie', 0: 'Par', 1: 'Bogey', 2: 'Double bogey', 3: 'Triple bogey' } as Record<number, string>)[d] ?? (d < 0 ? `${d}` : `+${d}`)
}

/** Put the round on the canvas: the trail, the tee and hole, and the moves from where the player stands. */
function render(g: Golf) {
  const nodes: Record<string, GNode> = { ...g.trailNodes, [g.hole.start.id]: g.hole.start, [g.hole.end.id]: g.hole.end }
  const edges: Record<string, GEdge> = {}
  for (const e of g.trailEdges) edges[e.id] = e
  if (g.result) {
    for (const n of g.result.solution.nodes) nodes[n.id] = n
    for (const e of g.result.solution.edges) edges[e.id] = e
  } else {
    const shown = sortOptions(g.options).slice(0, CANVAS_OPTIONS)
    const hole = g.options.find((o) => o.node.id === g.hole.end.id)
    if (hole && !shown.includes(hole)) shown.push(hole)
    for (const o of shown) {
      nodes[o.node.id] = nodes[o.node.id] ?? o.node
      edges[o.edge.id] = o.edge
    }
  }
  useStore.setState({ nodes, edges, selected: null, highlight: new Set(), pathFrom: g.hole.start.id, pathTo: g.hole.end.id, pathResult: null, pathPicking: false })
}

async function loadOptions(ref: string): Promise<GolfOption[]> {
  const p = await golfApi.moves(ref)
  const byId = Object.fromEntries(p.nodes.map((n) => [n.id, n]))
  const seen = new Map<string, GolfOption>()
  for (const e of p.edges) {
    const other = e.source === ref ? e.target : e.target === ref ? e.source : null
    if (!other || other === ref || !byId[other]) continue
    const o = { node: byId[other], edge: e }
    const prev = seen.get(other)
    if (!prev || priority(o) < priority(prev)) seen.set(other, o)
  }
  return [...seen.values()]
}

export const useGolf = create<GolfStore>((set, get) => {
  const update = (patch: Partial<Golf>) => {
    const g = get().golf
    if (!g) return
    const next = { ...g, ...patch }
    set({ golf: next })
    render(next)
  }

  const finish = async (gaveUp: boolean) => {
    const g = get().golf
    if (!g) return
    update({ loading: true, note: null })
    try {
      const r =
        g.mode === 'daily'
          ? await golfApi.finishDaily(g.moves, g.mulligans, gaveUp)
          : { ...(await golfApi.finishPractice(g.hole.start.id, g.hole.end.id, g.moves, g.mulligans, gaveUp)), par: g.hole.par }
      const round = r.round ?? { strokes: strokes(g), mulligans: g.mulligans, gave_up: gaveUp, moves: g.moves }
      update({ loading: false, result: { ...r, round, par: g.hole.par } })
    } catch (e) {
      update({ loading: false, note: errorText(e) })
    }
  }

  return {
    golf: null,
    starting: false,
    startError: null,
    stash: null,

    start: async (mode) => {
      const s = useStore.getState()
      if (!get().stash) set({ stash: { nodes: s.nodes, edges: s.edges } })
      set({ starting: true, startError: null })
      useStore.setState({ askOpen: false })
      try {
        const hole: DailyResponse = mode === 'daily' ? await golfApi.daily() : await golfApi.practice()
        const base: Golf = { mode, hole, moves: [hole.start.id], trailNodes: {}, trailEdges: [], options: [], mulligans: 0, loading: false, note: null, result: null }
        // Already played today: go straight to the result.
        if (hole.round && hole.solution) {
          const g: Golf = { ...base, moves: hole.round.moves, mulligans: hole.round.mulligans, result: { round: hole.round, shortest: hole.shortest ?? null, summary: hole.summary, solution: hole.solution, par: hole.par } }
          set({ golf: g, starting: false })
          render(g)
          return
        }
        const options = await loadOptions(hole.start.id)
        const g = { ...base, options }
        set({ golf: g, starting: false })
        render(g)
      } catch (e) {
        set({ starting: false, startError: errorText(e) })
      }
    },

    move: async (id) => {
      const g = get().golf
      if (!g || g.result || g.loading || id === current(g)) return
      const option = g.options.find((o) => o.node.id === id)
      if (!option) {
        const here = g.trailNodes[current(g)] ?? g.hole.start
        update({ note: `That isn't one move from ${here.name}.` })
        return
      }
      const moved: Golf = {
        ...g,
        moves: [...g.moves, id],
        trailNodes: { ...g.trailNodes, [id]: option.node, [g.hole.start.id]: g.hole.start },
        trailEdges: [...g.trailEdges, option.edge],
        note: null,
      }
      set({ golf: moved })
      if (id === g.hole.end.id) return finish(false)
      if (strokes(moved) >= MAX_STROKES) return finish(true)
      update({ loading: true })
      try {
        update({ options: await loadOptions(id), loading: false })
      } catch (e) {
        update({ loading: false, note: errorText(e) })
      }
    },

    mulligan: async () => {
      const g = get().golf
      if (!g || g.result || g.loading || g.mulligans > 0 || g.moves.length < 2) return
      const moves = g.moves.slice(0, -1)
      const trailEdges = g.trailEdges.slice(0, -1)
      const keep = new Set(moves)
      const trailNodes = Object.fromEntries(Object.entries(g.trailNodes).filter(([k]) => keep.has(k)))
      set({ golf: { ...g, moves, trailEdges, trailNodes, mulligans: 1, loading: true, note: null } })
      try {
        update({ options: await loadOptions(moves[moves.length - 1]), loading: false })
      } catch (e) {
        update({ loading: false, note: errorText(e) })
      }
    },

    giveUp: () => finish(true),

    exit: () => {
      const stash = get().stash
      set({ golf: null, stash: null, startError: null })
      useStore.setState({ nodes: stash?.nodes ?? {}, edges: stash?.edges ?? {}, selected: null, pathFrom: null, pathTo: null, highlight: new Set() })
    },
  }
})

/** Canvas marks for the current round: trail, where the player stands, and the shortest route once finished. */
export function golfMarks(g: Golf | null): { trail: Set<string>; current: string | null; solution: Set<string> } {
  if (!g) return { trail: new Set(), current: null, solution: new Set() }
  const trail = new Set<string>([...g.moves, ...g.trailEdges.map((e) => e.id)])
  const solution = new Set<string>(g.result ? [...g.result.solution.nodes.map((n) => n.id), ...g.result.solution.edges.map((e) => e.id)] : [])
  return { trail, current: g.result ? null : current(g), solution }
}
