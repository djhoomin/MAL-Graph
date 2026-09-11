import type { Label, ListStatus, RelType } from '../api'
import type { StylesheetJson } from 'cytoscape'

export const LABEL_COLORS: Record<Label, string> = {
  Anime: '#4f8cff',
  Character: '#ff8a4f',
  Person: '#c85cff',
  Studio: '#26c6a2',
  Genre: '#8d99ae',
  User: '#ffd166',
}
export const REL_COLORS: Record<RelType, string> = {
  LISTED: '#ffd166',
  HAS_CHARACTER: '#ff8a4f',
  VOICES: '#c85cff',
  WORKED_ON: '#7f5af0',
  RELATED_TO: '#4f8cff',
  PRODUCED_BY: '#26c6a2',
  HAS_GENRE: '#8d99ae',
}
export const STATUS_COLORS: Record<ListStatus, string> = {
  completed: '#3ddc84',
  watching: '#4f8cff',
  on_hold: '#ffd166',
  plan_to_watch: '#8d99ae',
  dropped: '#ff4f6a',
  none: '#5c6270',
}
export const REL_LABELS: Record<RelType, string> = {
  LISTED: 'on my list',
  HAS_CHARACTER: 'has character',
  VOICES: 'voices',
  WORKED_ON: 'worked on',
  RELATED_TO: 'related',
  PRODUCED_BY: 'produced by',
  HAS_GENRE: 'genre',
}

export const stylesheet: StylesheetJson = [
  {
    selector: 'node',
    style: {
      label: 'data(name)',
      'font-size': 9,
      color: '#e6e6e6',
      'text-outline-color': '#0f1117',
      'text-outline-width': 2,
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-max-width': '110px',
      'text-wrap': 'ellipsis',
      width: 28,
      height: 28,
      'background-color': 'data(color)',
      'border-width': 2,
      'border-color': 'data(color)',
      'background-fit': 'cover',
      'background-image-opacity': 1,
    },
  },
  { selector: 'node[image]', style: { 'background-image': 'data(image)' } },
  { selector: 'node[label = "Anime"]', style: { shape: 'round-rectangle', width: 36, height: 48 } },
  { selector: 'node[label = "Studio"], node[label = "Genre"]', style: { shape: 'diamond', width: 24, height: 24 } },
  { selector: 'node[label = "User"]', style: { shape: 'star', width: 40, height: 40 } },
  // ring colour = my list status (matches the status chips in the sidebar)
  { selector: 'node[status = "completed"]', style: { 'border-color': STATUS_COLORS.completed, 'border-width': 4 } },
  { selector: 'node[status = "watching"]', style: { 'border-color': STATUS_COLORS.watching, 'border-width': 4 } },
  { selector: 'node[status = "on_hold"]', style: { 'border-color': STATUS_COLORS.on_hold, 'border-width': 4 } },
  { selector: 'node[status = "dropped"]', style: { 'border-color': STATUS_COLORS.dropped, 'border-width': 4 } },
  { selector: 'node[status = "plan_to_watch"]', style: { 'border-color': STATUS_COLORS.plan_to_watch, 'border-width': 4 } },
  { selector: 'node[?stub]', style: { 'border-style': 'dashed', opacity: 0.75 } },
  { selector: 'node:selected', style: { 'border-color': '#ffffff', 'border-width': 4, 'z-index': 10 } },
  { selector: 'node.pathFrom', style: { 'border-color': '#3ddc84', 'border-width': 5 } },
  { selector: 'node.pathTo', style: { 'border-color': '#ff4f6a', 'border-width': 5 } },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': 'data(color)',
      'curve-style': 'bezier',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': 'data(color)',
      'arrow-scale': 0.6,
      opacity: 0.6,
      label: 'data(labelText)',
      'font-size': 7,
      color: '#c9c9c9',
      'text-outline-color': '#0f1117',
      'text-outline-width': 2,
      'text-rotation': 'autorotate',
      'text-opacity': 0,
    },
  },
  { selector: 'edge:selected, edge.path', style: { 'text-opacity': 1, opacity: 1, width: 3 } },
  { selector: '.path', style: { 'z-index': 20 } },
  { selector: 'node.path', style: { 'border-color': '#ffffff', 'border-width': 4 } },
  { selector: '.faded', style: { opacity: 0.15, 'text-opacity': 0 } },
  // selected node's neighbourhood
  { selector: '.dim', style: { opacity: 0.2, 'text-opacity': 0.15 } },
  { selector: 'node.nbr', style: { 'border-color': '#ffffff', 'border-width': 3, 'z-index': 15 } },
  { selector: 'edge.nbr', style: { opacity: 1, width: 3, 'text-opacity': 1, 'z-index': 15 } },
  { selector: '.hidden', style: { display: 'none' } },
]
