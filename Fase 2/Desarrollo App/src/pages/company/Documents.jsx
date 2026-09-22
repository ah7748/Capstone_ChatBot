import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { Badge, CHAT_TYPE_BADGE, Loading, Modal, STATUS_BADGE, errText, useToast } from '../../components/ui'
import { useI18n } from '../../context/I18nContext'

export default function Documents() {
  const { t } = useI18n()
  const toast = useToast()
  const [tab, setTab] = useState('docs')
  return (
    <>
      <div className="page-head">
        <h1>{t('Documentos del cliente')}</h1>
        <div className="sub">Cada documento pertenece al tipo de chat que lo usará (técnico o comercial).</div>
      </div>
      <div className="tabs">
        <button className={`tab ${tab === 'docs' ? 'active' : ''}`} onClick={() => setTab('docs')}>📄 {t('Documentos')}</button>
        <button className={`tab ${tab === 'faq' ? 'active' : ''}`} onClick={() => setTab('faq')}>❓ {t('Preguntas frecuentes')}</button>
        <button className={`tab ${tab === 'web' ? 'active' : ''}`} onClick={() => setTab('web')}>🌐 {t('Sitio web')}</button>
      </div>
      {tab === 'docs' && <DocsTab t={t} toast={toast} />}
      {tab === 'faq' && <FaqTab t={t} toast={toast} />}
      {tab === 'web' && <WebTab t={t} toast={toast} />}
    </>
  )
}

