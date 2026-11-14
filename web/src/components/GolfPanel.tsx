import { useMemo, useState } from 'react'
import type { GNode } from '../api'
import { edgeLabel } from '../graph/elements'
import { LABEL_COLORS } from '../graph/style'
import { scoreName, sortOptions, strokes, useGolf } from '../golf'
import { CloseIcon } from './icons'

const dayLabel = (date: string) => new Date(`${date}T00:00:00Z`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' })

function End({ node, tag }: { node: GNode; tag: string }) {
  return (
    <div className={`golf-end ${tag === 'Tee' ? 'tee' : 'hole'}`}>
      {node.image_url && <img src={node.image_url} alt="" />}
      <div>
        <small>{tag}</small>
        <span>{node.name}</span>
      </div>
    </div>
  )
}

export function GolfPanel() {
  const golf = useGolf((s) => s.golf)
  const starting = useGolf((s) => s.starting)
  const startError = useGolf((s) => s.startError)
  const { move, mulligan, giveUp, exit, start } = useGolf.getState()
  const [filter, setFilter] = useState('')

  const options = useMemo(() => {
    if (!golf) return []
    const q = filter.trim().toLowerCase()
    const all = sortOptions(golf.options)
    return q ? all.filter((o) => o.node.name.toLowerCase().includes(q)) : all
  }, [golf, filter])

  if (!golf) {
    return (
      <div className="golf-panel float-panel">
        <header>
          <strong>Graph Golf</strong>
          <button className="icon-btn ghost" onClick={exit} aria-label="Close">
            <CloseIcon />
          </button>
        </header>
        {starting ? <div className="muted">Setting up the hole…</div> : <div className="error">{startError}</div>}
      </div>
    )
  }

  const { hole, result } = golf
  const title = golf.mode === 'daily' && hole.date ? `Daily hole · ${dayLabel(hole.date)}` : 'Practice hole'
  // Switching modes starts the hole again. For the daily hole each mode has its own scores.
  const setEasy = (easy: boolean) => easy !== golf.easy && void start(golf.mode, easy)
  const warmth =
    golf.toHole == null || golf.lastToHole == null ? '' : golf.toHole < golf.lastToHole ? ' · closer' : golf.toHole > golf.lastToHole ? ' · further' : ' · no closer'
  const here = golf.trailNodes[golf.moves[golf.moves.length - 1]] ?? hole.start

  return (
    <div className="golf-panel float-panel">
      <header>
        <strong>{title}</strong>
        <span className="golf-header-actions">
          {!result && (
            <span className="segmented golf-level" role="group" aria-label="Difficulty">
              <button className={golf.easy ? '' : 'on'} onClick={() => setEasy(false)} disabled={golf.loading}>
                Normal
              </button>
              <button className={golf.easy ? 'on' : ''} onClick={() => setEasy(true)} disabled={golf.loading} title="A few moves to choose from, one of which always gets closer, and the distance to the hole after each move">
                Easy
              </button>
            </span>
          )}
          {!result && (
            <button className="link" onClick={() => void start('practice')} disabled={golf.loading}>
              {golf.mode === 'daily' ? 'Practice' : 'New hole'}
            </button>
          )}
          <button className="icon-btn ghost" onClick={exit} aria-label="Leave the game">
            <CloseIcon />
          </button>
        </span>
      </header>
      <div className="golf-ends">
        <End node={hole.start} tag="Tee" />
        <End node={hole.end} tag="Hole" />
      </div>

      {result ? (
        <div className="golf-result">
          <h2>{result.round?.gave_up ? 'Picked up' : scoreName(result.round?.strokes ?? 0, result.par)}</h2>
          <p>
            {result.round?.strokes} {result.round?.strokes === 1 ? 'stroke' : 'strokes'} · par {result.par}
            {result.shortest != null && ` · shortest route ${result.shortest}`}
            {result.round?.mulligans ? ' · 1 mulligan' : ''}
            {golf.easy ? ' · easy' : ''}
          </p>
          {result.first_round === false && <p className="muted small-text">Only your first round today counts. This is that round.</p>}
          {result.summary && result.summary.players > 0 && (
            <div className="golf-field">
              <div className="muted small-text">
                {result.summary.players} {result.summary.players === 1 ? 'player' : 'players'} today
                {result.summary.rank != null && ` · you're ${result.summary.rank} of ${result.summary.finished}`}
              </div>
              {result.summary.by_score.map((b) => (
                <div key={b.to_par} className="golf-bar">
                  <span>{scoreName(result.par + b.to_par, result.par)}</span>
                  <i style={{ width: `${(100 * b.players) / Math.max(...result.summary!.by_score.map((x) => x.players))}%` }} />
                  <b>{b.players}</b>
                </div>
              ))}
            </div>
          )}
          <p className="muted small-text">The dashed green line is the shortest route{golf.trailEdges.length ? ', and yours is in white' : ''}.</p>
          <div className="golf-actions">
            <button className="primary" onClick={() => void start('practice')}>
              Practice hole
            </button>
            <button onClick={exit}>Done</button>
          </div>
        </div>
      ) : (
        <>
          <div className="golf-score">
            <span>
              Par <b>{hole.par}</b>
            </span>
            <span>
              Strokes <b>{strokes(golf)}</b>
            </span>
          </div>
          <div className="golf-here muted small-text">
            At <b>{here.name}</b> · {golf.options.length} {golf.options.length === 1 ? 'move' : 'moves'}
          </div>
          {golf.easy && golf.toHole != null && (
            <div className={`golf-distance ${warmth === ' · closer' ? 'warmer' : warmth === ' · further' ? 'colder' : ''}`}>
              {golf.toHole} {golf.toHole === 1 ? 'step' : 'steps'} to the hole{warmth}
            </div>
          )}
          {!golf.easy && <input className="golf-filter" placeholder="Find a move" value={filter} onChange={(e) => setFilter(e.target.value)} autoComplete="off" />}
          <ul className="golf-moves">
            {options.slice(0, 300).map((o) => (
              <li key={o.node.id}>
                <button onClick={() => void move(o.node.id).then(() => setFilter(''))} disabled={golf.loading} className={o.node.id === hole.end.id ? 'is-hole' : ''}>
                  <span className="tag" style={{ background: LABEL_COLORS[o.node.label] }}>
                    {o.node.label}
                  </span>
                  <span className="golf-move-name">{o.node.name}</span>
                  <small className="muted">{edgeLabel(o.edge)}</small>
                </button>
              </li>
            ))}
            {options.length === 0 && <li className="muted small-text">{golf.loading ? 'Loading moves…' : 'No moves match.'}</li>}
          </ul>
          {golf.note && <div className="error small-text">{golf.note}</div>}
          <div className="golf-actions">
            <button onClick={() => void mulligan()} disabled={golf.loading || golf.mulligans > 0 || golf.moves.length < 2} title="Take back your last move without a stroke. One per hole.">
              {golf.mulligans > 0 ? 'Mulligan used' : 'Mulligan'}
            </button>
            <button onClick={() => void giveUp()} disabled={golf.loading}>
              Give up
            </button>
          </div>
        </>
      )}
    </div>
  )
}
