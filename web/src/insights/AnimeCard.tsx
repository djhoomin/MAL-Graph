import { LIST_STATUS_LABELS, type ListAnime } from '../api'
import { STATUS_COLORS } from '../graph/style'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

/** An anime from the list as a card that opens it on the graph. `note` adds a line, such as a score comparison. */
export function AnimeCard({ a, dim = false, note }: { a: ListAnime; dim?: boolean; note?: string }) {
  const mergePayload = useStore((s) => s.mergePayload)
  const select = useStore((s) => s.select)
  const open = () => {
    mergePayload({
      nodes: [{ id: `Anime:${a.id}`, label: 'Anime', key: a.id, name: a.title, image_url: a.image_url, watched: a.status !== 'plan_to_watch', list_status: a.status, fetched: true, props: {} }],
      edges: [],
    })
    select(`Anime:${a.id}`)
    navigate('/')
  }
  return (
    <button className="card" style={{ opacity: dim ? 0.35 : 1 }} onClick={open} title="Open in graph">
      {a.image_url ? <img src={a.image_url} alt="" /> : <div className="noimg" />}
      <div className="card-body">
        <strong>{a.title}</strong>
        <span className="muted">
          <i className="dot" style={{ background: STATUS_COLORS[a.status] }} /> {LIST_STATUS_LABELS[a.status]}
          {a.my_score > 0 ? ` · ${a.my_score}/10` : ''}
        </span>
        {note && <span className="muted small-text">{note}</span>}
      </div>
    </button>
  )
}
