import { marked } from 'marked'
import { useEffect, useRef, useState } from 'react'
import { api, ask, type AskEvent, type ConversationSummary, type GNode } from '../api'
import { useStore } from '../store'
import { navigate } from '../useHashRoute'

interface Turn {
  role: 'user' | 'assistant'
  text: string
  steps: { name: string; args: Record<string, unknown>; error?: string }[]
  cards: { title: string; cards: { node: GNode; caption: string }[] }[]
  usage?: { prompt_tokens: number; completion_tokens: number; cached_tokens?: number } | null
  error?: string | null
  notice?: string
}

const when = (t: number) => {
  const d = new Date(t * 1000)
  const days = (Date.now() - d.getTime()) / 86400000
  return days < 1 ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : days < 7 ? d.toLocaleDateString([], { weekday: 'short' }) : d.toLocaleDateString()
}

const TOOL_LABELS: Record<string, string> = {
  search: 'searching',
  node: 'reading',
  neighbors: 'expanding',
  shortest_path: 'finding path',
  va_roles: 'listing roles',
  roster: 'ranking voice actors',
  people: 'ranking people',
  gaps: 'checking gaps',
  cypher_read: 'querying graph',
  show_on_canvas: 'drawing on canvas',
  present_cards: 'preparing cards',
}

const EXAMPLES = [
  'Pick a voice actor with at least 3 main roles I have seen and give me 3 of their characters from different genres',
  'How is Takehito Koyasu connected to Studio Bones through anime I have watched?',
  'Which sequels of shows I rated 9+ have I not seen yet?',
  'Show me the characters voiced by Rie Kugimiya in anime I have completed',
]

function argSummary(name: string, args: Record<string, unknown>): string {
  if (name === 'cypher_read') return String(args.query ?? '').replace(/\s+/g, ' ').slice(0, 120)
  const v = args.q ?? args.ref ?? args.person_id ?? (args.from_ref && `${args.from_ref} → ${args.to_ref}`) ?? args.kind ?? ''
  return String(v)
}

