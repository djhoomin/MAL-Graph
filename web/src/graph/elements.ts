import type { ElementDefinition } from 'cytoscape'
import type { GEdge, GNode } from '../api'
import { LABEL_COLORS, REL_COLORS } from './style'

export function nodeElement(n: GNode): ElementDefinition {
  return {
    group: 'nodes',
    data: {
      id: n.id,
      name: n.name,
      label: n.label,
      color: LABEL_COLORS[n.label],
      image: n.image_url ?? undefined,
      watched: n.watched ?? false,
      status: n.label === 'Anime' ? n.list_status ?? 'none' : null,
      stub: !n.fetched,
    },
  }
}

function edgeLabel(e: GEdge): string {
  const p = e.props
  switch (e.type) {
    case 'RELATED_TO':
      return String(p.relation ?? 'related')
    case 'HAS_CHARACTER':
      return String(p.role ?? '')
    case 'VOICES':
      return `voices (${p.language ?? '?'})`
    case 'WORKED_ON':
      return Array.isArray(p.positions) ? p.positions.slice(0, 2).join(', ') : 'staff'
    case 'LISTED':
      return String(p.status ?? 'listed')
    default:
      return e.type.toLowerCase().replace('_', ' ')
  }
}

export function edgeElement(e: GEdge): ElementDefinition {
  return {
    group: 'edges',
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
      color: REL_COLORS[e.type],
      labelText: edgeLabel(e),
      language: e.props.language ?? null,
    },
  }
}