/* ------------------------- Documentos ------------------------- */
function DocsTab({ t, toast }) {
  const [filter, setFilter] = useState('all')
  const [data, setData] = useState(null)
  const [uploadType, setUploadType] = useState('technical')
  const [viewer, setViewer] = useState(null) // {doc, edit, content, version}
  const fileRef = useRef(null)

  const load = () => api(`/company/documents?chat_type=${filter}&page_size=100`)
    .then(setData).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [filter])

  async function upload(file) {
    const form = new FormData()
    form.append('file', file)
    form.append('chat_type', uploadType)
    try {
      await api('/company/documents', { method: 'POST', form })
      toast('Documento subido: ingesta en curso')
      load()
    } catch (e) { toast(errText(e)) }
  }

  async function openDoc(doc, edit) {
    try {
      const c = await api(`/company/documents/${doc.document_id}/content`)
      setViewer({ doc, edit, content: c.content, version: c.version })
    } catch (e) { toast(errText(e)) }
  }

  async function saveDoc() {
    try {
      await api(`/company/documents/${viewer.doc.document_id}/content`, {
        method: 'PUT', body: { content: viewer.content, version: viewer.version } })
      toast('Documento guardado: se reindexará automáticamente')
      setViewer(null); load()
    } catch (e) { toast(errText(e)) }
  }

  async function removeDoc(doc) {
    if (!confirm(`¿Eliminar ${doc.filename}?`)) return
    try { await api(`/company/documents/${doc.document_id}`, { method: 'DELETE' }); load() }
    catch (e) { toast(errText(e)) }
  }

  return (
    <>
      <div className="dropzone" style={{ marginBottom: 16 }}
        onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('drag') }}
        onDragLeave={e => e.currentTarget.classList.remove('drag')}
        onDrop={e => { e.preventDefault(); e.currentTarget.classList.remove('drag')
          if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]) }}>
        <div style={{ fontSize: 24 }}>⬆️</div>
        Arrastra un documento o{' '}
        <b style={{ color: 'var(--brand-dark)', cursor: 'pointer' }}
          onClick={() => fileRef.current.click()}>explora tu equipo</b>
        <div style={{ fontSize: 12, marginTop: 6 }}>PDF · DOCX · TXT · MD — máx. 25 MB</div>
        <div style={{ marginTop: 10, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12.5 }}>Indexar para:</span>
          <select value={uploadType} onChange={e => setUploadType(e.target.value)}
            style={{ border: '1px solid var(--input-border)', borderRadius: 8, padding: '6px 10px' }}>
            <option value="technical">🛠️ Chat técnico</option>
            <option value="commercial">💼 Chat comercial</option>
            <option value="both">Ambos chats</option>
          </select>
        </div>
        <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.txt,.md"
          onChange={e => e.target.files[0] && upload(e.target.files[0])} />
      </div>

      <div className="panel">
        <div className="panel-head">
          <h3>{t('Documentos')}</h3>
          <div className="tabs" style={{ borderBottom: 0, marginBottom: 0 }}>
            {[['all', 'Todos'], ['technical', 'Chat técnico'], ['commercial', 'Chat comercial']].map(([v, l]) => (
              <button key={v} className={`tab ${filter === v ? 'active' : ''}`}
                onClick={() => setFilter(v)}>{t(l)}</button>
            ))}
          </div>
          <div className="spacer" />
          <button className="btn btn-soft btn-sm" onClick={async () => {
            try { await api('/company/knowledge/reindex', { method: 'POST' }); toast('Reindexación lanzada') }
            catch (e) { toast(errText(e)) } }}>↻ Reindexar todo</button>
        </div>
        {!data ? <Loading t={t} /> : (
          <table>
            <thead><tr><th>Documento</th><th>Tipo de chat</th><th>{t('Estado')}</th>
              <th>Fragmentos</th><th>{t('Acciones')}</th></tr></thead>
            <tbody>
              {data.items.map(d => {
                const [sk, sl] = STATUS_BADGE[d.status] || ['off', d.status]
                const [ck, cl] = CHAT_TYPE_BADGE[d.chat_type] || ['off', d.chat_type]
                return (
                  <tr key={d.document_id}>
                    <td>📄 {d.filename}</td>
                    <td><Badge kind={ck}>{cl}</Badge></td>
                    <td><Badge kind={sk}>{sl}</Badge>{d.error_detail &&
                      <div style={{ fontSize: 11, color: 'var(--danger)' }}>{d.error_detail}</div>}</td>
                    <td>{d.chunks || '—'}</td>
                    <td style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => openDoc(d, false)}>{t('Ver')}</button>
                      <button className="btn btn-soft btn-sm" onClick={() => openDoc(d, true)}>{t('Editar')}</button>
                      {d.status === 'error' && (
                        <button className="btn btn-soft btn-sm" onClick={async () => {
                          await api(`/company/documents/${d.document_id}/reingest`, { method: 'POST' })
                          load() }}>Reintentar</button>
                      )}
                      <button className="btn btn-soft btn-sm" onClick={() => removeDoc(d)}>🗑</button>
                    </td>
                  </tr>
                )
              })}
              {data.items.length === 0 && (
                <tr><td colSpan={5} style={{ color: 'var(--muted)' }}>Sin documentos aún.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {viewer && (
        <Modal title={viewer.doc.filename} width={720} onClose={() => setViewer(null)} footer={<>
          <button className="btn btn-soft" onClick={() => setViewer(null)}>{t('Cerrar')}</button>
          {viewer.edit && <button className="btn btn-primary" onClick={saveDoc}>Guardar y reindexar</button>}
        </>}>
          <Badge kind="brand">{viewer.edit ? 'Edición' : 'Lectura'}</Badge>
          <textarea rows={16} readOnly={!viewer.edit} value={viewer.content}
            onChange={e => setViewer(v => ({ ...v, content: e.target.value }))}
            style={{ width: '100%', marginTop: 10, border: '1px solid var(--input-border)',
              borderRadius: 8, padding: 12, fontSize: 13 }} />
        </Modal>
      )}
    </>
  )
}

/* ------------------------- FAQ ------------------------- */
function FaqTab({ t, toast }) {
  const [data, setData] = useState(null)
  const [suggestions, setSuggestions] = useState(null)
  const [showSugg, setShowSugg] = useState(false)
  const [newFaq, setNewFaq] = useState(null)

  const load = () => api('/company/faqs?page_size=100').then(setData).catch(e => toast(errText(e)))
  useEffect(() => { load() }, [])

  async function openSuggestions() {
    setShowSugg(true); setSuggestions(null)
    try { setSuggestions(await api('/company/faqs/suggestions')) }
    catch (e) { toast(errText(e)); setShowSugg(false) }
  }

  async function accept(s) {
    try {
      const r = await api(`/company/faqs/suggestions/${s.suggestion_id}/accept`, { method: 'POST', body: {} })
      toast(`Pregunta añadida · ${r.faq_count} FAQ en total`)
      setSuggestions(sg => ({ ...sg, suggestions: sg.suggestions.filter(x => x.suggestion_id !== s.suggestion_id) }))
      load()
    } catch (e) { toast(errText(e)) }
  }

  async function exportFaq(format) {
    try {
      const res = await api(`/company/faqs/export?format=${format}`, { raw: true })
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = (res.headers.get('content-disposition') || '').split('filename=')[1]?.replaceAll('"', '')
        || `FAQ.${format}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) { toast(errText(e)) }
  }

  async function saveNew() {
    try {
      await api('/company/faqs', { method: 'POST', body: newFaq })
      setNewFaq(null); load(); toast('FAQ creada')
    } catch (e) { toast(errText(e)) }
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>{t('Preguntas frecuentes')}</h3>
        {data && <Badge kind="brand">{data.total} FAQ</Badge>}
        <div className="spacer" />
        <button className="btn btn-primary btn-sm" onClick={openSuggestions}>💡 {t('Agregar sugerencias')}</button>
        <button className="btn btn-soft btn-sm" onClick={() =>
          setNewFaq({ question: '', answer: '', chat_type: 'technical' })}>+ Nueva FAQ</button>
        <span style={{ color: 'var(--muted)', fontSize: 12 }}>{t('Exportar:')}</span>
        {['pdf', 'json', 'docx'].map(f => (
          <button key={f} className="btn btn-ghost btn-sm" onClick={() => exportFaq(f)}>{f.toUpperCase()}</button>
        ))}
      </div>
      {!data ? <Loading t={t} /> : (
        <div className="panel-body">
          {data.items.map(f => {
            const [ck, cl] = CHAT_TYPE_BADGE[f.chat_type]
            return (
              <div key={f.faq_id} style={{ border: '1px solid var(--border)', borderRadius: 10,
                padding: '12px 16px', marginBottom: 10 }}>
                <div style={{ float: 'right', display: 'flex', gap: 6 }}>
                  <Badge kind={ck}>{cl}</Badge>
                  <button className="btn btn-soft btn-sm" onClick={async () => {
                    if (confirm('¿Eliminar esta FAQ?')) {
                      await api(`/company/faqs/${f.faq_id}`, { method: 'DELETE' }); load()
                    } }}>{t('Eliminar')}</button>
                </div>
                <div style={{ fontWeight: 600, color: 'var(--heading)' }}>{f.question}</div>
                <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>{f.answer}</div>
              </div>
            )
          })}
          {data.items.length === 0 && <div style={{ color: 'var(--muted)' }}>Sin FAQ aún.</div>}
        </div>
      )}

      {showSugg && (
        <Modal title="💡 Preguntas sugeridas por la IA" width={740} onClose={() => setShowSugg(false)}
          footer={<button className="btn btn-soft" onClick={() => setShowSugg(false)}>{t('Cerrar')}</button>}>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 12 }}>
            Preguntas frecuentes de los usuarios que aún no están en el documento de FAQ.
          </div>
          {!suggestions ? <Loading t={t} /> : suggestions.suggestions.length === 0 ? (
            <div style={{ color: 'var(--muted)' }}>No hay sugerencias pendientes: la base de FAQ cubre
              las preguntas recientes de los usuarios.</div>
          ) : suggestions.suggestions.map(s => (
            <div key={s.suggestion_id} className="sugg">
              <div className="src">{s.chat_type === 'technical' ? '🛠️ TÉCNICO' : '💼 COMERCIAL'} ·
                preguntada {s.frequency} veces</div>
              <b>{s.question}</b><br />
              <span>{s.suggested_answer}</span>
              <div style={{ marginTop: 8 }}>
                <button className="btn btn-primary btn-sm" onClick={() => accept(s)}>{t('Añadir')}</button>
              </div>
            </div>
          ))}
        </Modal>
      )}

      {newFaq && (
        <Modal title="Nueva FAQ" onClose={() => setNewFaq(null)} footer={<>
          <button className="btn btn-soft" onClick={() => setNewFaq(null)}>{t('Cancelar')}</button>
          <button className="btn btn-primary" onClick={saveNew}>{t('Guardar')}</button>
        </>}>
          <div className="field"><label>Pregunta</label>
            <input value={newFaq.question} onChange={e => setNewFaq(f => ({ ...f, question: e.target.value }))} /></div>
          <div className="field"><label>Respuesta</label>
            <textarea rows={4} value={newFaq.answer}
              onChange={e => setNewFaq(f => ({ ...f, answer: e.target.value }))} /></div>
          <div className="field"><label>Tipo de chat</label>
            <select value={newFaq.chat_type}
              onChange={e => setNewFaq(f => ({ ...f, chat_type: e.target.value }))}>
              <option value="technical">🛠️ Técnico</option>
              <option value="commercial">💼 Comercial</option>
            </select></div>
        </Modal>
      )}
    </div>
  )
}

/* ------------------------- Sitio web ------------------------- */
function WebTab({ t, toast }) {
  const [info, setInfo] = useState(null)
  const [url, setUrl] = useState('')
  const [scan, setScan] = useState(null)
  const pollRef = useRef(null)

  const load = () => api('/company/website')
    .then(d => { setInfo(d); setUrl(d.url) })
    .catch(e => { if (e.code === 'WEBSITE_NOT_SET') setInfo({ url: null }); else toast(errText(e)) })
  useEffect(() => { load(); return () => clearInterval(pollRef.current) }, [])

  async function save() {
    try { await api('/company/website', { method: 'PUT', body: { url } }); toast('URL registrada'); load() }
    catch (e) { toast(errText(e)) }
  }

  async function startScan() {
    try {
      const r = await api('/company/website/scans', { method: 'POST' })
      toast('Escaneo iniciado')
      pollRef.current = setInterval(async () => {
        const s = await api(`/company/website/scans/${r.scan_id}`)
        setScan(s)
        if (s.status !== 'running') { clearInterval(pollRef.current); load() }
      }, 1500)
    } catch (e) { toast(errText(e)) }
  }

  if (!info) return <Loading t={t} />
  return (
    <div className="panel"><div className="panel-body" style={{ maxWidth: 640 }}>
      <div className="field"><label>URL del sitio</label>
        <div style={{ display: 'flex', gap: 10 }}>
          <input value={url || ''} onChange={e => setUrl(e.target.value)}
            placeholder="https://www.tuempresa.com" style={{ flex: 1 }} />
          <button className="btn btn-soft" onClick={save}>{t('Guardar')}</button>
          <button className="btn btn-primary" onClick={startScan} disabled={!info.url}>
            🌐 {t('Escanear sitio del cliente')}</button>
        </div>
        <div className="hint">El escáner recorre el sitio (respetando robots.txt) y añade su
          contenido a la base de conocimiento.</div>
      </div>
      {(scan || info.last_scan) && (() => {
        const s = scan || info.last_scan
        return (
          <table>
            <thead><tr><th>{t('Estado')}</th><th>Progreso</th><th>Páginas</th><th>Nuevas</th></tr></thead>
            <tbody><tr>
              <td><Badge kind={s.status === 'done' ? 'ok' : s.status === 'failed' ? 'danger' : 'warn'}>
                {s.status}</Badge></td>
              <td><div className="progress" style={{ maxWidth: 140 }}>
                <i style={{ width: `${s.progress_pct}%` }} /></div>{s.progress_pct}%</td>
              <td>{s.pages_indexed}</td><td>{s.new_pages}</td>
            </tr></tbody>
          </table>
        )
      })()}
    </div></div>
  )
}
