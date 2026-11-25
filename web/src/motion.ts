/** Whether the visitor has asked for less movement. Read each time, since it can change while the app is open. */
export const lessMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** A duration for movement that only shows where something went: none at all when less movement is wanted. */
export const ms = (duration: number) => (lessMotion() ? 0 : duration)

/** For scrolling into place. */
export const scrollBehavior = (): ScrollBehavior => (lessMotion() ? 'auto' : 'smooth')
