import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Loading, enumLabel, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

export default function CompanySettings() {
  const { t } = useI18n()
  const toast = useToast()
  const [form, setForm] = useState(null)
  const [newKey, setNewKey] = useState('')

  const load = () => api('/company/settings').then(setForm).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  if (!form) return <Loading />
  const toggleLang = l => setForm(f => ({ ...f,
    languages: f.languages.includes(l) ? f.languages.filter(x => x !== l) : [...f.languages, l] }))

  return (
    <>
      <div className="page-head"><h1>{t('Configuración')}</h1>
        <div className="sub">{t('Identidad del bot y conexión con DeepSeek.')}</div></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="panel">
          <div className="panel-head"><h3>{t('Identidad del chatbot')}</h3></div>
          <div className="panel-body">
            <div className="field"><label>{t('Nombre del asistente')}</label>
              <input value={form.bot_name}
                onChange={e => setForm(f => ({ ...f, bot_name: e.target.value }))} /></div>
            <div className="field"><label>{t('Mensaje de bienvenida')}</label>
              <textarea rows={2} value={form.welcome_message}
                onChange={e => setForm(f => ({ ...f, welcome_message: e.target.value }))} /></div>
            <div className="field"><label>{t('Idiomas del bot')}</label>
              <div style={{ display: 'flex', gap: 14 }}>
                {['es', 'en', 'pt'].map(l => (
                  <label key={l} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <input type="checkbox" checked={form.languages.includes(l)}
                      onChange={() => toggleLang(l)} />{l.toUpperCase()}
                  </label>
                ))}
              </div>
              <div className="hint">{t('El bot responde en el idioma en que escribe el usuario.')}</div></div>
            <div className="field"><label>{t('Color del widget')}</label>
              <input type="color" value={form.widget_color} style={{ width: 64, height: 36, padding: 2 }}
                onChange={e => setForm(f => ({ ...f, widget_color: e.target.value }))} /></div>
            <button className="btn btn-primary" onClick={async () => {
              try {
                await api('/company/settings', { method: 'PATCH', body: {
                  bot_name: form.bot_name, welcome_message: form.welcome_message,
                  languages: form.languages, widget_color: form.widget_color } })
                toast(t('Identidad guardada'))
              } catch (e) { toast(errText(e)) } }}>{t('Guardar')}</button>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h3>{t('Conexión DeepSeek')}</h3>
            <Badge kind={form.deepseek_key_status === 'valid' ? 'ok' : 'warn'}>
              {enumLabel(form.deepseek_key_status)}</Badge></div>
          <div className="panel-body">
            <div className="field"><label>{t('API key actual')}</label>
              <input value={form.deepseek_key_masked || t('sin configurar')} readOnly /></div>
            <div className="field"><label>{t('Reemplazar API key')}</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input style={{ flex: 1 }} value={newKey} onChange={e => setNewKey(e.target.value)}
                  placeholder="sk-…" />
                <button className="btn btn-soft" onClick={async () => {
                  try {
                    await api('/company/settings/deepseek-key', { method: 'PUT',
                      body: { api_key: newKey } })
                    setNewKey(''); toast(t('API key guardada (cifrada)')); load()
                  } catch (e) { toast(errText(e)) } }}>{t('Guardar')}</button>
                <button className="btn btn-ghost" onClick={async () => {
                  try { await api('/company/settings/deepseek-key/validate', { method: 'POST' })
                    toast(t('API key válida ✔')); load()
                  } catch (e) { toast(errText(e)) } }}>{t('Validar')}</button>
              </div>
              <div className="hint">{t('Se almacena cifrada; nunca se expone al navegador ni al chat.')}</div></div>
            <div className="field"><label>{t('Consumo del mes')}</label>
              <div className="progress" style={{ height: 10 }}>
                <i style={{ width: `${Math.min(100, form.token_usage.pct)}%` }} /></div>
              <div className="hint">{t('{used} de {limit} tokens ({pct}%)', {
                used: form.token_usage.used.toLocaleString(),
                limit: form.token_usage.limit.toLocaleString(),
                pct: form.token_usage.pct })}</div></div>
          </div>
        </div>
      </div>
    </>
  )
}
