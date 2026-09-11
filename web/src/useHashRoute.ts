import { useEffect, useState } from 'react'

/** Tiny hash router: '#/roster/8' -> ['roster', '8']. Empty hash = graph view. */
export function useHashRoute(): string[] {
  const parse = () => window.location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [route, setRoute] = useState<string[]>(parse)
  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export const navigate = (hash: string) => {
  window.location.hash = hash
}
