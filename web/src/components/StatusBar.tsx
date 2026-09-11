import { useEffect, useState } from 'react'
import { api, type SyncStatus } from '../api'
import { useStore } from '../store'

export function StatusBar() {
  const busy = useStore((s) => s.busy)
  const error = useStore((s) => s.error)
  const user = useStore((s) => s.user)
  const nodeCount = useStore((s) => Object.keys(s.nodes).length)
  const edgeCount = useStore((s) => Object.keys(s.edges).length)
  const refreshUser = useStore((s) => s.refreshUser)
  const run = useStore((s) => s.run)
  const [sync, setSync] = useState<SyncStatus | null>(null)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  useEffect(() => {
    void refreshUser()
    // Pick up a background expansion that may already be running (e.g. after a page reload).
    api.syncStatus().then((st) => st.running && setSync(st)).catch(() => {})
  }, [refreshUser])

  // Poll while a background expansion is running.
  useEffect(() => {
    if (!sync?.running) return
    const t = setInterval(async () => {
      try {
        const st = await api.syncStatus()
        setSync(st)
        if (!st.running) {
          clearInterval(t)
          void refreshUser()
          setSyncMsg(st.failed.length ? `${st.failed.length} anime failed to fetch — press Sync again to retry` : `fetched ${st.done} new anime`)
        }
      } catch {
        /* keep polling */
      }
    }, 2000)
    return () => clearInterval(t)
  }, [sync?.running, refreshUser])

  const doSync = async () => {
    setSyncMsg(null)
    const r = await run('Syncing MAL list…', api.sync)
    if (!r) return
    await refreshUser()
    if (r.expanding) setSync({ running: true, total: r.unfetched, done: 0, failed: [], current: null })
    else setSyncMsg(`list synced (${r.synced} entries), nothing new to fetch`)
  }

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
      {!user?.username && <span className="muted">no MAL list synced yet</span>}
      <button className="small" disabled={!!busy || !!sync?.running} onClick={() => void doSync()} title="Re-fetch your MAL list, then fetch any new anime from MAL">
        {sync?.running ? `fetching ${sync.done}/${sync.total}…` : 'Sync list'}
      </button>
      {syncMsg && <span className="muted">{syncMsg}</span>}
      {busy && <span className="busy">⏳ {busy}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  )
}
