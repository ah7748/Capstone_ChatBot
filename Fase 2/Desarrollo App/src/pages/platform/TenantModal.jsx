import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Loading, Modal, errText, useToast } from '../../components/ui'
import { PERIOD_OPTIONS, useI18n } from '../../context/I18nContext'

/** Ficha de empresa: datos legales, bots por canal y consumo de tokens con selector de período. */
export default function TenantModal({ tenantId, onClose }) {
  const { t } = useI18n()
  const toast = useToast()
  const [detail, setDetail] = useState(null)
  const [period, setPeriod] = useState('7d')
  const [usage, setUsage] = useState(null)

  useEffect(() => {
    api(`/platform/tenants/${tenantId}`).then(setDetail).catch(e => toast(errText(e)))
  }, [tenantId])

  useEffect(() => {
    api(`/platform/tenants/${tenantId}/usage?period=${period}`)
      .then(setUsage).catch(e => toast(errText(e)))
  }, [tenantId, period])

  if (!detail) return <Modal title="…" onClose={onClose}><Loading t={t} /></Modal>
  const info = detail.tenant
  const fmt = n => n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : n >= 1e3 ? `${Math.round(n / 1e3)} K` : n

  return (
    <Modal title={info.name} width={680} onClose={onClose}
      footer={<button className="btn btn-soft" onClick={onClose}>{t('Cerrar')}</button>}>
      <h4 style={{ fontSize: 12, letterSpacing: 1.2, textTransform: 'uppercase',
        color: 'var(--muted)', marginBottom: 8 }}>{t('Datos de la empresa')}</h4>
      <div className="ctx-card" style={{ marginBottom: 16 }}>
        <div className="kv"><span>Razón social</span><b>{info.legal_name}</b></div>
        <div className="kv"><span>RUT / ID fiscal</span><b>{info.tax_id}</b></div>
        <div className="kv"><span>País</span><b>{info.country}</b></div>
        <div className="kv"><span>Idioma</span><b>{info.language}</b></div>
        <div className="kv"><span>API key DeepSeek</span>
          <b>{info.deepseek_key_masked || '—'} · {info.deepseek_key_status}</b></div>
      </div>
      <h4 style={{ fontSize: 12, letterSpacing: 1.2, textTransform: 'uppercase',
        color: 'var(--muted)', marginBottom: 8 }}>{t('Bots por canal en uso')}</h4>
      <table style={{ marginBottom: 16 }}>
        <thead><tr><th>{t('Canal')}</th><th>Agente técnico</th><th>Agente comercial</th></tr></thead>
        <tbody>
          {detail.bots_by_channel.map(row => (
            <tr key={row.channel}>
              <td>{row.channel === 'web' ? '💻 Web' : '📱 WhatsApp'}</td>
              <td><Badge kind={row.technical === 'enabled' ? 'ok' : 'off'}>{row.technical}</Badge></td>
              <td><Badge kind={row.commercial === 'enabled' ? 'ok' : 'off'}>{row.commercial}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <h4 style={{ fontSize: 12, letterSpacing: 1.2, textTransform: 'uppercase',
          color: 'var(--muted)', margin: 0 }}>{t('Consumo de tokens')}</h4>
        <div className="spacer" />
        <select value={period} onChange={e => setPeriod(e.target.value)}
          style={{ border: '1px solid var(--input-border)', borderRadius: 8, padding: '6px 10px' }}>
          {PERIOD_OPTIONS.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
        </select>
      </div>
      {usage && (
        <table>
          <thead><tr><th>Bot</th><th>{t('Canal')}</th><th>Tokens</th><th>%</th></tr></thead>
          <tbody>
            {usage.rows.map((row, i) => (
              <tr key={i}>
                <td>{row.bot === 'technical' ? '🛠️ Técnico' : '💼 Comercial'}</td>
                <td>{row.channel}</td>
                <td><b>{fmt(row.tokens)}</b></td>
                <td>
                  <div className="progress" style={{ maxWidth: 120 }}>
                    <i style={{ width: `${row.pct}%` }} /></div>{row.pct}%
                </td>
              </tr>
            ))}
            <tr><td colSpan={2}><b>Total</b></td>
              <td><b>{fmt(usage.total_tokens)}</b></td><td>100%</td></tr>
          </tbody>
        </table>
      )}
    </Modal>
  )
}
