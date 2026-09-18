import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { Badge, Kpi, Loading, errText, useToast } from '../../components/ui'
import { PERIOD_OPTIONS, useI18n } from '../../context/I18nContext'
import TenantModal from './TenantModal'

export default function PlatformDashboard() {
  const { t } = useI18n()
  const toast = useToast()
  const [period, setPeriod] = useState('7d')
  const [data, setData] = useState(null)
  const [openTenant, setOpenTenant] = useState(null)

  useEffect(() => {
    api(`/platform/dashboard?period=${period}`).then(setData).catch(e => toast(errText(e)))
  }, [period])

  if (!data) return <Loading t={t} />
  const k = data.kpis
  return (
    <>
      <div className="page-head">
        <h1>{t('Dashboard global')}</h1>
        <Badge kind="brand">{data.tenants.length} empresas</Badge>
        <div className="spacer" />
        <select value={period} onChange={e => setPeriod(e.target.value)}
          style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px' }}>
          {PERIOD_OPTIONS.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
        </select>
      </div>
      <div className="cards-row">
        <Kpi label={t('Conversaciones')} value={k.conversations} />
        <Kpi label={t('Resueltas por el bot')} value={`${k.bot_resolved_pct}%`} />
        <Kpi label={t('Derivadas a agente')} value={k.escalations} />
        <Kpi label="Tokens DeepSeek" value={k.tokens.toLocaleString()} />
      </div>
      <div className="panel">
        <div className="panel-head"><h3>Actividad por empresa</h3></div>
        <table>
          <thead><tr>
            <th>Empresa</th><th>Canales</th><th>{t('Conversaciones')}</th>
            <th>% resuelto bot</th><th>Derivadas</th><th>Tokens</th><th>{t('Estado')}</th>
          </tr></thead>
          <tbody>
            {data.tenants.map(row => (
              <tr key={row.tenant_id} className="rowlink" onClick={() => setOpenTenant(row.tenant_id)}>
                <td><b>{row.name}</b></td>
                <td>{row.channels.join(' · ')}</td>
                <td>{row.conversations}</td>
                <td>
                  <div className="progress"><i style={{ width: `${row.bot_resolved_pct}%` }} /></div>
                  {row.bot_resolved_pct}%
                </td>
                <td>{row.escalations}</td>
                <td>{row.tokens.toLocaleString()}</td>
                <td><Badge kind={row.status === 'active' ? 'ok' : 'warn'}>{row.status}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {openTenant && <TenantModal tenantId={openTenant} onClose={() => setOpenTenant(null)} />}
    </>
  )
}
