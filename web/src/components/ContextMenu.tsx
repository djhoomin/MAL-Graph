import { useStore } from '../store'
import type { Label } from '../api'

export interface MenuState {
  id: string
  label: Label
  x: number
  y: number
}

export function ContextMenu({ menu, onClose }: { menu: MenuState; onClose: () => void }) {
  const { loadNeighbors, fetchFromMal, setPathEnd, removeNode, collapseNode, select, setView } = useStore.getState()
  const expandable = menu.label === 'Anime' || menu.label === 'Person' || menu.label === 'Character'
  const item = (text: string, fn: () => void, disabled = false) => (
    <button
      disabled={disabled}
      onClick={() => {
        fn()
        onClose()
      }}
    >
      {text}
    </button>
  )
  return (
    <div className="ctx-menu" style={{ left: menu.x, top: menu.y }}>
      {item('Expand neighbours (from DB)', () => void loadNeighbors(menu.id))}
      {item('Fetch from MAL (Jikan)', () => void fetchFromMal(menu.id), !expandable)}
      {item('Collapse (remove leaf neighbours)', () => collapseNode(menu.id))}
      {menu.label === 'Person' &&
        item('Show voice roles', () => {
          select(menu.id)
          setView('va')
        })}
      {item('Set as path start', () => setPathEnd('from', menu.id))}
      {item('Set as path end', () => setPathEnd('to', menu.id))}
      {item('Remove from canvas', () => removeNode(menu.id))}
    </div>
  )
}
