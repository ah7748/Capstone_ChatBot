import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { getLang, hasKey, tr } from '../context/I18nContext'

// ---------- Toast ----------
const ToastCtx = createContext(() => {})
export function ToastProvider({ children }) {
  const [msg, setMsg] = useState('')
  const [show, setShow] = useState(false)
  const timer = useRef(null)
  const toast = useCallback((m) => {
    setMsg(m); setShow(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setShow(false), 2800)
  }, [])
  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div id="toast" className={show ? 'show' : ''}>{msg}</div>
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

// ---------- Modal ----------
export function Modal({ title, children, footer, onClose, width }) {
  return (
    <div className="modal-bg" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={width ? { width } : undefined}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="x" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

// ---------- Piezas pequeñas ----------
export const Badge = ({ kind = 'off', children }) => <span className={`badge ${kind}`}>{children}</span>

export const Kpi = ({ label, value, extra, onClick, more }) => (
  <div className={`kpi ${onClick ? 'click' : ''}`} onClick={onClick}>
    <div className="lbl">{label}</div>
    <div className="val">{value}</div>
    {extra && <div style={{ fontSize: 12, color: 'var(--muted)' }}>{extra}</div>}
    {onClick && <div className="more">{more}</div>}
  </div>
)

export const Loading = () => <div className="center">{tr('Cargando…')}</div>

/** Mensaje de error: si el idioma no es ES y hay traducción para el código estable, la usa. */
export function errText(e) {
  if (!e?.message) return tr('Error inesperado')
  const key = `code:${e.code}`
  const msg = getLang() !== 'es' && hasKey(key) ? tr(key) : e.message
  const trace = e.detail?.trace_id ? ` · trace ${e.detail.trace_id}`: ''
  return e.code ? `${msg} (${e.code})` : msg
}

// Valores crudos de la API → etiqueta en español (clave del diccionario)
const ENUM_ES = {
  active: 'Activo', disabled: 'Desactivado', pending: 'Pendiente', invited: 'Invitación enviada',
  done: 'Completado', running: 'En curso', failed: 'Fallido',
  valid: 'Válida', unvalidated: 'Sin validar', rejected: 'Rechazada', missing: 'Sin configurar',
  connected: 'Conectado', not_configured: 'No configurado',
  web: 'Web', whatsapp: 'WhatsApp', preview: 'Vista previa',
  user: 'Usuario', bot: 'Bot', agent: 'Agente', system: 'Sistema',
  queued: 'Esperando', live: 'En vivo', ticket: 'Ticket', resolved: 'Resuelta', abandoned: 'Abandonada',
}
/** Traduce un valor crudo de la API (status, channel, etc.) */
export const enumLabel = (v) => (v == null || v === '' ? '' : tr(ENUM_ES[v] || String(v)))

// Etiquetas en español; las vistas las traducen al renderizar: t(label)
export const STATUS_BADGE = {
  indexed: ['ok', 'Indexado'], queued: ['warn', 'En cola'], processing: ['warn', 'Procesando…'],
  error: ['danger', 'Error'], active: ['ok', 'Activo'], invited: ['warn', 'Invitación enviada'],
  pending: ['warn', 'Pendiente'], disabled: ['off', 'Desactivado'],
  open: ['off', 'Abierto'], resolved: ['ok', 'Resuelta'], live: ['ok', 'En vivo'],
  queued_live: ['warn', 'Esperando'],
}

export const CHAT_TYPE_BADGE = {
  technical: ['navy', '🛠️ Técnico'], commercial: ['brand', '💼 Comercial'],
  both: ['navy', '🛠️💼 Ambos'],
}
