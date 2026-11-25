import { useState } from 'react'
import { useStore, type PathOpts } from '../store'
import { CloseIcon } from './icons'

const VIA: [keyof PathOpts['via'], string][] = [
  ['va', 'voice actors'],
  ['staff', 'staff'],
  ['related', 'related anime'],
  ['studio', 'studios'],
  ['genre', 'genres'],
]

/** Contextual path finding: appears after "Path" on a node, shows the result, hides again on ×. */
export function PathBar() {
  const pathFrom = useStore((s) => s.pathFrom)
  const pathTo = useStore((s) => s.pathTo)
  const picking = useStore((s) => s.pathPicking)
  const result = useStore((s) => s.pathResult)
  const opts = useStore((s) => s.pathOpts)
  const nodes = useStore((s) => s.nodes)
  const busy = useStore((s) => s.busy)
  const { clearPath, setPathOpts, select } = useStore.getState()
  const [showOpts, setShowOpts] = useState(false)

  if (!pathFrom || (!picking && !pathTo)) return null
  const name = (id: string) => nodes[id]?.name ?? id

  return (
    <div className="path-bar float-panel" role="region" aria-label="Path" tabIndex={-1}>
      <div className="path-head">
        {picking ? (
          <span>
            Path from <strong>{name(pathFrom)}</strong>. Tap a node or search for the destination.
          </span>
        ) : (
          <span>
            <strong>{name(pathFrom)}</strong> to <strong>{name(pathTo!)}</strong>
            {result?.found && (
              <span className="muted">
                {' '}
                · {result.hops} hops{result.paths.length > 1 ? ` · ${result.paths.length} paths` : ''}
              </span>
            )}
            {busy === 'Finding path…' && <span className="muted"> · finding…</span>}
          </span>
        )}
        {!picking && (
          <button className="link" onClick={() => setShowOpts((v) => !v)} aria-expanded={showOpts}>
            {showOpts ? 'Hide options' : 'Options'}
          </button>
        )}
        <button className="icon-btn ghost" onClick={clearPath} aria-label="Close path">
          <CloseIcon />
        </button>
      </div>

      <div className="sr-only" role="status">
        {!picking && result?.found ? `Path found, ${result.hops} hops` : ''}
      </div>
      {!picking && result && !result.found && <div className="error" role="alert">No path within {opts.maxHops} hops in the data fetched so far.</div>}
      {!picking && result?.found && (
        <div className="path-list">
          {result.paths.slice(0, 5).map((p, i) => (
            <div key={i} className="path">
              {p.map((id, j) => (
                <span key={id}>
                  {j > 0 && <span className="muted"> → </span>}
                  <button className="link" onClick={() => select(id)}>
                    {name(id)}
                  </button>
                </span>
              ))}
            </div>
          ))}
        </div>
      )}

      {showOpts && !picking && (
        <div className="path-opts">
          <label className="row">
            Max hops <input type="range" min={1} max={15} value={opts.maxHops} onChange={(e) => setPathOpts({ maxHops: +e.target.value })} /> {opts.maxHops}
          </label>
          <div className="chips">
            {VIA.map(([k, label]) => (
              <button key={k} className={`chip ${opts.via[k] ? '' : 'off'}`} aria-pressed={opts.via[k]} onClick={() => setPathOpts({ via: { ...opts.via, [k]: !opts.via[k] } })}>
                {label}
              </button>
            ))}
          </div>
          <label className="toggle">
            <input type="checkbox" checked={opts.onlyWatched} onChange={(e) => setPathOpts({ onlyWatched: e.target.checked })} /> Only through anime I've seen
          </label>
          <label className="toggle">
            <input type="checkbox" checked={opts.allPaths} onChange={(e) => setPathOpts({ allPaths: e.target.checked })} /> Show all shortest paths
          </label>
        </div>
      )}
    </div>
  )
}
