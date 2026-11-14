/** What a player has seen lately in Kiss Marry Kill, so draws feel random. Pure chance repeats itself, and players
 *  read the repeats as a pattern, so recent characters and themes are held back (the fix Apple made to shuffle).
 *  Kept per browser. If storage is blocked, the memory lasts until the page closes. */

const CHARACTERS_KEY = 'malgraph.kmk.recent'
const THEMES_KEY = 'malgraph.kmk.recentThemes'
const MAX_CHARACTERS = 80
const MAX_THEMES = 8

const memory: Record<string, string[]> = {}

function load(key: string): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (Array.isArray(v)) return v.filter((x) => typeof x === 'string')
  } catch {
    /* fall back to this page's memory */
  }
  return memory[key] ?? []
}

function remember(key: string, ids: string[], max: number) {
  const list = [...load(key).filter((x) => !ids.includes(x)), ...ids].slice(-max)
  memory[key] = list
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    /* kept in this page's memory only */
  }
}

/** How recently each character was dealt: higher is more recent, and characters not seen lately are missing. */
export function characterRecency(): Map<string, number> {
  return new Map(load(CHARACTERS_KEY).map((id, i) => [id, i]))
}
export const rememberCharacters = (ids: string[]) => remember(CHARACTERS_KEY, ids, MAX_CHARACTERS)

/** Recent themes as kind:key, oldest first. */
export const recentThemes = () => load(THEMES_KEY)
export const rememberTheme = (id: string) => remember(THEMES_KEY, [id], MAX_THEMES)
