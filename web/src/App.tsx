import { lazy, Suspense, useEffect, useRef } from 'react'
import { LoadBoundary, PageLoading } from './components/LoadBoundary'
import { PENDING_INVITE_KEY } from './invite'
import { navigate, useHashRoute } from './useHashRoute'

// Each page is its own download, so a text page or a game doesn't bring the graph library along.
const load = {
  graph: () => import('./GraphPage'),
  roster: () => import('./components/RosterPage'),
  insights: () => import('./insights/InsightsPage'),
  privacy: () => import('./components/PrivacyPage'),
  help: () => import('./components/HelpPage'),
  tour: () => import('./components/TourPage'),
  kmk: () => import('./components/KmkPage'),
  odd: () => import('./components/OddPage'),
  mystery: () => import('./components/MysteryPage'),
  yay: () => import('./components/YayPage'),
  match: () => import('./components/MatchPage'),
}
const GraphPage = lazy(() => load.graph().then((m) => ({ default: m.GraphPage })))
const RosterPage = lazy(() => load.roster().then((m) => ({ default: m.RosterPage })))
const InsightsPage = lazy(() => load.insights().then((m) => ({ default: m.InsightsPage })))
const PrivacyPage = lazy(() => load.privacy().then((m) => ({ default: m.PrivacyPage })))
const HelpPage = lazy(() => load.help().then((m) => ({ default: m.HelpPage })))
const TourPage = lazy(() => load.tour().then((m) => ({ default: m.TourPage })))
const KmkPage = lazy(() => load.kmk().then((m) => ({ default: m.KmkPage })))
const OddPage = lazy(() => load.odd().then((m) => ({ default: m.OddPage })))
const MysteryPage = lazy(() => load.mystery().then((m) => ({ default: m.MysteryPage })))
const YayPage = lazy(() => load.yay().then((m) => ({ default: m.YayPage })))
const MatchPage = lazy(() => load.match().then((m) => ({ default: m.MatchPage })))

const TITLES: Record<string, string> = {
  roster: 'Voice actor roster',
  insights: 'Insights',
  privacy: 'Privacy',
  help: 'Help',
  tour: 'Graph tour',
  kmk: 'Kiss Marry Kill',
  odd: 'Odd one out',
  mystery: 'Mystery character',
  yay: 'Yay or Nay',
  match: 'Taste match',
}

export default function App() {
  const route = useHashRoute()
  const main = useRef<HTMLElement>(null)
  const page = route[0] in TITLES ? route[0] : ''
  const shown = useRef(page)
  useEffect(() => {
    document.title = page ? `${TITLES[page]} · Aniweb` : 'Aniweb'
    if (shown.current === page) return
    shown.current = page
    main.current?.focus({ preventScroll: true }) // the link that led here is gone, so start from the new page
  }, [page])
  // Someone opened an invite before signing in, and signing in brought them back to the start page.
  useEffect(() => {
    try {
      const token = localStorage.getItem(PENDING_INVITE_KEY)
      if (!token) return
      localStorage.removeItem(PENDING_INVITE_KEY)
      if (!window.location.hash.replace(/^#\/?/, '')) navigate(`match/join/${token}`)
    } catch {
      /* storage blocked */
    }
  }, [])
  return (
    <main ref={main} tabIndex={-1}>
      <LoadBoundary key={page}>
        <Suspense fallback={<PageLoading />}>
          <Page route={route} />
        </Suspense>
      </LoadBoundary>
    </main>
  )
}

function Page({ route }: { route: string[] }) {
  if (route[0] === 'roster') return <RosterPage personId={route[1]} />
  if (route[0] === 'insights') return <InsightsPage />
  if (route[0] === 'privacy') return <PrivacyPage />
  if (route[0] === 'help') return <HelpPage />
  if (route[0] === 'tour') return <TourPage />
  if (route[0] === 'kmk') return <KmkPage />
  if (route[0] === 'odd') return <OddPage />
  if (route[0] === 'mystery') return <MysteryPage />
  if (route[0] === 'yay') return <YayPage />
  if (route[0] === 'match') return <MatchPage route={route} />
  return <GraphPage />
}
