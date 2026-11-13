import { useEffect, useRef, useState } from 'react'
import { api, type NodeDetail } from '../api'
import { useStore } from '../store'
import { GenderFix } from './Gender'
import { navigate } from '../useHashRoute'
import { LABEL_COLORS, REL_LABELS } from '../graph/style'
import { CloseIcon, MoreIcon } from './icons'
import { useDismiss } from './useDismiss'
import { VaView } from './VaView'

const SHOWN_PROPS = ['title_english', 'title_japanese', 'type', 'episodes', 'year', 'season', 'status', 'score', 'rank', 'popularity', 'members', 'rating', 'source', 'studio', 'list_status', 'my_score', 'given_name', 'family_name', 'birthday', 'favorites', 'name_kanji', 'kind']

export function NodeCard() {
  const view = useStore((s) => s.view)
  return <div className="node-card float-panel">{view === 'va' ? <VaView /> : <NodeSummary />}</div>
}

function NodeSummary() {
  const node = useStore((s) => (s.selected ? s.nodes[s.selected] : undefined))
  const pathPicking = useStore((s) => s.pathPicking)
  const pathFrom = useStore((s) => s.pathFrom)
  const { expandNode, fetchFromMal, startPath, setView, removeNode, collapseNode, select } = useStore.getState()
  // Remembered across selections so the card keeps the shape you left it in.
  const open = useStore((s) => s.cardDetailsOpen)
  const [loaded, setLoaded] = useState<NodeDetail | null>(null)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  useDismiss(moreRef, moreOpen, () => setMoreOpen(false))

  const nodeId = node?.id
  const fetched = node?.fetched
  // Only load the full record once Details is open.
  useEffect(() => {
    if (!open || !nodeId) return
    let live = true
    api.node(nodeId).then((d) => live && setLoaded(d)).catch(() => {})
    return () => {
      live = false
    }
  }, [open, nodeId, fetched])

  if (!node) return null
  const detail = loaded?.node.id === node.id ? loaded : null
  const props = detail?.node.props ?? node.props
  const expandable = node.label === 'Anime' || node.label === 'Person' || node.label === 'Character'
  const about = (props.synopsis ?? props.about) as string | undefined
  const statusLine = node.watched
    ? `✓ ${String(node.list_status ?? '').replace(/_/g, ' ')}${props.my_score ? ` · ${String(props.my_score)}/10` : ''}`
    : !node.fetched && expandable
      ? 'Not fetched from MAL yet'
      : null

  const menuItem = (text: string, fn: () => void) => (
    <button
      onClick={() => {
        fn()
        setMoreOpen(false)
      }}
    >
      {text}
    </button>
  )

  return (
    <>
      <div className="card-head">
        {node.image_url && <img src={node.image_url} alt="" />}
        <div className="card-title">
          <span className="tag" style={{ background: LABEL_COLORS[node.label] }}>
            {node.label}
          </span>
          <h2>{node.name}</h2>
          {statusLine && <div className={node.watched ? 'watched' : 'stub'}>{statusLine}</div>}
        </div>
        <button className="icon-btn ghost" onClick={() => select(null)} aria-label="Close">
          <CloseIcon />
        </button>
      </div>

      {/* The extra actions open in place: the card scrolls, so a floating list would be clipped by it. */}
      <div ref={moreRef}>
        <div className="card-actions">
          <button className="primary" onClick={() => void expandNode(node.id)}>
            Expand
          </button>
          <button className={pathPicking && pathFrom === node.id ? 'on' : ''} onClick={() => startPath(node.id)}>
            Path
          </button>
          <button className={`icon-btn ${moreOpen ? 'on' : ''}`} onClick={() => setMoreOpen((v) => !v)} aria-label="More actions" aria-expanded={moreOpen}>
            <MoreIcon />
          </button>
        </div>
        {moreOpen && (
          <div className="menu-list card-more">
            {node.label === 'Person' && menuItem('Voice roles', () => setView('va'))}
            {node.label === 'Person' && menuItem('Roster', () => navigate(`/roster/${node.mal_id}`))}
            {expandable && node.fetched && menuItem('Refetch from MAL', () => void fetchFromMal(node.id))}
            {menuItem('Collapse neighbours', () => collapseNode(node.id))}
            {typeof props.url === 'string' && menuItem('Open on MAL', () => window.open(props.url as string, '_blank', 'noreferrer'))}
            {menuItem('Remove from canvas', () => removeNode(node.id))}
            {node.label === 'Character' && (
              <div className="card-gender">
                <GenderFix node={node} onFixed={(gender) => useStore.getState().mergePayload({ nodes: [{ ...node, props: { ...node.props, gender } }], edges: [] })} />
              </div>
            )}
          </div>
        )}
      </div>

      <details
        className="card-details"
        open={open}
        onToggle={(e) => useStore.setState({ cardDetailsOpen: (e.target as HTMLDetailsElement).open })}
      >
        <summary>Details</summary>
        {detail && detail.degrees.length > 0 && (
          <div className="degrees">
            {detail.degrees.map((d) => (
              <span key={d.type + d.label} className="chip">
                {d.n} {REL_LABELS[d.type]} → {d.label}
              </span>
            ))}
          </div>
        )}
        <table className="props">
          <tbody>
            {SHOWN_PROPS.filter((k) => props[k] != null && props[k] !== '').map((k) => (
              <tr key={k}>
                <th>{k.replace('_', ' ')}</th>
                <td>{String(props[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {about && <p className="about">{about}</p>}
      </details>
    </>
  )
}
