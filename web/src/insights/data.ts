import type { ListAnime, ListStatus } from '../api'

export const SEASONS = ['winter', 'spring', 'summer', 'fall'] as const
export const SEEN: ListStatus[] = ['completed', 'watching', 'on_hold', 'dropped']

/** Season index (year*4 + quarter) for an anime, using MAL's season or the air date. */
export function seasonKey(a: ListAnime): number | null {
  const date = a.aired_from ? new Date(a.aired_from) : null
  const year = a.year ?? date?.getUTCFullYear() ?? null
  if (year == null) return null
  let q = a.season ? SEASONS.indexOf(a.season as (typeof SEASONS)[number]) : -1
  if (q < 0) q = date ? Math.floor(date.getUTCMonth() / 3) : 0
  return year * 4 + q
}
export const seasonLabel = (key: number) => `${SEASONS[key % 4][0].toUpperCase()}${SEASONS[key % 4].slice(1)} ${Math.floor(key / 4)}`
export const yearOf = (key: number) => Math.floor(key / 4)

export interface Bucket {
  key: number // season key, or year when granularity = 'year'
  label: string
  anime: ListAnime[]
  byStatus: Record<ListStatus, ListAnime[]>
}

export function buildBuckets(anime: ListAnime[], granularity: 'season' | 'year'): Bucket[] {
  const keyed = anime.map((a) => ({ a, k: seasonKey(a) })).filter((x): x is { a: ListAnime; k: number } => x.k != null)
  if (keyed.length === 0) return []
  const toBucketKey = (k: number) => (granularity === 'year' ? yearOf(k) : k)
  const keys = keyed.map((x) => toBucketKey(x.k))
  const lo = Math.min(...keys)
  const hi = Math.max(...keys)
  const buckets: Bucket[] = []
  for (let k = lo; k <= hi; k++) {
    buckets.push({
      key: k,
      label: granularity === 'year' ? String(k) : seasonLabel(k),
      anime: [],
      byStatus: { completed: [], watching: [], on_hold: [], dropped: [], plan_to_watch: [], none: [] },
    })
  }
  for (const { a, k } of keyed) {
    const b = buckets[toBucketKey(k) - lo]
    b.anime.push(a)
    b.byStatus[a.status].push(a)
  }
  return buckets
}

export const fmt = (n: number) => n.toLocaleString('en-US')
