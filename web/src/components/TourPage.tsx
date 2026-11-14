import { useEffect, useState, type ReactNode } from 'react'
import { errorText, tourApi, type GraphPayload, type Tour, type TourBridge, type TourCluster } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

const STEPS = ['Your taste clusters', 'The bridges'] as const
const STEP_KEY = 'malgraph.tour.step'

function loadStep(): number {
  try {
    const n = Number(localStorage.getItem(STEP_KEY))
    return n >= 0 && n < STEPS.length ? n : 0
  } catch {
    return 0
  }
}

/** Put a cluster or a bridge on the graph by itself, then go and look at it. The graph is opened first and the
 *  nodes added once its canvas exists, so they're laid out on a canvas that has its size. */
async function showOnGraph(load: () => Promise<GraphPayload>) {
  const payload = await load()
  const { clear, setFilter, filters } = useStore.getState()
  // The tour's links are mostly staff credits, which the graph hides by default.
  if (!filters.rels.WORKED_ON) setFilter({ rels: { ...filters.rels, WORKED_ON: true } })
  clear()
  navigate('')
  setTimeout(() => {
    useStore.getState().mergePayload(payload)
  }, 150)
}

/** The graph tour: questions about your list that only the graph's structure can answer. */
export function TourPage() {
  const [tour, setTour] = useState<Tour | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState(loadStep)

  useEffect(() => {
    tourApi.get().then(setTour, (e) => setError(errorText(e)))
  }, [])

  const go = (n: number) => {
    setStep(n)
    try {
      localStorage.setItem(STEP_KEY, String(n))
    } catch {
      /* storage blocked: the tour starts at the beginning next time */
    }
    document.querySelector('.doc-page')?.scrollTo({ top: 0 })
  }

  return (
    <div className="doc-page">
      <header className="doc-head">
        <button className="link" onClick={() => navigate('')}>
          ← Back to the graph
        </button>
      </header>
      <div className="kmk-page tour">
        <h1>Graph tour</h1>
        {tour && (
          <p className="muted">
            Your list is a graph. Your {tour.anime} anime are linked to the {tour.makers} people and studios who made them, whenever someone directed, wrote, scored, designed or animated a show. This tour asks questions about your taste that a list can't answer but the shape of that graph can.
          </p>
        )}
        <div className="segmented game-mode" role="group" aria-label="Tour step">
          {STEPS.map((s, i) => (
            <button key={s} className={step === i ? 'on' : ''} onClick={() => go(i)}>
              {i + 1}. {s}
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
        {!tour && !error && <p className="muted">Working out your graph…</p>}
        {tour && step === 0 && <Clusters tour={tour} />}
        {tour && step === 1 && <Bridges tour={tour} />}
        {tour && (
          <div className="kmk-actions tour-nav">
            {step > 0 && <button onClick={() => go(step - 1)}>Back</button>}
            {step < STEPS.length - 1 ? (
              <button className="primary" onClick={() => go(step + 1)}>
                Next: {STEPS[step + 1].toLowerCase()}
              </button>
            ) : (
              <button className="primary" onClick={() => navigate('')}>
                Back to your graph
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** What the step teaches, and the query behind it. */
function Lesson({ title, query, children }: { title: string; query: string; children: ReactNode }) {
  return (
    <aside className="tour-lesson">
      <strong>{title}</strong>
      {children}
      <details>
        <summary>See the query</summary>
        <pre>{query}</pre>
        <p className="muted small-text">This is the query that ran on your graph. $user is your MyAnimeList name.</p>
      </details>
    </aside>
  )
}

function ShowButton({ load }: { load: () => Promise<GraphPayload> }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      <button
        onClick={() => {
          setBusy(true)
          setError(null)
          showOnGraph(load).catch((e) => {
            setError(errorText(e))
            setBusy(false)
          })
        }}
        disabled={busy}
      >
        {busy ? 'Loading…' : 'Show on the graph'}
      </button>
      {error && <span className="error small-text">{error}</span>}
    </>
  )
}

function Covers({ items }: { items: { mal_id: number; title: string; image_url: string | null }[] }) {
  return (
    <div className="tour-covers">
      {items.map((s) => (
        <figure key={s.mal_id} title={s.title}>
          {s.image_url ? <img src={s.image_url} alt="" loading="lazy" /> : <div className="noimg" />}
          <figcaption>{s.title}</figcaption>
        </figure>
      ))}
    </div>
  )
}

function Clusters({ tour }: { tour: Tour }) {
  if (!tour.clusters.length) return <p className="muted">Your list is too small to find clusters yet. Sync more of it and come back.</p>
  return (
    <>
      <h2>Which of your anime belong together?</h2>
      <p>
        The graph found {tour.clusters.length} clusters in your list, covering {tour.clustered} of your {tour.anime} anime. Each one is a group of shows that share more of their makers with each other than with the rest of your list. Sequels share almost everything, so each series is shown once.
      </p>
      <Lesson title="The graph idea: community detection" query={tour.queries.clusters}>
        <p>Nobody told the graph about genres or studios. The Louvain algorithm only looked at who is linked to what, and kept moving shows between groups until each group was as tightly knit inside as it could be. The genres under each cluster were worked out afterwards, to describe what it found.</p>
      </Lesson>
      {tour.clusters.map((c, i) => (
        <ClusterCard key={i} index={i} cluster={c} />
      ))}
    </>
  )
}

function ClusterCard({ index, cluster }: { index: number; cluster: TourCluster }) {
  const [all, setAll] = useState(false)
  const series = all ? cluster.series : cluster.series.slice(0, 6)
  return (
    <section className="tour-card">
      <div className="tour-card-head">
        <h3>Cluster {index + 1}</h3>
        <span className="muted small-text">
          {cluster.series.length} series, {cluster.anime} anime
        </span>
      </div>
      <Covers items={series} />
      {cluster.series.length > 6 && (
        <button className="link small-text" onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show all ${cluster.series.length}`}
        </button>
      )}
      {cluster.makers.length > 0 && (
        <p className="small-text">
          <span className="muted">Made by </span>
          {cluster.makers.map((m, i) => (
            <span key={m.id}>
              {i > 0 && ', '}
              {m.name} <span className="muted">({m.series})</span>
            </span>
          ))}
        </p>
      )}
      {cluster.genres.length > 0 && (
        <p className="small-text">
          <span className="muted">More than usual for you: </span>
          {cluster.genres.join(', ')}
        </p>
      )}
      <ShowButton load={() => tourApi.cluster(index)} />
    </section>
  )
}

function Bridges({ tour }: { tour: Tour }) {
  if (!tour.bridges.length) return <p className="muted">Your clusters don't share anyone yet, so there are no bridges. Sync more of your list and come back.</p>
  return (
    <>
      <h2>Who connects the different sides of your taste?</h2>
      <p>These people and studios link clusters that otherwise have little to do with each other. Take one away and parts of your graph drift apart.</p>
      <Lesson title="The graph idea: betweenness centrality" query={tour.queries.bridges}>
        <p>Imagine walking from every anime on your list to every other one along the graph, always taking the shortest way. Betweenness counts how many of those walks pass through someone. It measures where someone sits in the network, so a bridge isn't always the person you've seen most. The number next to each bridge shows where they'd rank if you only counted their shows.</p>
      </Lesson>
      {tour.bridges.map((b) => (
        <BridgeCard key={b.id} bridge={b} />
      ))}
    </>
  )
}

function BridgeCard({ bridge }: { bridge: TourBridge }) {
  const gap = bridge.count_rank - bridge.rank
  return (
    <section className="tour-card">
      <div className="tour-card-head">
        <h3>
          {bridge.rank}. {bridge.name}
        </h3>
        <span className="muted small-text">{bridge.label === 'Studio' ? 'Studio' : 'Person'}</span>
      </div>
      <p className="small-text">
        Joins {bridge.clusters.length} of your clusters. Behind {bridge.series} of your series, which would make them number {bridge.count_rank} by count
        {gap >= 5 ? ', so their place in the graph matters far more than how often they show up.' : '.'}
      </p>
      <Covers items={bridge.clusters.map((c) => ({ ...c, title: `Cluster ${c.cluster + 1}: ${c.title}` }))} />
      <ShowButton load={() => tourApi.bridge(bridge.id)} />
    </section>
  )
}
