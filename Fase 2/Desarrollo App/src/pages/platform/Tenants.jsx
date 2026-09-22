import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Loading, Modal, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'
import TenantModal from './TenantModal'

const EMPTY = { name: '', slug: '', legal_name: '', tax_id: '', country: 'CL',
  language: 'es', admin_email: '', deepseek_api_key: '' }

export default function Tenants() {
  const { t } = useI18n()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [openTenant, setOpenTenant] = useState(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [busy, setBusy] = useState(false)

  const load = () => api('/platform/tenants?page_size=100').then(setData).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  async function create() {
    setBusy(true)
    try {
      const r = await api('/platform/tenants', { method: 'POST', body: form })
      toast(`Empresa creada · ${r.chat_url} · invitación enviada`)
      setCreating(false); setForm(EMPTY); load()
    } catch (e) { toast(errText(e)) } finally { setBusy(false) }
  }

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  if (!data) return <Loading t={t} />
  return (
    <>
      <div className="page-head">
        <h1>{t('Empresas cliente')}</h1>
        <div className="spacer" />
        <button className="btn btn-primary" onClick={() => setCreating(true)}>+ {t('Nueva empresa')}</button>
      </div>
      <div className="panel">
        <table>
          <thead><tr>
            <th>Empresa</th><th>API key</th><th>Base de conocimiento</th>
            <th>Enlace de chat</th><th>WhatsApp</th><th>{t('Estado')}</th><th></th>
          </tr></thead>
          <tbody>
            {data.items.map(row => (
              <tr key={row.tenant_id}>
                <td><b>{row.name}</b><br /><span style={{ color: 'var(--muted)', fontSize: 12 }}>{row.slug}</span></td>
                <td><Badge kind={row.deepseek_key_status === 'valid' ? 'ok' : 'warn'}>{row.deepseek_key_status}</Badge></td>
                <td>{row.kb_summary.documents} docs · {row.kb_summary.faqs} FAQ · sitio {row.kb_summary.website_ok ? '✔' : '—'}</td>
                <td><code style={{ fontSize: 12 }}>{row.chat_url}</code></td>
                <td><Badge kind={row.whatsapp_status === 'connected' ? 'ok' : 'off'}>{row.whatsapp_status}</Badge></td>
                <td><Badge kind={row.status === 'active' ? 'ok' : 'warn'}>{row.status}</Badge></td>
                <td><button className="btn btn-soft btn-sm"
                  onClick={() => setOpenTenant(row.tenant_id)}>{t('Gestionar')}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {openTenant && <TenantModal tenantId={openTenant} onClose={() => setOpenTenant(null)} />}
      {creating && (
        <Modal title={t('Nueva empresa')} onClose={() => setCreating(false)} footer={<>
          <button className="btn btn-soft" onClick={() => setCreating(false)}>{t('Cancelar')}</button>
          <button className="btn btn-primary" disabled={busy} onClick={create}>
            {busy ? '…' : 'Crear empresa'}</button>
        </>}>
          <div className="field"><label>Nombre</label>
            <input value={form.name} onChange={set('name')} placeholder="Acme Corp" /></div>
          <div className="field"><label>Slug (soporte.allox.ai/…)</label>
            <input value={form.slug} onChange={set('slug')} placeholder="acme" /></div>
          <div className="field"><label>Razón social</label>
            <input value={form.legal_name} onChange={set('legal_name')} /></div>
          <div className="field"><label>RUT / ID fiscal</label>
            <input value={form.tax_id} onChange={set('tax_id')} /></div>
          <div className="field"><label>País (ISO-2)</label>
            <input value={form.country} onChange={set('country')} maxLength={2} /></div>
          <div className="field"><label>Idioma principal</label>
            <select value={form.language} onChange={set('language')}>
              <option value="es">Español</option><option value="en">Inglés</option>
              <option value="pt">Portugués</option>
            </select></div>
          <div className="field"><label>Email del administrador</label>
            <input type="email" value={form.admin_email} onChange={set('admin_email')} />
            <div className="hint">Recibirá la invitación para configurar el chatbot.</div></div>
          <div className="field"><label>API key de DeepSeek</label>
            <input value={form.deepseek_api_key} onChange={set('deepseek_api_key')} placeholder="sk-…" />
            <div className="hint">Se almacena cifrada; una clave por empresa.</div></div>
        </Modal>
      )}
    </>
  )
}
