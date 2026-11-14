import { useEffect, useState, type ReactNode } from 'react'
import { errorText, tourApi, type GraphPayload, type Tour, type TourBridge, type TourCluster, type TourCut, type TourThread, type TourTwins } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

const STEPS = ['Your taste clusters', 'The bridges', 'The cut points', 'Twins'] as const
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
async function showOnGraph(load: () => Promise<GraphPayload>, select?: string) {
  const payload = await load()
  const { clear, setFilter, filters } = useStore.getState()
  // The tour's links are mostly staff credits, which the graph hides by default.
  if (!filters.rels.WORKED_ON) setFilter({ rels: { ...filters.rels, WORKED_ON: true } })
  clear()
  navigate('')
  setTimeout(() => {
    useStore.getState().mergePayload(payload)
    if (select) useStore.getState().select(select)
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
        {tour && step === 2 && <Cuts tour={tour} />}
        {tour && step === 3 && <Twins tour={tour} />}
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
function Lesson({ title, query, note, children }: { title: string; query: string; note?: string; children: ReactNode }) {
  return (
    <aside className="tour-lesson">
      <strong>{title}</strong>
      {children}
      <details>
        <summary>See the query</summary>
        <pre>{query}</pre>
        <p className="muted small-text">{note ?? 'This is the query that ran on your graph. $user is your MyAnimeList name.'}</p>
      </details>
    </aside>
  )
}

function ShowButton({ load, select }: { load: () => Promise<GraphPayload>; select?: string }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <>
      <button
        onClick={() => {
          setBusy(true)
          setError(null)
          showOnGraph(load, select).catch((e) => {
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
  const [timeline, setTimeline] = useState(false)
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
      {timeline && <Timeline timeline={cluster.timeline} />}
      <div className="row">
        <ShowButton load={() => tourApi.cluster(index)} />
        {cluster.timeline.items.length > 1 && <button onClick={() => setTimeline((v) => !v)}>{timeline ? 'Hide the timeline' : 'Timeline'}</button>}
      </div>
    </section>
  )
}

const SEASON_NAMES = ['Winter', 'Spring', 'Summer', 'Fall']

/** A cluster's anime by the season they started airing. Tap a person or studio to pick out their anime. */
function Timeline({ timeline }: { timeline: TourCluster['timeline'] }) {
  const [maker, setMaker] = useState<string | null>(null)
  const [picked, setPicked] = useState<number | null>(null)
  const years = [...new Set(timeline.items.map((a) => a.year))].sort((x, y) => x - y)
  const pick = picked != null ? timeline.items.find((a) => a.mal_id === picked) : null
  return (
    <div className="tour-timeline">
      {timeline.makers.length > 0 && (
        <div className="row tour-timeline-makers">
          {timeline.makers.map((m) => (
            <button key={m.id} className={`chip ${maker === m.id ? 'on' : 'off'}`} onClick={() => setMaker(maker === m.id ? null : m.id)}>
              {m.name} <span className="muted">{m.anime}</span>
            </button>
          ))}
        </div>
      )}
      <div className="tour-timeline-grid">
        <span />
        {SEASON_NAMES.map((s) => (
          <span key={s} className="muted small-text">
            {s}
          </span>
        ))}
        {years.map((year, i) => (
          <TimelineYear key={year} year={year} gap={i > 0 ? year - years[i - 1] - 1 : 0} items={timeline.items.filter((a) => a.year === year)} maker={maker} picked={picked} onPick={setPicked} />
        ))}
      </div>
      <p className="small-text tour-timeline-picked">
        {pick ? `${pick.title}, ${SEASON_NAMES[pick.season].toLowerCase()} ${pick.year}` : <span className="muted">Tap a cover to see its title.</span>}
      </p>
    </div>
  )
}

function TimelineYear({ year, gap, items, maker, picked, onPick }: { year: number; gap: number; items: TourCluster['timeline']['items']; maker: string | null; picked: number | null; onPick: (id: number) => void }) {
  return (
    <>
      {gap > 0 && <span className="tour-timeline-gap muted small-text">{gap === 1 ? '1 year without any' : `${gap} years without any`}</span>}
      <span className="small-text tour-timeline-year">{year}</span>
      {SEASON_NAMES.map((_, season) => (
        <span key={season} className="tour-timeline-cell">
          {items
            .filter((a) => a.season === season)
            .map((a) => (
              <button
                key={a.mal_id}
                className={`tour-timeline-cover${maker && !a.makers.includes(maker) ? ' dim' : ''}${picked === a.mal_id ? ' picked' : ''}`}
                title={a.title}
                aria-label={a.title}
                onClick={() => onPick(a.mal_id)}
              >
                {a.image_url ? <img src={a.image_url} alt="" loading="lazy" /> : <span className="noimg" />}
              </button>
            ))}
        </span>
      ))}
    </>
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

function Cuts({ tour }: { tour: Tour }) {
  if (!tour.cuts.length && !tour.threads.length) return <p className="muted">Every cluster in your list holds together without any single person, studio or anime. Sync more of your list and come back.</p>
  return (
    <>
      <h2>What holds your clusters together?</h2>
      <p>Some clusters hang by a thread. Each of these people, studios and anime is the only link between two parts of a cluster, so the cluster splits apart without them.</p>
      <Lesson title="The graph idea: cut points" query={tour.queries.cuts} note="This query ran once for each cluster. $anime, $people and $studios are the anime and makers drawn for that cluster.">
        <p>A cut point, also called an articulation point, is a node whose removal splits a graph into separate pieces. Memgraph finds them by breaking each cluster into biconnected components, which are pieces that stay connected whichever single node you take out. Anything that belongs to two of those pieces is a cut point.</p>
        <p>Bridges connect your whole list, and cut points are the weak spots inside one cluster. In a network of people, a cut point is the one contact two groups share. Here it's often a composer or a studio who worked on two otherwise unrelated sets of shows.</p>
      </Lesson>
      {tour.cuts.map((c) => (
        <CutCard key={`${c.cluster}-${c.id}`} cut={c} />
      ))}
      {tour.threads.length > 0 && <Threads threads={tour.threads} />}
    </>
  )
}

function CutCard({ cut }: { cut: TourCut }) {
  const pieces = cut.sides.length === 2 ? 'two' : cut.sides.length === 3 ? 'three' : String(cut.sides.length)
  return (
    <section className="tour-card">
      <div className="tour-card-head">
        <h3>{cut.name}</h3>
        <span className="muted small-text">
          {cut.label}, cluster {cut.cluster + 1}
        </span>
      </div>
      <p className="small-text">
        Without {cut.name}, cluster {cut.cluster + 1} falls into {pieces} pieces.
      </p>
      {cut.sides.map((side, i) => (
        <div key={i} className="tour-side">
          <p className="muted small-text">
            {side.series === 1 ? '1 series' : `${side.series} series`}
            {side.anime > side.series && `, ${side.anime} anime`}
          </p>
          <Covers items={side.items} />
        </div>
      ))}
      <ShowButton load={() => tourApi.cluster(cut.cluster)} select={cut.id} />
    </section>
  )
}

const and = (xs: string[]) => (xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`)

function Threads({ threads }: { threads: TourThread[] }) {
  const [all, setAll] = useState(false)
  const shown = all ? threads : threads.slice(0, 6)
  return (
    <>
      <h3 className="tour-subhead">Hanging by a thread</h3>
      <p className="small-text">These shows belong to a cluster but connect to the rest of it through only one person, studio or anime.</p>
      <div className="tour-threads">
        {shown.map((t) => (
          <div key={`${t.cluster}-${t.show.mal_id}-${t.via.id}`} className="tour-thread">
            {t.show.image_url ? <img src={t.show.image_url} alt="" loading="lazy" /> : <div className="noimg" />}
            <p className="small-text">
              <strong>{t.show.title}</strong> connects to cluster {t.cluster + 1} only through <strong>{t.via.name}</strong>
              {t.also.length > 0 ? `, who also worked on ${and(t.also.map((a) => a.title))}.` : '.'}
            </p>
            <ShowButton load={() => tourApi.cluster(t.cluster)} select={t.via.id} />
          </div>
        ))}
      </div>
      {threads.length > 6 && (
        <button className="link small-text" onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show all ${threads.length}`}
        </button>
      )}
    </>
  )
}

function Twins({ tour }: { tour: Tour }) {
  if (!tour.twins.length) return <p className="muted">None of your anime from different series share enough of their makers yet. Sync more of your list and come back.</p>
  return (
    <>
      <h2>Which of your shows were made by the same team?</h2>
      <p>These anime come from different series but share a lot of the people behind them. Sequels are left out, since they share almost everything.</p>
      <Lesson title="The graph idea: Jaccard similarity" query={tour.queries.twins} note="This is the query that ran on your graph. $user is your MyAnimeList name, and $min_shared is 3, since many anime only list a few makers.">
        <p>To compare two anime, the graph looks at their neighbours, which here are the people and studios linked to each. Jaccard similarity divides the neighbours they share by all the neighbours either of them has. Two anime made by exactly the same team score 1, and two with nobody in common score 0.</p>
        <p>Recommendation systems use the same idea, with the people who watched a show in place of the people who made it.</p>
      </Lesson>
      {tour.twins.map((t, i) => (
        <TwinsCard key={i} index={i} twins={t} />
      ))}
    </>
  )
}

function TwinsCard({ index, twins }: { index: number; twins: TourTwins }) {
  const n = twins.shows.length
  return (
    <section className="tour-card">
      <Covers items={twins.shows} />
      <p className="small-text">
        {n === 2
          ? `They share ${twins.shared.length} of the ${twins.either} people and studios behind either of them, a similarity of ${twins.jaccard.toFixed(2)}.`
          : `All ${n === 3 ? 'three' : n} share the same ${twins.shared.length} people and studios.`}
      </p>
      <p className="small-text">
        <span className="muted">Shared </span>
        {twins.shared.map((m) => m.name).join(', ')}
      </p>
      <ShowButton load={() => tourApi.twins(index)} />
    </section>
  )
}
