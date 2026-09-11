import { useEffect } from 'react'
import { useStore } from '../store'

export function StatusBar() {
  const busy = useStore((s) => s.busy)
  const error = useStore((s) => s.error)
  const user = useStore((s) => s.user)
  const nodeCount = useStore((s) => Object.keys(s.nodes).length)
  const edgeCount = useStore((s) => Object.keys(s.edges).length)
  const refreshUser = useStore((s) => s.refreshUser)

  useEffect(() => {
    void refreshUser()
  }, [refreshUser])

  return (
    <div className="statusbar">
      <span>
        canvas: {nodeCount} nodes · {edgeCount} edges
      </span>
      {user?.username && (
        <span>
          {user.username}: {user.total} on list
          {Object.entries(user.by_status)
            .map(([k, v]) => ` · ${k.replace(/_/g, ' ')} ${v}`)
            .join('')}
          {user.unfetched > 0 && <em> · {user.unfetched} not yet fetched from MAL</em>}
        </span>
      )}
      {!user?.username && <span className="muted">no MAL list synced yet — run `malgraph sync-list`</span>}
      {busy && <span className="busy">⏳ {busy}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  )
}
