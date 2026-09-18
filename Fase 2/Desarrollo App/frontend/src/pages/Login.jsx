import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { HOME_BY_ROLE, useAuth } from '../context/AuthContext'
import { useI18n } from '../context/I18nContext'
import { errText } from '../components/ui'

/** Login único: el backend devuelve el rol y aquí se redirige a la interfaz correspondiente
 *  (platform_admin → /platform · company_admin → /company · human_agent → /console). */
export default function Login() {
  const { login } = useAuth()
  const { t } = useI18n()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const me = await login(email, password)
      nav(HOME_BY_ROLE[me.role] || '/login', { replace: true })
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="logo-fallback" style={{ color: 'var(--heading)', marginBottom: 18 }}>
          allo<span>x</span>entric
        </div>
        <h1>Chatbot de Soporte Genérico</h1>
        <div className="sub">{t('Iniciar sesión')} · {t('Módulo de administración')}</div>
        {error && <div className="login-error">{error}</div>}
        <div className="field">
          <label>{t('Correo electrónico')}</label>
          <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
            placeholder="tu@empresa.com" autoFocus />
        </div>
        <div className="field">
          <label>{t('Contraseña')}</label>
          <input type="password" required value={password}
            onChange={e => setPassword(e.target.value)} placeholder="••••••••••" />
        </div>
        <button className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? '…' : t('Entrar')}
        </button>
      </form>
    </div>
  )
}
