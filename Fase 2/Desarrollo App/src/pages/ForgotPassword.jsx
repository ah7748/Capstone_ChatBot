import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import LangSwitch from '../components/LangSwitch'
import { errText } from '../components/ui'
import { useI18n } from '../context/I18nContext'

export default function ForgotPassword() {
  const { t } = useI18n()
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      await api('/auth/password/reset-request', { method: 'POST', body: { email: email.trim() } })
      setSent(true)
    } catch (err) { setError(errText(err)) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <LangSwitch />
        <div className="logo-fallback" style={{ color: 'var(--heading)', marginBottom: 18 }}>
          allo<span>x</span>entric
        </div>
        <h1>{t('Recuperar contraseña')}</h1>
        {sent ? (
          <div className="sub">{t('Si el correo está registrado, recibirás un enlace para crear una nueva contraseña.')}</div>
        ) : (<>
          <div className="sub">{t('Te enviaremos un enlace para crear una nueva contraseña.')}</div>
          {error && <div className="login-error">{error}</div>}
          <div className="field"><label>{t('Correo electrónico')}</label>
            <input type="email" required value={email} onChange={e => setEmail(e.target.value)}
              placeholder={t('tu@empresa.com')} autoFocus /></div>
          <button className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
            {busy ? '…' : t('Enviar enlace')}</button>
        </>)}
        <div style={{ marginTop: 14, textAlign: 'center', fontSize: 13 }}>
          <Link to="/login">{t('Volver a iniciar sesión')}</Link>
        </div>
      </form>
    </div>
  )
}