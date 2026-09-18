import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getTokens, wsUrl } from '../../api/client'
import { Badge, CHAT_TYPE_BADGE, Loading, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'
import { Topbar } from '../../components/Layout'
import { useAuth } from '../../context/AuthContext'

export default function Console() {
  const { t } = useI18n()
  const { user } = useAuth()
  const toast = useToast()
  const [queueType, setQueueType] = useState('live')
  const [queue, setQueue] = useState(null)
  const [current, setCurrent] = useState(null) // detalle de conversación
  const [suggestions, setSuggestions] = useState([])
  const [text, setText] = useState('')
  const bodyRef = useRef(null)
  const wsRef = useRef(null)

  const loadQueue = useCallback(() => {
    api(`/agent/queue?type=${queueType}&page_size=50`).then(setQueue).catch(e => toast(errText(e)))
  }, [queueType])

  const loadConvo = useCallback(async (id) => {
    try {
      const d = await api(`/agent/conversations/${id}`)
      setCurrent(d)
      setSuggestions([])
      api(`/agent/conversations/${id}/suggestions`)
        .then(r => setSuggestions(r.suggestions)).catch(() => setSuggestions([]))
    } catch (e) { toast(errText(e)) }
  }, [])

  useEffect(() => { loadQueue() }, [loadQueue])

  // presencia disponible al entrar + WebSocket de la consola
  useEffect(() => {
    api('/agent/presence', { method: 'PATCH', body: { presence: 'available' } }).catch(() => {})
    const ws = new WebSocket(wsUrl(`/ws/agent?token=${getTokens().access}`))
    wsRef.current = ws
    ws.onmessage = (ev) => {
      const { event } = JSON.parse(ev.data)
      if (event === 'queue.updated') loadQueue()
      if (event === 'message.user' && current) loadConvo(current.conversation.conversation_id)
    }
    return () => ws.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [current])

  async function act(action, body = {}) {
    const id = current.conversation.conversation_id
    try {
      await api(`/agent/conversations/${id}/${action}`, { method: 'POST', body })
      await loadConvo(id); loadQueue()
    } catch (e) { toast(errText(e)) }
  }

  async function send() {
    if (!text.trim()) return
    const id = current.conversation.conversation_id
    try {
      if (!current.claimed_by) await api(`/agent/conversations/${id}/claim`, { method: 'POST' })
      await api(`/agent/conversations/${id}/messages`, { method: 'POST', body: { content: text } })
      setText('')
      await loadConvo(id)
    } catch (e) { toast(errText(e)) }
  }

  const c = current?.conversation
  return (
    <>
      <Topbar />
      <div className="agent-app">
        {/* Cola */}
        <aside className="queue">
          <div className="queue-head">
            <h2>Bandeja de soporte</h2>
            <div className="tabs" style={{ marginBottom: 0 }}>
              <button className={`tab ${queueType === 'live' ? 'active' : ''}`}
                onClick={() => setQueueType('live')}>
                🔴 {t('En vivo')} {queue ? `(${queue.counts.live})` : ''}</button>
              <button className={`tab ${queueType === 'tickets' ? 'active' : ''}`}
                onClick={() => setQueueType('tickets')}>
                🎫 Tickets {queue ? `(${queue.counts.tickets})` : ''}</button>
            </div>
          </div>
          {!queue ? <Loading t={t} /> : queue.items.map(item => {
            const [ck, cl] = CHAT_TYPE_BADGE[item.chat_type] || ['off', item.chat_type]
            const id = item.conversation_id
            return (
              <button key={item.ticket_id || id}
                className={`q-item ${c?.conversation_id === id ? 'active' : ''}`}
                onClick={() => loadConvo(id)}>
                <div className="q-top">
                  <span className="name">{item.number ? `#${item.number} · ` : ''}{item.user_name}</span>
                  <span className="time">{new Date(item.waiting_since).toLocaleTimeString()}</span>
                </div>
                <div className="q-prev">{item.preview}</div>
                <div className="q-meta">
                  <Badge kind="navy">{item.channel}</Badge>
                  <Badge kind={ck}>{cl}</Badge>
                  {item.assigned_to && <Badge kind="ok">{item.assigned_to}</Badge>}
                </div>
              </button>
            )
          })}
        </aside>

        {/* Conversación */}
        <section className="convo">
          {!current ? <div className="center">Selecciona una conversación de la bandeja</div> : (
            <>
              <div className="convo-head">
                <h3>{current.user.name || 'Usuario'}</h3>
                <Badge kind="navy">{c.channel}</Badge>
                <Badge kind={CHAT_TYPE_BADGE[c.chat_type][0]}>{CHAT_TYPE_BADGE[c.chat_type][1]}</Badge>
                <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                  {current.claimed_by ? `Atendida por ${current.claimed_by}` : 'Esperando agente'}
                </span>
                <div className="spacer" />
                {!current.claimed_by && (
                  <button className="btn btn-primary btn-sm" onClick={() => act('claim')}>
                    {t('Tomar conversación')}</button>
                )}
                <button className="btn btn-ghost btn-sm" onClick={() => act('release', {})}>
                  {t('Devolver al bot')}</button>
                <button className="btn btn-soft btn-sm" onClick={() => act('resolve', {})}>
                  ✓ {t('Resolver')}</button>
              </div>
              <div className="convo-body" ref={bodyRef}>
                {current.messages.map(m => m.role === 'system' ? (
                  <div key={m.message_id} className="sysline">— {m.content} —</div>
                ) : (
                  <div key={m.message_id} className={`msg ${m.role}`}>
                    <span className="who">{m.role === 'agent' ? m.agent_name : m.role}</span>
                    {m.content}
                  </div>
                ))}
              </div>
              <div className="convo-foot">
                <div className="reply-row">
                  <textarea value={text} onChange={e => setText(e.target.value)}
                    placeholder="Escribe tu respuesta al usuario…"
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
                  <button className="btn btn-primary" onClick={send}>{t('Enviar')} ➤</button>
                </div>
              </div>
            </>
          )}
        </section>

        {/* Contexto */}
        <aside className="ctx">
          {current && (
            <>
              <h4>Contexto de la derivación</h4>
              <div className="ctx-card">
                <div className="kv"><span>{t('Motivo')}</span><b>{current.context.escalation_reason || '—'}</b></div>
                <div className="kv"><span>Tema</span><b>{current.context.topic || '—'}</b></div>
                <div className="kv"><span>Agente del bot</span>
                  <b>{current.context.bot_agent_type === 'technical' ? '🛠️ Técnico' : '💼 Comercial'}</b></div>
              </div>
              <h4>{t('Usuario')}</h4>
              <div className="ctx-card">
                <div className="kv"><span>Nombre</span><b>{current.user.name || '—'}</b></div>
                <div className="kv"><span>Email</span><b>{current.user.email || '—'}</b></div>
                <div className="kv"><span>Conversaciones previas</span>
                  <b>{current.user.previous_conversations}</b></div>
              </div>
              <h4>{t('Respuestas sugeridas (IA)')}</h4>
              {suggestions.map(s => (
                <div key={s.suggestion_id} className="sugg">
                  <div className="src">⚡ RAG · {s.source_document}</div>
                  {s.content}
                  <div style={{ marginTop: 8 }}>
                    <button className="btn btn-ghost btn-sm"
                      onClick={() => setText(s.content)}>{t('Usar respuesta')}</button>
                  </div>
                </div>
              ))}
              {suggestions.length === 0 && (
                <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>Sin sugerencias por ahora.</div>
              )}
            </>
          )}
        </aside>
      </div>
    </>
  )
}
