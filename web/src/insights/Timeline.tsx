import { useEffect, useMemo, useRef, useState } from 'react'
import type { ListAnime, ListStatus } from '../api'
import { LIST_STATUS_LABELS } from '../api'
import { STATUS_COLORS } from '../graph/style'
import { buildBuckets, type Bucket } from './data'

/** Label every Nth year so rotated labels (about 14px apart at 45°) never overlap. */
const yearStep = (yearWidth: number) => [1, 2, 5, 10].find((n) => n * yearWidth >= 14) ?? 10

const ORDER: ListStatus[] = ['completed', 'watching', 'on_hold', 'dropped', 'plan_to_watch']
const ACCENT = '#3987e5'
const DIM = '#3a3f4d'
const PLOT_H = 180
const AXIS_H = 48 // room for the season strip and rotated year labels
const STRIP_Y = 6 // season strip, just under the columns
const LABEL_Y = 22
// Winter, spring, summer, fall. Muted, so the strip groups columns without competing with the status colours.
const SEASON_COLORS = ['#6f9bd1', '#e8a3c0', '#d9c36a', '#cf8a5a']
const SEASON_NAMES = ['Winter', 'Spring', 'Summer', 'Fall']
const GAP = 2

export interface Thread {
  label: string
  ids: Set<number>
}

interface Props {
  anime: ListAnime[]
  granularity: 'season' | 'year'
  thread: Thread | null
  onPick: (bucket: Bucket) => void
  picked: number | null
}