export function AskPanel() {
  const [status, setStatus] = useState<{ configured: boolean; model: string | null } | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<ConversationSummary[] | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [title, setTitle] = useState('')
  const sessionRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const mergePayload = useStore((s) => s.mergePayload)
  const select = useStore((s) => s.select)

  useEffect(() => {
    api.askStatus().then(setStatus).catch(() => setStatus({ configured: false, model: null }))
  }, [])
  const refreshHistory = () => api.conversations().then((r) => setHistory(r.conversations)).catch(() => {})
  useEffect(() => {
    if (showHistory) void refreshHistory()
  }, [showHistory])

  const openConversation = async (id: string) => {
    const c = await api.conversation(id)
    sessionRef.current = c.id
    setTitle(c.title)
    setTurns(c.turns.map((t) => ({ ...t, usage: t.usage ?? undefined, error: t.error ?? undefined })))
    setShowHistory(false)
  }
  const newChat = () => {
    setTurns([])
    setTitle('')
    sessionRef.current = null
    setShowHistory(false)
  }
  const rename = async () => {
    const id = sessionRef.current
    if (!id) return
    const next = window.prompt('Conversation title', title)
    if (next == null) return
    const r = await api.renameConversation(id, next)
    setTitle(r.title)
  }
  const remove = async (id: string) => {
    await api.deleteConversation(id)
    if (sessionRef.current === id) newChat()
    void refreshHistory()
  }
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  const send = async (text: string) => {
    const q = text.trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)
    const assistant: Turn = { role: 'assistant', text: '', steps: [], cards: [] }
    setTurns((t) => [...t, { role: 'user', text: q, steps: [], cards: [] }, assistant])
    const update = (fn: (a: Turn) => void) =>
      setTurns((t) => {
        const copy = t.slice()
        const last = { ...copy[copy.length - 1] }
        fn(last)
        copy[copy.length - 1] = last
        return copy
      })
    abortRef.current = new AbortController()
    try {
      for await (const ev of ask(q, sessionRef.current, abortRef.current.signal)) handle(ev, update)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') update((a) => (a.error = (e as Error).message))
    } finally {
      setBusy(false)
      abortRef.current = null
      if (!title) setTitle(q.slice(0, 80))
    }
  }

  const handle = (ev: AskEvent, update: (fn: (a: Turn) => void) => void) => {
    switch (ev.type) {
      case 'session':
        if (sessionRef.current && !ev.resumed) update((a) => (a.notice = 'earlier context was lost — answering from scratch'))
        sessionRef.current = ev.id
        break
      case 'tool_call':
        update((a) => (a.steps = [...a.steps, { name: ev.name, args: ev.args }]))
        break
      case 'tool_error':
        update((a) => {
          const steps = a.steps.slice()
          const i = steps.map((s) => s.name).lastIndexOf(ev.name)
          if (i >= 0) steps[i] = { ...steps[i], error: ev.message }
          a.steps = steps
        })
        break
      case 'canvas':
        mergePayload(ev.payload)
        if (ev.payload.select) select(ev.payload.select)
        break
      case 'cards':
        update((a) => (a.cards = [...a.cards, { title: ev.title, cards: ev.cards }]))
        break
      case 'answer':
        update((a) => (a.text = ev.text))
        break
      case 'error':
        update((a) => (a.error = ev.message))
        break
      case 'done':
        update((a) => (a.usage = ev.usage))
        break
    }
  }

  const openCard = (n: GNode) => {
    mergePayload({ nodes: [n], edges: [] })
    select(n.id)
    if (window.location.hash.startsWith('#/ask')) navigate('/')
  }

  if (status && !status.configured) {
    return (
      <div className="panel muted">
        <h2>Ask the graph</h2>
        Not configured — set <code>OPENROUTER_API_KEY</code> (and optionally <code>OPENROUTER_MODEL</code>) in the server's <code>.env</code> and restart the API.
      </div>
    )
  }

  return (
    <div className="ask">
      <div className="ask-head">
        <button className="small" onClick={() => setShowHistory((v) => !v)} title="Saved conversations">
          {showHistory ? '← back' : 'history'}
        </button>
        {!showHistory && turns.length > 0 && (
          <>
            <button className="link ask-title" onClick={() => void rename()} title="Rename">
              {title || 'untitled'}
            </button>
            <button className="small" onClick={newChat}>
              new chat
            </button>
          </>
        )}
      </div>
      {showHistory ? (
        <div className="ask-log">
          {history === null && <div className="muted">loading…</div>}
          {history?.length === 0 && <div className="muted">No saved conversations yet — every chat is saved automatically.</div>}
          {history?.map((c) => (
            <div key={c.id} className={`conv ${c.id === sessionRef.current ? 'active' : ''}`}>
              <button className="link conv-title" onClick={() => void openConversation(c.id)}>
                {c.title}
              </button>
              <span className="muted">
                {when(c.updated_at)} · {Math.floor(c.turns / 2)} q
              </span>
              <button className="small" onClick={() => void remove(c.id)} title="Delete">
                ×
              </button>
            </div>
          ))}
        </div>
      ) : (
      <div className="ask-log">
        {turns.length === 0 && (
          <div className="ask-empty">
            <h2>Ask the graph</h2>
            <p className="muted">
              Natural-language questions, answered by exploring the graph{status?.model ? ` (${status.model})` : ''}. Results can be drawn on the canvas or shown as cards.
            </p>
            {EXAMPLES.map((e) => (
              <button key={e} className="example" onClick={() => void send(e)}>
                {e}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) =>
          t.role === 'user' ? (
            <div key={i} className="msg user">
              {t.text}
            </div>
          ) : (
            <div key={i} className="msg assistant">
              {t.steps.length > 0 && (
                <details className="steps" open={!t.text && !t.error}>
                  <summary>
                    {t.steps.length} step{t.steps.length > 1 ? 's' : ''}
                    {!t.text && !t.error && busy && i === turns.length - 1 ? ` · ${TOOL_LABELS[t.steps[t.steps.length - 1].name] ?? t.steps[t.steps.length - 1].name}…` : ''}
                  </summary>
                  <ol>
                    {t.steps.map((s, j) => (
                      <li key={j} className={s.error ? 'error' : ''}>
                        <b>{TOOL_LABELS[s.name] ?? s.name}</b> <code>{argSummary(s.name, s.args)}</code>
                        {s.error && <div className="error">{s.error}</div>}
                      </li>
                    ))}
                  </ol>
                </details>
              )}
              {t.cards.map((group, j) => (
                <div key={j} className="ask-cards">
                  {group.title && <div className="muted">{group.title}</div>}
                  <div className="roster-grid people">
                    {group.cards.map((c) => (
                      <button key={c.node.id} className="card" onClick={() => openCard(c.node)} title="Open in graph">
                        {c.node.image_url ? <img src={c.node.image_url} alt="" /> : <div className="noimg" />}
                        <div className="card-body">
                          <strong>{c.node.name}</strong>
                          {c.caption && <span className="muted">{c.caption}</span>}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {t.text && <div className="md" dangerouslySetInnerHTML={{ __html: marked.parse(t.text, { async: false }) as string }} />}
              {t.error && <div className="error">{t.error}</div>}
              {t.notice && <div className="muted" style={{ fontSize: 11 }}>{t.notice}</div>}
              {!t.text && !t.error && t.steps.length === 0 && busy && i === turns.length - 1 && <div className="muted">thinking…</div>}
              {t.usage && (
                <div className="usage muted">
                  {t.usage.prompt_tokens.toLocaleString()} in
                  {t.usage.cached_tokens ? ` (${Math.round((100 * t.usage.cached_tokens) / Math.max(1, t.usage.prompt_tokens))}% cached)` : ''} · {t.usage.completion_tokens.toLocaleString()} out
                </div>
              )}
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>
      )}
      <form
        className="ask-input"
        onSubmit={(e) => {
          e.preventDefault()
          void send(input)
        }}
      >
        <textarea
          value={input}
          placeholder="Ask about your anime, characters, voice actors…"
          rows={2}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void send(input)
            }
          }}
        />
        {busy ? (
          <button type="button" onClick={() => abortRef.current?.abort()}>
            stop
          </button>
        ) : (
          <button type="submit" disabled={!input.trim()}>
            ask
          </button>
        )}
      </form>
    </div>
  )
}
