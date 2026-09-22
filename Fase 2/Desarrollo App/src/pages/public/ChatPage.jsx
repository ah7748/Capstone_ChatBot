import { useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import { errText } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

/** Chat público del usuario final (/c/{slug}).
 *  Con ?embed=1 corre dentro del iframe del widget y habla con la página anfitriona
 *  por postMessage (identify, open/close, eventos). */
export default function ChatPage() {
  const { slug } = useParams()
  const [params] = useSearchParams()
  const embed = params.get('embed') === '1'
  const { t } = useI18n()
  const [session, setSession] = useState(null)   // {session_id, session_token, config, ws_url}
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [status, setStatus] = useState('bot')    // bot|escalated|closed
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const bodyRef = useRef(null)
  const identifyRef = useRef(null)

  useEffect(() => {
    (async () => {
      try {
        const s = await api(`/public/chat/${slug}/sessions`, { method: 'POST', body: {
          lang: params.get('lang') || undefined,
          page_url: embed ? document.referrer : window.location.href,
          user: identifyRef.current || undefined,
        } })
        setSession(s)
        setMessages([{ message_id: 'w', role: 'bot', content: s.config.welcome_message }])
        connectWs(s)
        window.parent?.postMessage({ allox: 'session', session_id: s.session_id }, '*')
      } catch (e) { setError(errText(e)) }
    })()
    const onMsg = (ev) => {
      if (ev.data?.allox === 'identify') identifyRef.current = ev.data.user
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  function connectWs(s) {
    try {
      const ws = new WebSocket(`${s.ws_url}?token=${s.session_token}`)
      ws.onmessage = (ev) => {
        const { event, data } = JSON.parse(ev.data)
        if (event === 'message.agent') {
          push({ role: 'agent', content: data.content, agent_name: data.agent_name })
        } else if (event === 'agent.joined') {
          push({ role: 'system', content: `${data.agent_name} se unió a la conversación` })
        } else if (event === 'escalation.update') {
          window.parent?.postMessage({ allox: 'escalated', mode: data.mode }, '*')
        } else if (event === 'session.closed') {
          setStatus('closed')
        }
      }
    } catch { /* el chat sigue por REST */ }
  }

  const push = (m) => setMessages(ms => [...ms, { message_id: Math.random().toString(36), ...m }])

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages])

  async function send() {
    if (!text.trim() || !session || busy) return
    const content = text
    setText(''); push({ role: 'user', content }); setBusy(true)
    try {
      const r = await api(`/public/chat/sessions/${session.session_id}/messages`, {
        method: 'POST', body: { content }, token: session.session_token })
      if (r.bot_reply) push({ role: 'bot', content: r.bot_reply.content })
      if (r.escalation) handleEscalation(r.escalation)
      window.parent?.postMessage({ allox: 'message' }, '*')
    } catch (e) {
      push({ role: 'system', content: errText(e) })
    } finally { setBusy(false) }
  }

  function handleEscalation(esc) {
    setStatus('escalated')
    push({ role: 'system', content: esc.mode === 'live'
      ? `Te estamos conectando con una persona (posición ${esc.queue_position})…`
      : `Creamos el ticket #${esc.ticket_number}: te responderemos por este mismo chat.` })
  }

  async function escalate() {
    try {
      const r = await api(`/public/chat/sessions/${session.session_id}/escalate`, {
        method: 'POST', body: {}, token: session.session_token })
      handleEscalation(r)
    } catch (e) { push({ role: 'system', content: errText(e) }) }
  }

  async function rate(rating) {
    try {
      await api(`/public/chat/sessions/${session.session_id}/rating`, {
        method: 'POST', body: { rating }, token: session.session_token })
      push({ role: 'system', content: '¡Gracias por tu valoración!' })
      setStatus('rated')
    } catch (e) { push({ role: 'system', content: errText(e) }) }
  }

  if (error) return <div className="center" style={{ minHeight: '100vh' }}>{error}</div>
  if (!session) return <div className="center" style={{ minHeight: '100vh' }}>…</div>
  const color = session.config.widget_color || '#00a79d'

  return (
    <div className={`pchat ${embed ? 'embed' : ''}`}>
      <div className="pchat-head" style={{
        background: `linear-gradient(120deg, var(--navy) 0%, var(--navy-2) 55%, ${color} 130%)` }}>
        <b>{session.config.bot_name}</b>
        <span>Asistente virtual · en línea</span>
      </div>
      <div className="pchat-body" ref={bodyRef}>
        {messages.map(m => m.role === 'system' ? (
          <div key={m.message_id} className="sysline">— {m.content} —</div>
        ) : (
          <div key={m.message_id} className={`msg ${m.role}`}
            style={m.role === 'user' ? { background: color } : undefined}>
            {m.role === 'agent' && <span className="who">{m.agent_name}</span>}
            {m.content}
          </div>
        ))}
        {busy && <div className="sysline">escribiendo…</div>}
      </div>
      {status === 'closed' ? (
        <div className="pchat-actions" style={{ padding: 12, justifyContent: 'center' }}>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>¿Cómo estuvo la atención?</span>
          <button className="btn btn-soft btn-sm" onClick={() => rate('up')}>👍</button>
          <button className="btn btn-soft btn-sm" onClick={() => rate('down')}>👎</button>
        </div>
      ) : status !== 'rated' && (
        <>
          <div className="pchat-foot">
            <input value={text} onChange={e => setText(e.target.value)}
              placeholder={t('Escribe tu consulta…')}
              onKeyDown={e => e.key === 'Enter' && send()} />
            <button className="send" style={{ background: color }} onClick={send}>➤</button>
          </div>
          {status === 'bot' && (
            <div className="pchat-actions">
              <button className="btn btn-ghost btn-sm" onClick={escalate}>
                🧑‍💼 {t('Hablar con una persona')}</button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
