import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import LangSwitch from '../components/LangSwitch'
import { errText, useToast } from '../components/ui'
import { useI18n } from '../context/I18nContext'
import { isStrongPassword } from '../utils/password'

export default function AcceptInvitation() {
  const { t, setLang } = useI18n()
  const toast = useToast()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // el idioma del correo (?lang=) manda sobre el guardado en el navegador
  useEffect(() => {
    const l = params.get('lang')
    if (l) setLang(l)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function submit(e) {
    e.preventDefault()
    setError(null)
    if (!token) return setError(t('Falta el token de invitación en el enlace.'))
    if (!isStrongPassword(password))
      return setError(t('La contraseña debe tener 10+ caracteres, mayúscula, minúscula y número.'))
    if (password !== confirm) return setError(t('Las contraseñas no coinciden.'))
    setBusy(true)
    try {
      await api('/auth/invitations/accept', { method: 'POST', body: {
        invitation_token: token, password, name: name.trim() || undefined } })
      toast(t('Cuenta activada: ya puedes iniciar sesión'))
      nav('/login', { replace: true })
    } catch (err) { setError(errText(err)) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <LangSwitch />
        <div className="logo-fallback" style={{ color: 'var(--heading)', marginBottom: 18 }}>
          allo<span>x</span>entric
        </div>
        <h1>{t('Activar cuenta')}</h1>
        <div className="sub">{t('Define tu contraseña para activar tu cuenta.')}</div>
        {error && <div className="login-error">{error}</div>}
        <div className="field"><label>{t('Nombre (opcional)')}</label>
          <input value={name} onChange={e => setName(e.target.value)} /></div>
        <div className="field"><label>{t('Contraseña')}</label>
          <input type="password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
        <div className="field"><label>{t('Confirmar contraseña')}</label>
          <input type="password" required value={confirm} onChange={e => setConfirm(e.target.value)} /></div>
        <button className="btn btn-primary" style={{ width: '100%' }} disabled={busy}>
          {busy ? '…' : t('Activar cuenta')}</button>
      </form>
    </div>
  )
}