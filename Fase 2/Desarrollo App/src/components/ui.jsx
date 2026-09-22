import { createContext, useCallback, useContext, useRef, useState } from 'react'

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

export const Loading = ({ t }) => <div className="center">{t ? t('Cargando…') : 'Cargando…'}</div>

export function errText(e) {
  return e?.message ? `${e.message}${e.code ? ` (${e.code})` : ''}` : 'Error inesperado'
}

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
