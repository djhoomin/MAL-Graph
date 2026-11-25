import { useEffect, type RefObject } from 'react'

/** Close a popover on Escape or on a pointer press outside `ref`. */
export function useDismiss(ref: RefObject<HTMLElement | null>, open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // Closing removes whatever had focus, so hand it back to the button or field that opened the popover.
      if (ref.current?.contains(document.activeElement)) ref.current.querySelector<HTMLElement>('[aria-expanded], input')?.focus()
      onClose()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [ref, open, onClose])
}
