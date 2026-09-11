import { useEffect, useState } from 'react'
import { api, type NodeDetail } from '../api'
import { useStore } from '../store'
import { LABEL_COLORS, REL_LABELS } from '../graph/style'

const SHOWN_PROPS = ['title_english', 'title_japanese', 'type', 'episodes', 'year', 'season', 'status', 'score', 'rank', 'popularity', 'members', 'rating', 'source', 'studio', 'list_status', 'my_score', 'given_name', 'family_name', 'birthday', 'favorites', 'name_kanji', 'kind']

export function NodePanel() {
  const selected = useStore((s) => s.selected)
  const node = useStore((s) => (s.selected ? s.nodes[s.selected] : undefined))
  const { loadNeighbors, fetchFromMal, setPathEnd, setView, removeNode, collapseNode } = useStore.getState()
  const [detail, setDetail] = useState<NodeDetail | null>(null)

  useEffect(() => {
    setDetail(null)
    if (!selected) return
    let live = true
    api.node(selected).then((d) => live && setDetail(d)).catch(() => {})
    return () => {
      live = false
    }
  }, [selected, node?.fetched])

  if (!selected || !node) return <div className="panel muted">Select a node to see details.</div>
  const props = detail?.node.props ?? node.props
  const expandable = node.label === 'Anime' || node.label === 'Person' || node.label === 'Character'
  const about = (props.synopsis ?? props.about) as string | undefined

  return (
    <div className="panel">
      <div className="node-head">
        {node.image_url && <img src={node.image_url} alt="" />}
        <div>
          <div className="tag" style={{ background: LABEL_COLORS[node.label] }}>
            {node.label}
          </div>
          <h2>{node.name}</h2>
          {node.watched && <div className="watched">✓ {node.list_status} {props.my_score ? `· my score ${String(props.my_score)}` : ''}</div>}
          {!node.fetched && expandable && <div className="stub">stub — not yet fetched from MAL</div>}
          {typeof props.url === 'string' && (
            <a href={props.url} target="_blank" rel="noreferrer">
              open on MAL ↗
            </a>
          )}
        </div>
      </div>

      <div className="actions">
        <button onClick={() => void loadNeighbors(node.id)}>Expand neighbours</button>
        <button onClick={() => collapseNode(node.id)} title="Remove neighbours that aren't connected to anything else">
          Collapse
        </button>
        {expandable && <button onClick={() => void fetchFromMal(node.id)}>{node.fetched ? 'Refetch from MAL' : 'Fetch from MAL'}</button>}
        {node.label === 'Person' && <button onClick={() => setView('va')}>Voice roles</button>}
        <button onClick={() => setPathEnd('from', node.id)}>Path start</button>
        <button onClick={() => setPathEnd('to', node.id)}>Path end</button>
        <button onClick={() => removeNode(node.id)}>Remove</button>
      </div>

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
    </div>
  )
}