/** Stacked column chart: one column per season (or year), stacked by list status; emphasis mode when a thread is set. */
export function Timeline({ anime, granularity, thread, onPick, picked }: Props) {
  const buckets = useMemo(() => buildBuckets(anime, granularity), [anime, granularity])
  const [hover, setHover] = useState<{ b: Bucket; x: number } | null>(null)
  const [table, setTable] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const [avail, setAvail] = useState(1000)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => setAvail(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [table])
  // When the chart is wider than the screen (phones), start at the most recent seasons.
  useEffect(() => {
    const el = wrap.current
    if (el) el.scrollLeft = el.scrollWidth
  }, [table, granularity, buckets.length])

  const max = Math.max(1, ...buckets.map((b) => b.anime.length))
  // Fit all columns into the available width when possible; scroll only below the minimum width.
  const colW = Math.max(granularity === 'year' ? 14 : 6, Math.min(granularity === 'year' ? 40 : 22, Math.floor((avail - 40) / Math.max(1, buckets.length))))
  const width = buckets.length * colW
  const yTicks = niceTicks(max)
  const scale = (n: number) => (n / yTicks[yTicks.length - 1]) * PLOT_H

  // Years in view, with where each one starts and ends on the x axis.
  const years = useMemo(() => {
    const out: { year: number; x0: number; x1: number }[] = []
    buckets.forEach((b, i) => {
      const year = granularity === 'year' ? b.key : Math.floor(b.key / 4)
      const x = 32 + i * colW
      const last = out[out.length - 1]
      if (last && last.year === year) last.x1 = x + colW
      else out.push({ year, x0: x, x1: x + colW })
    })
    return out
  }, [buckets, granularity, colW])
  const step = yearStep(granularity === 'year' ? colW : 4 * colW)

  if (buckets.length === 0) return <div className="muted">No dated anime in this selection.</div>

  return (
    <div className="chart">
      <div className="chart-head">
        <div className="legend">
          {granularity === 'season' && !table && (
            <span className="season-legend">
              {SEASON_NAMES.map((n, i) => (
                <span key={n}>
                  <span className="swatch thin" style={{ background: SEASON_COLORS[i] }} /> {n}
                </span>
              ))}
            </span>
          )}
          {thread ? (
            <>
              <span className="swatch" style={{ background: ACCENT }} /> {thread.label}
              <span className="swatch" style={{ background: DIM, marginLeft: 12 }} /> other
            </>
          ) : (
            ORDER.map((s) => (
              <span key={s}>
                <span className="swatch" style={{ background: STATUS_COLORS[s] }} /> {LIST_STATUS_LABELS[s]}
              </span>
            ))
          )}
        </div>
        <button className="small" onClick={() => setTable((t) => !t)}>
          {table ? 'chart' : 'table'}
        </button>
      </div>

      {table ? (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{granularity}</th>
                <th>total</th>
                {ORDER.map((s) => (
                  <th key={s}>{LIST_STATUS_LABELS[s]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {buckets
                .filter((b) => b.anime.length)
                .map((b) => (
                  <tr key={b.key} onClick={() => onPick(b)} className="clickable">
                    <td>{b.label}</td>
                    <td>{b.anime.length}</td>
                    {ORDER.map((s) => (
                      <td key={s}>{b.byStatus[s].length || ''}</td>
                    ))}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-scroll" ref={wrap} onMouseLeave={() => setHover(null)}>
          <svg width={width + 36} height={PLOT_H + AXIS_H + 8} style={{ display: 'block' }}>
            {/* every other year shaded, so a year's seasons read as one group */}
            {granularity === 'season' &&
              years.map((y) =>
                y.year % 2 === 0 ? <rect key={`band${y.year}`} x={y.x0 - GAP / 2} y={0} width={y.x1 - y.x0} height={PLOT_H + 4} fill="rgba(255,255,255,0.035)" /> : null,
              )}
            {/* year labels, rotated and centred under the year */}
            {years.map((y) =>
              // A partial first or last year (under two seasons) would crowd its neighbour's label.
              (y.year % step === 0 || years.length <= 3) && (granularity === 'year' || y.x1 - y.x0 >= 2 * colW) ? (
                <text key={`y${y.year}`} transform={`translate(${(y.x0 + y.x1) / 2 - GAP / 2},${PLOT_H + LABEL_Y}) rotate(-45)`} textAnchor="end" className="axis">
                  {y.year}
                </text>
              ) : null,
            )}
            {/* y grid + labels */}
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${PLOT_H - scale(t) + 4})`}>
                <line x1={30} x2={width + 36} y1={0} y2={0} stroke="var(--border)" strokeWidth={1} />
                <text x={26} y={4} textAnchor="end" className="axis">
                  {t}
                </text>
              </g>
            ))}
            {buckets.map((b, i) => {
              const x = 32 + i * colW
              let y = PLOT_H + 4
              const segments = thread
                ? [
                    { color: DIM, n: b.anime.filter((a) => !thread.ids.has(a.id)).length },
                    { color: ACCENT, n: b.anime.filter((a) => thread.ids.has(a.id)).length },
                  ]
                : ORDER.map((s) => ({ color: STATUS_COLORS[s], n: b.byStatus[s].length }))
              return (
                <g key={b.key}>
                  {granularity === 'season' && <rect x={x} y={PLOT_H + STRIP_Y} width={colW - GAP} height={3} fill={SEASON_COLORS[b.key % 4]} opacity={0.8} />}
                  {segments.map((seg, j) => {
                    if (!seg.n) return null
                    const h = Math.max(1, scale(seg.n) - GAP)
                    y -= scale(seg.n)
                    const isTop = j === segments.length - 1 || segments.slice(j + 1).every((r) => !r.n)
                    return <rect key={j} x={x} y={y} width={colW - GAP} height={h} fill={seg.color} rx={isTop ? 3 : 0} ry={isTop ? 3 : 0} />
                  })}
                  {/* hit target: full column */}
                  <rect
                    x={x - GAP / 2}
                    y={0}
                    width={colW}
                    height={PLOT_H + AXIS_H}
                    fill={picked === b.key ? 'rgba(255,255,255,0.06)' : 'transparent'}
                    stroke={picked === b.key ? 'var(--accent)' : 'none'}
                    className="hit"
                    onMouseEnter={() => setHover({ b, x })}
                    onClick={() => onPick(b)}
                  />
                </g>
              )
            })}
          </svg>
          {hover && hover.b.anime.length > 0 && (
            <div className="tooltip" style={hover.x > avail / 2 ? { right: Math.max(0, width + 36 - hover.x + 12) } : { left: hover.x + colW + 12 }}>
              <strong>{hover.b.label}</strong> · {hover.b.anime.length} anime
              <div className="muted">
                {ORDER.filter((s) => hover.b.byStatus[s].length)
                  .map((s) => `${hover.b.byStatus[s].length} ${LIST_STATUS_LABELS[s]}`)
                  .join(' · ')}
              </div>
              <ul>
                {hover.b.anime.slice(0, 6).map((a) => (
                  <li key={a.id} style={{ color: thread && !thread.ids.has(a.id) ? 'var(--muted)' : undefined }}>
                    {a.title}
                  </li>
                ))}
                {hover.b.anime.length > 6 && <li className="muted">+{hover.b.anime.length - 6} more — click for all</li>}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function niceTicks(max: number): number[] {
  const step = max <= 5 ? 1 : max <= 10 ? 2 : max <= 25 ? 5 : 10
  const top = Math.ceil(max / step) * step
  const ticks: number[] = []
  for (let t = 0; t <= top; t += step) ticks.push(t)
  return ticks
}
