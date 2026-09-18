import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Loading, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

export default function Channels() {
  const { t } = useI18n()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [domains, setDomains] = useState('')
  const [esc, setEsc] = useState(null)

  const load = () => api('/company/channels').then(d => {
    setData(d); setDomains(d.web.allowed_domains.join(', ')); setEsc(d.escalation)
  }).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  if (!data || !esc) return <Loading t={t} />
  const copy = (text, label) => { navigator.clipboard?.writeText(text); toast(`${label} copiado`) }

  return (
    <>
      <div className="page-head"><h1>{t('Canales del chat')}</h1>
        <div className="sub">Enlace único, widget embebible, WhatsApp y reglas de derivación.</div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 20 }}>
        <div>
          <div className="panel">
            <div className="panel-head"><h3>💻 Chat web</h3>
              <Badge kind={data.web.published ? 'ok' : 'off'}>
                {data.web.published ? 'Publicado' : 'No publicado'}</Badge></div>
            <div className="panel-body">
              <div className="field"><label>Enlace único del chat</label>
                <div className="linkbox"><code>{data.web.chat_url}</code>
                  <button className="btn btn-primary btn-sm"
                    onClick={() => copy(data.web.chat_url, 'Enlace')}>Copiar</button></div></div>
              <div className="field"><label>Widget embebible</label>
                <div className="linkbox"><code>{data.web.widget_snippet}</code>
                  <button className="btn btn-primary btn-sm"
                    onClick={() => copy(data.web.widget_snippet, 'Snippet')}>Copiar</button></div></div>
              <div className="field"><label>Dominios autorizados a embeber el widget</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input style={{ flex: 1 }} value={domains} onChange={e => setDomains(e.target.value)}
                    placeholder="www.miempresa.com, *.miempresa.com" />
                  <button className="btn btn-soft" onClick={async () => {
                    try {
                      await api('/company/channels/web', { method: 'PATCH', body: {
                        allowed_domains: domains.split(',').map(d => d.trim()).filter(Boolean) } })
                      toast('Dominios guardados'); load()
                    } catch (e) { toast(errText(e)) } }}>{t('Guardar')}</button>
                </div>
                <div className="hint">Lista vacía = el chat solo funciona desde su enlace directo.</div>
              </div>
            </div>
          </div>
          <div className="panel">
            <div className="panel-head"><h3>📱 WhatsApp</h3>
              <Badge kind={data.whatsapp.connected ? 'ok' : 'off'}>
                {data.whatsapp.connected ? `Conectado ${data.whatsapp.phone_masked || ''}` : 'No conectado'}
              </Badge></div>
            <div className="panel-body" style={{ fontSize: 13, color: 'var(--muted)' }}>
              La conexión requiere una cuenta de WhatsApp Business (Meta) con phone_number_id,
              waba_id y token permanente — se configura vía API (POST /company/channels/whatsapp).
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><h3>Derivación a agente humano</h3></div>
          <div className="panel-body">
            <div className="field"><label>Cuándo derivar</label>
              <select value={esc.when} onChange={e => setEsc(x => ({ ...x, when: e.target.value }))}>
                <option value="after_2_failures_or_request">Sin resolución tras 2 intentos o a pedido</option>
                <option value="on_request_only">Solo cuando el usuario lo pide</option>
                <option value="never">Nunca (solo bot)</option>
              </select></div>
            <div className="field"><label>Si no hay agentes disponibles</label>
              <select value={esc.fallback} onChange={e => setEsc(x => ({ ...x, fallback: e.target.value }))}>
                <option value="create_ticket">Crear ticket</option>
                <option value="show_hours">Mostrar horario de atención</option>
              </select></div>
            <button className="btn btn-primary" onClick={async () => {
              try {
                await api('/company/channels/escalation', { method: 'PATCH',
                  body: { when: esc.when, fallback: esc.fallback } })
                toast('Reglas guardadas')
              } catch (e) { toast(errText(e)) } }}>{t('Guardar')}</button>
          </div>
        </div>
      </div>
    </>
  )
}
