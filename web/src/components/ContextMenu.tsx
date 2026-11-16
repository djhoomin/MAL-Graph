import { useStore } from '../store'
import type { Label } from '../api'

export interface MenuState {
  id: string
  label: Label
  x: number
  y: number
}

export function ContextMenu({ menu, onClose }: { menu: MenuState; onClose: () => void }) {
  const { expandNode, loadNeighbors, fetchFromMal, startPath, completePath, removeNode, collapseNode, select, setView, pathFrom } = useStore.getState()
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
      {item('Expand', () => void expandNode(menu.id))}
      {item('Expand without fetching', () => void loadNeighbors(menu.id))}
      {item('Refetch', () => void fetchFromMal(menu.id), !expandable)}
      {item('Collapse neighbours', () => collapseNode(menu.id))}
      {menu.label === 'Person' &&
        item('Voice roles', () => {
          select(menu.id)
          setView('va')
        })}
      {item('Find path from here', () => startPath(menu.id))}
      {pathFrom && pathFrom !== menu.id && item('Find path to here', () => void completePath(menu.id))}
      {item('Remove from canvas', () => removeNode(menu.id))}
    </div>
  )
}
