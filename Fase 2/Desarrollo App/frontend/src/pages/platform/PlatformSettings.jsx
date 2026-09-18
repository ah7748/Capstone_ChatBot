import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Loading, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

export default function PlatformSettings() {
  const { t } = useI18n()
  const toast = useToast()
  const [form, setForm] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api('/platform/settings').then(setForm).catch(e => toast(errText(e))) }, [])

  async function save() {
    setBusy(true)
    try {
      setForm(await api('/platform/settings', { method: 'PATCH', body: form }))
      toast('Configuración guardada')
    } catch (e) { toast(errText(e)) } finally { setBusy(false) }
  }

  if (!form) return <Loading t={t} />
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'number'
    ? Number(e.target.value) : e.target.value }))
  return (
    <>
      <div className="page-head"><h1>{t('Configuración')}</h1>
        <div className="sub">Valores por defecto de la plataforma; cada empresa puede sobreescribirlos.</div>
      </div>
      <div className="panel"><div className="panel-body" style={{ maxWidth: 560 }}>
        <div className="field"><label>Modelo LLM por defecto</label>
          <select value={form.default_model} onChange={set('default_model')}>
            <option value="deepseek-chat">DeepSeek Chat</option>
            <option value="deepseek-reasoner">DeepSeek Reasoner</option>
          </select></div>
        <div className="field"><label>Umbral de derivación (intentos sin resolución)</label>
          <input type="number" min={1} max={5} value={form.escalation_threshold}
            onChange={set('escalation_threshold')} /></div>
        <div className="field"><label>Límite mensual de tokens por empresa</label>
          <input type="number" value={form.default_token_limit_month}
            onChange={set('default_token_limit_month')} /></div>
        <div className="field"><label>% de consumo que dispara alerta</label>
          <input type="number" min={1} max={100} value={form.alert_pct} onChange={set('alert_pct')} /></div>
        <button className="btn btn-primary" disabled={busy} onClick={save}>{t('Guardar')}</button>
      </div></div>
    </>
  )
}
