import type { GEdge, GNode, ListStatus } from '../api'
import type { Filters } from '../store'

/** Whether the filters leave a node on the canvas. */
export const nodeShown = (n: GNode, f: Filters) => f.labels[n.label] && (n.label !== 'Anime' || f.statuses[(n.list_status ?? 'none') as ListStatus])

/** Whether they leave a connection on it, which also takes both of its ends. */
export function edgeShown(e: GEdge, nodes: Record<string, GNode>, f: Filters) {
  const a = nodes[e.source]
  const b = nodes[e.target]
  if (!a || !b || !nodeShown(a, f) || !nodeShown(b, f) || !f.rels[e.type]) return false
  return e.type !== 'VOICES' || !f.lang || e.props.language === f.lang
}
